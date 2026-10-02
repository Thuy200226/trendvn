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

- **Tác vụ nền** (`services/worker/src/trendvn_worker/tasks.py`): mỗi nút trên bảng điều khiển tạo một dòng trong bảng `tasks` và một luồng chạy nền. Khóa: một việc dùng trình duyệt tại một thời điểm (cùng khóa với agent, nên cả lịch n8n), một lần xử lý tại một thời điểm (cùng `process_lock` với `/api/process`). Khởi động lại worker đánh dấu việc dang dở là lỗi.
- **Trạng thái đăng:** `publishing` ghi nhớ `prev_state` (để đăng tay thất bại không vô tình duyệt video), `publish_fails` và `last_publish_fail` (nghỉ 1 giờ sau lỗi, 3 lần thì `needs_review`). Kết quả `deferred` không tính lỗi. Ngưỡng `publishing` → `publish_unknown` là 45 phút.
- **Dựng video:** một lượt ffmpeg: đưa về khung dọc 1080×1920 (nền mờ cho video ngang, vuông, 4:5, 3:4), nhận đúng video xoay, phụ đề đặt tránh vùng chữ của TikTok, chuẩn hóa âm lượng −14 LUFS, bỏ siêu dữ liệu, tối đa 30 fps, đo chất lượng đầu ra (`qc`) và tạo ảnh xem trước.
- **Mô tả và hashtag:** Gemini đề xuất; mã luôn lọc lại (`build_caption`: bỏ hashtag tên nền tảng, chuẩn hóa Unicode, cắt ở ranh giới từ), `lint_caption` hiển thị chất lượng, bạn sửa được trước khi đăng.

## 3. Quyết định nằm ở đâu

| Câu hỏi | Nơi quyết định | Hàm / cấu hình |
|---|---|---|
| Video nào đáng xem xét? | `services/agent/src/trendvn_agent/collector/rules.py` + `collector/sources/*.py` | `parse_*` (chuẩn hóa từng nguồn), `qualifies` (thời lượng, tuổi, lượt xem/tim), `score` |
| Video nào tải trước? | `services/agent/src/trendvn_agent/collector/rules.py` | `score` = mức tương tác ÷ (tuổi tính theo giờ, tối thiểu 6)^0.6 × trọng số nguồn |
| Có tải thêm không? | `services/agent/src/trendvn_agent/collector/run.py` | `fetch_pending`: dừng khi hàng chờ ≥ `max_backlog` |
| Video mới hay cũ? | `services/worker/src/trendvn_worker/store/ingest.py` | `Store.ingest` (baseline/candidate, trùng theo `(platform, source_id)` và URL) |
| Trùng file? | `services/worker/src/trendvn_worker/store/ingest.py` | `Store.attach` (SHA-256 nội dung) |
| Trùng hình dù mã hóa khác? | `services/worker/src/trendvn_worker/media/fingerprint.py` | `fingerprint` (5 khung hình, hash 64-bit) + `similar` |
| Nhạc hay lời? Chủ đề? Nhạy cảm? | Gemini theo `services/worker/src/trendvn_worker/ai/prompts.py` | kiểm tra lại cứng ở `domain/analysis.py::validate_analysis` |
| Xử lý theo đường nào? | `services/worker/src/trendvn_worker/domain/route.py` | `choose_route` trả đường đi và lý do; `validate_analysis` (analysis.py) kiểm tra rồi gọi nó |
| Dựng video | `services/worker/src/trendvn_worker/media/` và `ai/tts.py` | `render`, `ass_subtitles`, `make_voice` |
| Được đăng lúc này không? | `services/worker/src/trendvn_worker/store/publishing.py` | `publish_claim`: công tắc → không có bài chưa xác nhận → giờ vàng → giới hạn ngày → giãn cách → chọn bài điểm cao nhất |
| Đăng và xác nhận | `services/agent/src/trendvn_agent/publisher/post.py`, `publisher/jobs.py` | `publish_one`, `verify_unresolved` |
| Học từ kết quả | `services/worker/src/trendvn_worker/store/feedback.py` | `record_stats`, `platform_weights` (cần ≥ 8 bài đã đăng > 24 giờ) |
| Gửi thông báo | `services/worker/src/trendvn_worker/notify.py` | `Notifier` (chống spam theo loại + khóa) |
| Cài đặt đổi được | `services/worker/src/trendvn_worker/domain/settings.py` | `validate_settings` (mỗi khóa có khoảng giá trị chặt) |

## 3b. Chủ đề và nhiều tài khoản

