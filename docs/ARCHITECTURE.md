# Kiến trúc và nơi đặt từng quy tắc

## 1. Ba khối và vì sao tách như vậy

```
┌──────────────── Docker (mạng riêng trendvn_private) ────────────────┐      ┌──── Máy chủ (host) ────┐
│  n8n :5680        điều phối theo lịch, gọi API bằng HTTP            │      │  agent :5682           │
│  worker :5681     dữ liệu, quy tắc, ffmpeg, Gemini, bảng điều khiển │◄────►│  Chrome thật (Playwright)│
│  volume: data/worker/ (SQLite, video)   n8n_data (thông tin n8n)        │      │  hồ sơ: data/agent/    │
└──────────────────────────────────────────────────────────────────────┘      └────────────────────────┘
```

- **worker** giữ mọi *quyết định* (được đăng không, video này đạt không) và mọi *dữ liệu*. Không chạm vào trình duyệt.
- **agent** chỉ *làm* việc cần Chrome thật: quét bốn nguồn, tải video, đăng bài, đọc lượt xem. Không tự quyết định gì: mỗi lần đăng nó phải xin worker cấp quyền (claim) và báo lại kết quả.
- **n8n** chỉ *hẹn giờ và nối bước*. Toàn bộ logic nghiệp vụ nằm ở worker, nên đổi workflow không thể làm hỏng luật an toàn.
- Agent cần Chrome thật và màn hình/hồ sơ của máy nên chạy trực tiếp trên host (dịch vụ systemd người dùng). Nó chỉ lắng nghe trên địa chỉ cầu nối Docker (`TRENDVN_AGENT_BIND`, mặc định `172.20.0.1`), n8n gọi qua tên `trendvn-agent`.
- Ba khối cùng dùng một khóa `TRENDVN_TOKEN` (Bearer). n8n giữ khóa trong credential "TrendVN · Worker riêng".
- **Cách n8n tìm agent:** Linux dùng địa chỉ cầu nối của dự án (`TRENDVN_AGENT_HOSTREF`); macOS/Windows (Docker Desktop, container chạy trong máy ảo) dùng `host-gateway` và agent nghe ở `127.0.0.1`. `scripts/setup_env.py` tự chọn theo hệ điều hành.

## 2. Vòng đời của một video (máy trạng thái)

```
                 lần quét đầu                     
   (quét) ─────► baseline  (chỉ để nhận diện video mới, không bao giờ xử lý)
        │ lần quét sau, video chưa từng thấy
        ▼
     candidate ──tải lỗi 3 lần──► failed
        │ tải xong, chưa trùng hash
        ▼
      queued ──trùng hash──► duplicate
        │ worker nhận việc
        ▼
    processing ──trùng hình / lệch chủ đề / nhạy cảm / Gemini không chắc / lỗi──► needs_review ──bạn duyệt──► queued (bỏ qua kiểm tra phán đoán)
        │ dựng xong                                                        └──bạn bỏ──► rejected
        ├── cài đặt "duyệt tay" bật ─► awaiting_approval ──duyệt──► ready │ bỏ──► rejected
        ▼
       ready ──đủ điều kiện đăng──► publishing ──xác nhận trên hồ sơ──► published
                                        │  ├─ nút Đăng chưa bấm mà lỗi ─► ready (thử lại sau)
                                        │  ├─ trùng mô tả đã có ─► duplicate
                                        │  └─ đã bấm mà chưa xác nhận ─► publish_unknown ──bạn/agent xác nhận──► published │ ready
```

Bất biến quan trọng (đều có test):

1. **`publish_unknown` chặn mọi lần đăng sau đó.** Không có cơ chế tự thử lại một bài đã bấm Đăng.
2. **Mỗi lần chỉ một bài ở trạng thái `publishing`** (kiểm tra và đặt trong cùng một giao dịch SQLite `BEGIN IMMEDIATE`).
3. **Lease:** `processing` và `publishing` mang một token; kết quả trả về sai token bị từ chối, nên tiến trình cũ (treo, chạy lại) không ghi đè kết quả mới.
4. **`baseline` không bao giờ thành ứng viên.** Lần quét đầu của mỗi luồng chỉ ghi mốc; như vậy hệ thống không đăng ồ ạt các video đã nổi từ trước.
5. Quét cũ hơn lần trước bị từ chối (`observed_at`), lô có một mục sai thì cả lô không được ghi.