- **Thực đơn chủ đề** (`domain/topics.py`): 15 chủ đề (âm nhạc/nhảy, hài, thú cưng, ẩm thực, du lịch, gia đình, làm đẹp, thể thao, game, anime, phim, đời sống, kiến thức, tin nóng/drama, giải trí tổng hợp) cộng `other` (quảng cáo, bán hàng, spam; chỉ chủ duyệt tay mới đăng). Prompt Gemini, schema và giao diện đều sinh từ cùng một bảng này.
- **Hai lần quyết định chủ đề.** Trước khi tải: *gợi ý* miễn phí từ danh mục của nguồn (tab Douyin, chip TikTok) và từ khóa trong tiêu đề (đo trên 230 tiêu đề Douyin thật: đoán trúng 67% trong số tiêu đề có từ khóa; danh mục của nguồn tự nó cũng nhiễu nên chỉ dùng để chọn tải). Sau khi phân tích: **Gemini quyết định**; video thuộc chủ đề không tài khoản nào nhận vào "Cần xem" với lý do rõ.
- **Tài khoản** (`accounts`, `store/accounts.py`, `domain/accounts.py`): mỗi tài khoản có tên TikTok, danh sách chủ đề nhận, và (tùy chọn) giới hạn ngày, giãn cách, giờ vàng, chế độ hiển thị riêng; bỏ trống thì dùng cài đặt chung. Tài khoản của bản 1.0–1.3 thành `main` (nhận các chủ đề cũ: giải trí, nhạc, hài, thú cưng, gia đình, đời sống; migration phiên bản 4 thêm `tin nóng` nếu chủ chưa sửa danh sách). Mỗi tài khoản có **hồ sơ Chrome riêng** (`data/agent/profiles/publisher-<id>`; `main` giữ `publisher`) nên phiên đăng nhập không lẫn.
- **Lịch đăng** (`store/publishing.py`): mỗi lần hỏi, thử lần lượt các tài khoản đang bật, tài khoản đăng lâu nhất trước; tài khoản nào còn chỗ (giờ vàng, giới hạn ngày, giãn cách, không có bài chưa xác nhận) và có video điểm cao thuộc chủ đề của nó thì nhận video đó. Bài chưa xác nhận chỉ chặn tài khoản của nó; một bài đang đăng chặn mọi tài khoản (agent chỉ làm một việc trình duyệt một lúc). Nút Đăng ngay chọn tài khoản nhận chủ đề đó (ít bài hôm nay nhất), nếu không có thì tài khoản mặc định.
- **Thu thập theo chủ đề** (`collector/sources`): Douyin: một lần mở trang `jingxuan`, đọc luồng mặc định rồi bấm tab của từng chủ đề cần (tối đa 6 tab mỗi lần quét, luân phiên theo đồng hồ); Kuaishou không có danh mục cho khách chưa đăng nhập; TikTok: chip theo chủ đề; chip không có thì bỏ qua không thử lại. Ngưỡng cho tab chủ đề thấp hơn luồng chung vì đo trên 520 video Douyin thật: chỉ 12% video trong tab đạt mốc 150 nghìn tim của luồng chung (trung vị 10–70 nghìn) và tuổi trung vị là 39 ngày nên giới hạn 7 ngày chỉ cho qua 10%; luồng chủ đề dùng 15% ngưỡng tim/lượt xem và cho phép cũ gấp 4 lần (28 ngày), điểm xếp hạng vẫn ưu tiên video mới. Chọn tải (`choose_downloads`): bỏ video có gợi ý là chủ đề không ai nhận, chia lượt giữa các chủ đề, điểm cao trước, để một chủ đề đông không lấn át chủ đề khác.

## 3c. Hiệu suất (đo trên video thật, máy 12 nhân)

Thời gian xử lý một video: Gemini khoảng hai phần ba (30–100 giây, tùy lúc API rảnh; thường gặp lỗi 503 "quá tải" kéo dài nên chốt chặn và xếp hàng lại quan trọng hơn tối ưu), dựng khoảng một phần tư, phần còn lại là bản xem trước, dấu vân tay và kiểm tra (đo: video 78 giây dựng 24 giây; video ngang 153 giây dựng 40 giây).