### Các điểm bổ sung ở 1.2

- **Tác vụ nền** (`services/worker/app/tasks.py`): mỗi nút trên bảng điều khiển tạo một dòng trong bảng `tasks` và một luồng chạy nền. Khóa: một việc dùng trình duyệt tại một thời điểm (cùng khóa với agent, nên cả lịch n8n), một lần xử lý tại một thời điểm (cùng `process_lock` với `/api/process`). Khởi động lại worker đánh dấu việc dang dở là lỗi.
- **Trạng thái đăng:** `publishing` ghi nhớ `prev_state` (để đăng tay thất bại không vô tình duyệt video), `publish_fails` và `last_publish_fail` (nghỉ 1 giờ sau lỗi, 3 lần thì `needs_review`). Kết quả `deferred` không tính lỗi. Ngưỡng `publishing` → `publish_unknown` là 45 phút.
- **Dựng video:** một lượt ffmpeg: đưa về khung dọc 1080×1920 (nền mờ cho video ngang, vuông, 4:5, 3:4), nhận đúng video xoay, phụ đề đặt tránh vùng chữ của TikTok, chuẩn hóa âm lượng −14 LUFS, bỏ siêu dữ liệu, tối đa 30 fps, đo chất lượng đầu ra (`qc`) và tạo ảnh xem trước.
- **Mô tả và hashtag:** Gemini đề xuất; mã luôn lọc lại (`build_caption`: bỏ hashtag tên nền tảng, chuẩn hóa Unicode, cắt ở ranh giới từ), `lint_caption` hiển thị chất lượng, bạn sửa được trước khi đăng.

## 3. Quyết định nằm ở đâu

| Câu hỏi | Nơi quyết định | Hàm / cấu hình |
|---|---|---|
| Video nào đáng xem xét? | `services/agent/collector.py` | `parse_*` (chuẩn hóa từng nguồn), `qualifies` (thời lượng, tuổi, lượt xem/tim), `score` |
| Video nào tải trước? | `services/agent/collector.py` | `score` = mức tương tác ÷ (tuổi tính theo giờ, tối thiểu 6)^0.6 × trọng số nguồn |
| Có tải thêm không? | `services/agent/collector.py` | `fetch_pending`: dừng khi hàng chờ ≥ `max_backlog` |
| Video mới hay cũ? | `services/worker/app/core.py` | `Store.ingest` (baseline/candidate, trùng theo `(platform, source_id)` và URL) |
| Trùng file? | `services/worker/app/core.py` | `Store.attach` (SHA-256 nội dung) |
| Trùng hình dù mã hóa khác? | `services/worker/app/media.py` | `fingerprint` (5 khung hình, hash 64-bit) + `similar` |
| Nhạc hay lời? Chủ đề? Nhạy cảm? | Gemini theo `services/worker/app/prompts.py` | kiểm tra lại cứng ở `core.validate_analysis` |
| Xử lý theo đường nào? | `services/worker/app/core.py` | `validate_analysis` trả `original`/`vietsub`/`voiceover` |
| Dựng video | `services/worker/app/media.py` | `render`, `ass_subtitles`, `make_voice` |
| Được đăng lúc này không? | `services/worker/app/core.py` | `publish_claim`: công tắc → không có bài chưa xác nhận → giờ vàng → giới hạn ngày → giãn cách → chọn bài điểm cao nhất |
| Đăng và xác nhận | `services/agent/publisher.py` | `publish_one`, `verify_unresolved` |
| Học từ kết quả | `services/worker/app/core.py` | `record_stats`, `platform_weights` (cần ≥ 8 bài đã đăng > 24 giờ) |
| Gửi thông báo | `services/worker/app/notify.py` | `Notifier` (chống spam theo loại + khóa) |
| Cài đặt đổi được | `services/worker/app/core.py` | `validate_settings` (mỗi khóa có khoảng giá trị chặt) |

## 4. Nguồn thu thập