- **Xử lý song song** (`pipeline.process_many`): mặc định 2 video cùng lúc (`TRENDVN_PROCESS_PARALLEL`, 1 = lần lượt). Vì phần lớn thời gian một video là chờ Gemini nên 2 luồng gần như gấp đôi thông lượng mà không tranh CPU; dừng phát việc mới ngay khi gặp trạng thái dừng (tắt, thiếu khóa, hết hạn mức, hết hàng chờ).
- **Giữ nguyên hình** (`media/render.can_copy_video`): video **giữ nguyên** (nhạc, không lời) đã là dọc H.264 8-bit trong khung 1080×1920, ≤ 30 khung/giây, bitrate ≤ 6 Mb/s thì chỉ chỉnh âm lượng, hình được sao nguyên từng điểm ảnh (kiểm bằng md5). Đo trên video thật: 3,3 giây thay cho 24 giây, tệp 13,8 MB thay cho 24,8 MB, không mất chất lượng.
- **Chờ thích nghi khi thu thập Douyin** (`collector/capture.Feed`): thay các lần chờ cố định bằng "chờ tới khi trang đã trả lời và yên lặng"; cuộn dừng sau hai lần cuộn liên tiếp không có gì mới. Số video mỗi tab đo được vẫn 40–59 như trước. Kuaishou và TikTok **giữ chờ cố định**: dữ liệu Kuaishou về rải rác trong khoảng 25 giây (đã thấy ở giây 4, 16–19, 21, 25) và đôi khi kẹt ở yêu cầu đầu; lần so sánh trực tiếp không phân định được vì trang bị hạn chế khi tải lặp (0 đến 98 video với cả hai bản mã), nên không đánh đổi độ tin cậy lấy vài giây.
- Không đổi sau khi đo: bộ lọc khung 9:16 (giải mã 1080p và co ảnh chiếm hơn nửa, thử các biến thể không nhanh hơn), mã hóa `veryfast` (đã chọn ở Phase B), trang bảng điều khiển (8–12 ms mỗi lần tải trên CSDL thật nhỏ; đo trên CSDL giả 20.000 video: dựng trang 39 ms, `status` 17 ms, `record_stats` 200 mục 9 ms; trước đợt rà soát 52, 22 và 927 ms).

## 4. Nguồn thu thập

| Nguồn | Cách lấy | Ghi chú |
|---|---|---|
| Douyin | Trang 精选 (`/jingxuan`), bắt JSON `aweme/v2/web/module/feed`; mỗi tab chủ đề (音乐, 小剧场, 动物, 美食, 旅行, 亲子, 美妆穿搭, 体育, 游戏, 二次元, 影视, 生活vlog, 知识) cho khoảng 40 video riêng | Trình duyệt tự ký yêu cầu; chỉ nhận `aweme_type == 0` (video), bỏ quảng cáo và album ảnh |
| Kuaishou | Trang `brilliant`, bắt GraphQL `brilliantTypeData` | Đôi khi ngắt kết nối: thử lại tối đa 3 lần |
| TikTok | Trang Explore, nhấn các chip theo chủ đề (Singing & Dancing, Comedy, Animals, Food...), bắt `explore/item_list` | **Chỉ chạy khi IP thoát là Mỹ** |
| Instagram | Trang Reels công khai, lấy mã reel, `yt-dlp` lấy siêu dữ liệu và tải | **Chỉ chạy khi IP thoát là Mỹ** |

Douyin và Kuaishou chỉ phục vụ nội dung trong nước nên IP nào cũng cho đúng nguồn Trung Quốc. TikTok và Instagram đổi nội dung theo IP, nên agent kiểm tra quốc gia của IP thoát (`exit_country`) trước mỗi lần quét. Nếu gặp CAPTCHA hoặc yêu cầu đăng nhập, luồng đó báo lỗi thay vì cố vượt qua.

## 5. Dữ liệu

- `data/worker/trendvn.sqlite3` (WAL): `jobs` (mỗi video một dòng), `observations` (lịch sử thứ hạng/lượt xem mỗi lần quét), `events` (nhật ký), `settings`, `accounts` (các tài khoản TikTok: chủ đề nhận, giới hạn riêng), `api_calls` (đếm lượt gọi Gemini), `post_stats` (lượt xem sau đăng), `notif_log` (chống spam thông báo).
- `data/agent/profiles/`: một hồ sơ Chrome cho mỗi tài khoản TikTok (`publisher` cho `main`, `publisher-<mã>` cho các tài khoản thêm), `collector-cn`, `collector-us`.
- `data/worker/inbox/` video gốc tải về; `data/worker/jobs/<id>/` sản phẩm dựng (`final.mp4`, `vi.ass`, `manifest.json` ghi cả phiên bản prompt).
- **Dọn đĩa** (`store/retention.py`, chạy trong `/api/housekeeping`): ứng viên quá 3 ngày chưa tải và video quá 21 ngày không ai quyết định thành `rejected`; video đã đăng/bỏ/trùng/lỗi mất tệp gốc và bản dựng sau 7 ngày (giữ `manifest.json`, `poster.jpg` và dòng trong CSDL để không đăng trùng); xóa lịch sử cũ (quan sát 30 ngày, nhật ký 60, tác vụ 14); tệp mồ côi và ảnh chụp cũ. Dưới 1 GB trống thì ngừng tải thêm, dưới 512 MB thì ngừng dựng; ô "Ổ đĩa" ở trang Tổng quan cho biết còn bao nhiêu. Worker khởi động lại tự xếp lại video đang xử lý dở (tối đa 2 lần, sau đó chờ chủ xem).
- `data/worker/gemini.key`, `data/worker/notify.json`: bí mật, quyền 0600, không bao giờ trả về qua API.
- `data/agent/agent.log`, `data/agent/shots/` (ảnh chụp khi đăng lỗi; ảnh của lần chạy thử nằm ở `data/worker/exports/` để bảng điều khiển hiển thị).

## 6. Mở rộng

- **Thêm nguồn mới (2 file + test):** tạo một file trong `collector/sources/` với `parse_<nguồn>` (trả danh sách mục có `source_id`, `url`, `title`, `likes`, `views`, `duration`, `created`, `media`), `scan_<nguồn>` và `CDN` (tên miền phát video), đăng ký một dòng trong `collector/sources/__init__.py` (đặt `geo_locked`), và thêm **một dòng** vào `REGISTRY` ở `services/worker/src/trendvn_worker/domain/platforms.py` (tên, nước, tên miền, ngưỡng lượt xem mặc định). Nhãn trên bảng điều khiển, ô nhập ngưỡng, cài đặt mặc định, hashtag bị cấm và tên trong thông báo đều sinh từ `REGISTRY`; `tests/agent/test_collector.py::RegistryContractTests` kiểm tra hai phía khớp nhau.
- **Thêm tab mới (1 file + 1 dòng):** một module trong `ui/tabs/` có `render(view)` và một dòng trong `TABS` ở `ui/page.py` (nhãn, biểu tượng, hàm đếm huy hiệu); mục điều hướng và `<section>` được sinh từ đó.
- **Thêm cài đặt mới (5 chỗ, có chủ ý):** `DEFAULTS` và `validate_settings` (domain/settings.py), `DASHBOARD_SETTINGS` (store/reporting.py), ô nhập (ui/tabs/more.py), đọc biểu mẫu (web/forms.py); test `tests/worker/test_settings.py`. Chưa gom thành bảng khai báo vì mỗi cài đặt có luật kiểm tra riêng và việc gom không rút ngắn được chỗ nào đáng kể.
- **Đổi cách chấm điểm:** sửa `score` (một hàm thuần, đã có test ở `tests/agent/test_collector.py::ScoringTests`).
- **Đổi luật an toàn khi đăng:** chỉ sửa `publish_claim`; agent và n8n không cần đổi.

## 7. Bố cục mã và dữ liệu

```
services/worker/
  Dockerfile
  src/trendvn_worker/                  → đóng gói thành image Docker (chỉ thư viện chuẩn của Python)
    domain/        luật thuần, không đọc/ghi gì: platforms, settings, analysis, route, readability, hardsubs, captions, schedule, states
    store/         SQLite: base, schema (di trú có số phiên bản), ingest, queue, publishing, captions, health, task_log, feedback, reporting
    ai/            Gemini: gemini (gọi, ngân sách, dự phòng model), prompts, analyzer, tts, errors
    media/         ffmpeg: ffmpeg, fingerprint, geometry, subtitles, render
    pipeline.py    một video đi từ hàng đợi tới bản dựng đã kiểm tra
    web/           HTTP: handler, security, forms, api, media_files, pages, responses, app, server
    ui/            giao diện: view, components, cards, tabs/ (mỗi tab một file), static/app.css, static/app.js
    notify.py  tasks.py  version.py
services/agent/
  src/trendvn_agent/                   → chạy trên máy (Chrome thật), cùng .venv của dự án
    collector/     sources/ (douyin, kuaishou, tiktok, instagram), rules, capture, download, run, cli
    publisher/     session, profile, studio, challenge, post, jobs, screenshots, cli
    browser.py  config.py  log.py  worker_client.py  server.py
n8n/               build.py (sinh workflow) · manage.py (nạp/bật/xuất) · workflows/*.json (kết quả)
scripts/           install · backup · restore · migrate · uninstall · test · doctor · package · setup_env · agent · lib · service/
data/              worker/ (gắn vào container) · agent/ (hồ sơ Chrome, log, ảnh chụp) · backups/     ← sinh ra khi chạy, không đóng gói
```

Quy tắc đặt file (mỗi file một việc, ghi ở dòng docstring đầu file): luật nghiệp vụ không phụ thuộc I/O nằm ở `domain/` để kiểm thử nhanh; mọi truy cập SQLite nằm ở `store/` (mỗi mối quan tâm một mixin, ghép lại thành `Store`); mọi việc cần Chrome nằm ở `services/agent`; một nguồn mới = một file trong `collector/sources/`; mỗi tab của giao diện là một file trong `ui/tabs/`; n8n chỉ hẹn giờ và nối bước (xem [N8N.md](N8N.md)); mọi lệnh vận hành đi qua `./trendvn` (xem [COMMANDS.md](COMMANDS.md)).