| Nguồn | Cách lấy | Ghi chú |
|---|---|---|
| Douyin | Trang 精选 (`/jingxuan`), bắt JSON `aweme/v2/web/module/feed` | Trình duyệt tự ký yêu cầu; chỉ nhận `aweme_type == 0` (video), bỏ quảng cáo và album ảnh |
| Kuaishou | Trang `brilliant`, bắt GraphQL `brilliantTypeData` | Đôi khi ngắt kết nối: thử lại tối đa 3 lần |
| TikTok | Trang Explore, nhấn các chip Singing & Dancing, Comedy, Lipsync, Shows, bắt `explore/item_list` | **Chỉ chạy khi IP thoát là Mỹ** |
| Instagram | Trang Reels công khai, lấy mã reel, `yt-dlp` lấy siêu dữ liệu và tải | **Chỉ chạy khi IP thoát là Mỹ** |

Douyin và Kuaishou chỉ phục vụ nội dung trong nước nên IP nào cũng cho đúng nguồn Trung Quốc. TikTok và Instagram đổi nội dung theo IP, nên agent kiểm tra quốc gia của IP thoát (`exit_country`) trước mỗi lần quét. Nếu gặp CAPTCHA hoặc yêu cầu đăng nhập, luồng đó báo lỗi thay vì cố vượt qua.

## 5. Dữ liệu

- `data/worker/trendvn.sqlite3` (WAL): `jobs` (mỗi video một dòng), `observations` (lịch sử thứ hạng/lượt xem mỗi lần quét), `events` (nhật ký), `settings`, `api_calls` (đếm lượt gọi Gemini), `post_stats` (lượt xem sau đăng), `notif_log` (chống spam thông báo).
- `data/worker/inbox/` video gốc tải về; `data/worker/jobs/<id>/` sản phẩm dựng (`final.mp4`, `vi.ass`, `manifest.json` ghi cả phiên bản prompt).
- `data/worker/gemini.key`, `data/worker/notify.json`: bí mật, quyền 0600, không bao giờ trả về qua API.
- `data/agent/profiles/collector-*`, `data/agent/profiles/publisher` (phiên TikTok), `data/agent/agent.log`, `data/agent/shots/` (ảnh chụp khi đăng lỗi; ảnh của lần chạy thử nằm ở `data/worker/exports/` để bảng điều khiển hiển thị).

## 6. Mở rộng

- **Thêm nguồn mới:** viết `parse_<nguồn>` (trả danh sách mục có `source_id`, `url`, `title`, `likes`, `views`, `duration`, `created`, `media`), thêm hàm `scan_<nguồn>`, đăng ký trong `SOURCES` (đặt `geo_locked`), thêm tên miền vào `PLATFORMS` và `COUNTRIES` ở `services/worker/app/core.py`, thêm CDN vào `CDN_SUFFIXES`.
- **Đổi cách chấm điểm:** sửa `score` (một hàm thuần, đã có test ở `tests/test_features.py::ScoringTests`).
- **Đổi luật an toàn khi đăng:** chỉ sửa `publish_claim`; agent và n8n không cần đổi.

## 7. Bố cục mã và dữ liệu

```
services/worker/app/   core.py (luật, SQLite)  media.py (ffmpeg, Gemini)  prompts.py  tasks.py (nút chạy nền)  notify.py  ui.py  server.py  → đóng gói thành image Docker
services/agent/        collector.py (4 nguồn)  publisher.py (TikTok)  common.py  server.py                    → chạy trên máy, cần Chrome thật
n8n/                   build.py (sinh workflow)  manage.py (nạp/bật/xuất)  workflows/*.json (kết quả)
scripts/               install · backup · restore · uninstall · test · doctor · package · setup_env · agent · lib · service/
data/                  worker/ (gắn vào container)  agent/ (hồ sơ Chrome, log, ảnh chụp)  backups/     ← sinh ra khi chạy, không đóng gói
```

Quy tắc đặt file: nghiệp vụ và luật nằm ở `services/worker/app/core.py`; mọi việc cần Chrome nằm ở `services/agent`; n8n chỉ hẹn giờ và nối bước (xem [N8N.md](N8N.md)); mọi lệnh vận hành đi qua `./trendvn` (xem [COMMANDS.md](COMMANDS.md)).

