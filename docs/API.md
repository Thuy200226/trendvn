# API

Mọi lời gọi `POST` (trừ các form của bảng điều khiển) dùng `Authorization: Bearer <TRENDVN_TOKEN>` và JSON. Phản hồi luôn là JSON; lỗi kiểm tra trả `400` kèm `{"error": "..."}`.

## Worker — `http://127.0.0.1:5681`

### Đọc

| Phương thức, đường dẫn | Xác thực | Trả về |
|---|---|---|
| `GET /health` | không | `{ok, project, version}` |
| `GET /api/status` | token hoặc bảng điều khiển nội bộ | Trạng thái gọn: `counts`, `jobs` (100 mới nhất), `discovery`, `publisher`, `published_today`, `daily_limit` (tổng giới hạn của các tài khoản đang bật), `accounts` (từng tài khoản: `id, username, topics, enabled, daily_limit, published_today, logged_in`...), `wanted_topics` (chủ đề có tài khoản nhận: collector tìm đúng các chủ đề này), `thresholds`, `weights`, `unresolved_publishes`... Collector và n8n dùng cái này |
| `GET /api/dashboard` | như trên | Toàn bộ dữ liệu bảng điều khiển: `review`, `approval`, `pipeline`, `performance`, `events`, `settings`, `by_platform`... |
| `GET /` | chỉ `Host` cho phép | Bảng điều khiển HTML |
| `GET /media/<id>/final`, `/source`, `/media/voice-sample` | chỉ `Host` cho phép | Video/âm thanh, hỗ trợ `Range` |

### Ghi (token)

| Đường dẫn | Nội dung | Ghi chú |
|---|---|---|
| `POST /api/ingest` | `{platform, stream, observed_at, topic?, items:[{source_id, url, country, title, rank, views, evidence_url, meta}]}` | ≤ 100 mục; `topic` (không bắt buộc) là danh mục của chính luồng đó (tab Douyin, chip TikTok), một mã trong thực đơn chủ đề; từ đó và từ từ khóa trong tiêu đề worker suy ra gợi ý chủ đề của từng video. Lần đầu của mỗi luồng là baseline. Trả `{baseline, new, existing, candidates:[{id, source_id}]}` |
| `POST /api/media/pending` | `{limit, platform?, source_ids?}` | Ứng viên chưa có video, điểm cao nhất trước (lọc theo nền tảng nếu có). `source_ids` (danh sách ≤ 300 mã video, mỗi mã 1–100 ký tự `A-Za-z0-9_-`): chỉ xét các mã này **trước khi** cắt còn `limit`; lần quét chỉ tải được video nó vừa thấy nên kho ứng viên cũ điểm cao không được chặn nó. Sai kiểu hoặc quá dài trả 400. Cùng điểm thì theo `first_seen` rồi `id`, thứ tự cố định |
| `POST /api/attach` | `{id, filename}` | Gắn file đã tải trong `data/worker/inbox`; trả `queued` hoặc `duplicate` |
| `POST /api/media/failed` | `{id, reason}` | Ghi tải lỗi (lần thứ 3 thành `failed`) |
| `POST /api/process` | `{max}` (1–8) | Xử lý tối đa `max` video liên tiếp; dừng khi `disabled`, `blocked`, `idle`, `rate_limited` |
| `POST /api/housekeeping` | `{}` | Giải phóng việc treo (xử lý quá 30 phút xếp lại hàng đợi, đăng quá 45 phút chờ xác nhận; yêu cầu xóa bài chưa ai nhận quá 300 giây thành `failed`, đã nhận mà không có kết quả quá 600 giây thành `unknown`, trừ khi một tác vụ xóa còn chạy dưới 900 giây) và dọn đĩa (`pruned`: hết hạn, tệp, lịch sử, tệp mồ côi; xem ARCHITECTURE mục 5) |
| `POST /api/heartbeat` | `{component: discovery\|publisher, ok, detail}` | Cập nhật tình trạng; `detail` dạng object được **gộp** với lần trước |
| `POST /api/publish/claim` | `{}` | `{status: claimed\|disabled\|blocked\|wait\|limit\|idle, ...}`; khi `claimed` kèm `id, lease, caption, output_file, output_hash, account` (mã tài khoản, agent dùng để mở đúng hồ sơ Chrome), `target` (tên TikTok), `visibility`. Lịch tự động thử lần lượt các tài khoản (tài khoản đăng lâu nhất trước), mỗi tài khoản theo giờ vàng, giới hạn ngày và giãn cách riêng, và chọn video điểm cao nhất thuộc chủ đề tài khoản đó nhận |
| `POST /api/publish/finish` | `{id, lease, outcome: published\|failed\|unknown\|duplicate, url, reason}` | `lease` phải đúng; `url` phải là địa chỉ `*.tiktok.com` |
| `POST /api/publish/peek` | `{}` | Bài kế tiếp (chạy thử, không đổi trạng thái) |
| `POST /api/publish/unresolved`, `/api/publish/resolve` | `{}` / `{id, outcome: published\|failed, url}` | Bài chưa xác nhận |
| `POST /api/stats` | `{items:[{video_id, views, likes, comments, shares}]}` | Khớp bài đã đăng theo `/video/<id>` |
| `POST /api/publisher/challenge` | `{active: bool, account?: string}` | Bật/tắt trạng thái "TikTok đang đòi xác minh": bật thì `publish/claim` trả `blocked` cho tới khi tắt. `account` là mã tài khoản có hồ sơ gặp CAPTCHA: thông báo và lệnh gợi ý nêu đúng `--account`, và tắt cho một tài khoản khác thì không gỡ chặn (không gửi `account` thì tắt được bằng mọi tài khoản) |
| `POST /api/accounts` | `{}` | `{accounts, wanted_topics}` |
| `POST /api/accounts/add` | `{username, topics:[...], id?, label?, enabled?, daily_limit?, min_gap?, windows?, visibility?}` | Thêm tài khoản (tối đa 10). Giới hạn bỏ trống/`null` = dùng cài đặt chung |
| `POST /api/accounts/update` | `{id, ...các trường như trên}` | Sửa; không cho tắt tài khoản cuối cùng đang bật |
| `POST /api/accounts/login` | `{id, ok: bool}` | Agent báo trình duyệt có đang đăng nhập đúng tài khoản này không (lịch tự động bỏ qua tài khoản đã đăng xuất) |
| `POST /api/accounts/delete` | `{id}` | Xóa; không xóa tài khoản cuối cùng hoặc tài khoản đang có bài chưa xác nhận |
| `POST /api/settings` | Một phần của cài đặt (xem `validate_settings`) | Trả `{changed:[...]}` |
| `POST /api/notify` | `{kind:"summary"}` hoặc `{kind:"text", text}` | Gửi qua các kênh đã cấu hình; trả kênh nào thành công |

### Tác vụ nền (nút trên bảng điều khiển)

| Đường dẫn | Nội dung | Ghi chú |
|---|---|---|
| `POST /api/tasks/start` (token) | `{kind: update\|collect\|process\|process_one\|queue_download\|publish\|dryrun\|stats, job_id?}` | Trả `{id}`; `409`-tương-đương là lỗi 400 "Đang có một việc dùng trình duyệt..." khi trùng khóa |
| `GET /api/tasks` (token hoặc giao diện nội bộ) | | `{running, tasks:[{id, kind, state, steps, result, error}]}` |
| `GET /fragment/tasks` | | HTML bảng tiến độ (giao diện dùng để cập nhật trực tiếp) |
| `POST /api/publish/claim`, `/api/publish/peek` | `{job_id?}` | Có `job_id`: nhận/xem đúng video đó (đăng thủ công: bỏ qua công tắc, giờ vàng, giới hạn, giãn cách; các chốt bảo vệ vẫn giữ) |
| `POST /api/publish/finish` | `outcome: published\|failed\|deferred\|unknown\|duplicate` | `failed` được đếm (3 lần thì chuyển Cần xem, nghỉ 1 giờ giữa các lần); `deferred` không đếm (TikTok đòi xác minh, trùng mô tả khi đăng tay) |
| `GET /media/<id>/final\|source\|poster`, `/media/shot/<shot_*.png>` | | Video, ảnh xem trước, ảnh chụp lần xem thử |

## Agent — `http://<TRENDVN_AGENT_BIND>:5682` (mặc định `172.20.0.1`)

Chỉ một việc trình duyệt tại một thời điểm; đang bận trả `409`.

| Đường dẫn | Nội dung | Việc làm |
|---|---|---|
| `GET /health` | không xác thực | `{ok, busy}` |
| `POST /api/collect` | `{platforms?: [...], download?: bool}` | Quét, chấm điểm, nhập vào worker, tải video mới. Trả báo cáo theo nguồn |
| `POST /api/publish` | `{job_id?}` | Xin worker `claim` (có `job_id` = đăng đúng video đó theo nút bấm); nếu được thì mở Chrome đăng, xác nhận trên hồ sơ, báo `finish`. Không bao giờ ném lỗi: lỗi trước khi bấm Đăng là `failed`, sau khi bấm là `unknown` |
| `POST /api/dry-run` | `{job_id?}` | Tải video (kế tiếp hoặc được chọn) lên TikTok Studio, điền mô tả, chụp ảnh vào `data/worker/exports/shot_*.png` rồi dừng, **không bấm Đăng** |
| `POST /api/session` | `{}` | Kiểm tra đã đăng nhập TikTok chưa, gửi heartbeat |
| `POST /api/verify` | `{}` | Đối chiếu bài "chưa xác nhận" với hồ sơ công khai |
| `POST /api/stats` | `{}` | Đọc lượt xem/tim từ hồ sơ công khai, gửi worker |

## Dòng lệnh

| Lệnh | Tác dụng |
|---|---|
| `PYTHONPATH=services/agent/src .venv/bin/python -m trendvn_agent.collector [douyin kuaishou tiktok instagram]` | Quét thật và nhập vào worker |
| `./trendvn tiktok login\|trust\|status\|dry-run\|verify\|stats` | Đăng nhập, giải xác minh một lần, kiểm tra phiên, chạy thử, đối chiếu, đọc lượt xem |
| `./trendvn doctor` | Chẩn đoán |
| `./trendvn n8n build && ./trendvn n8n import` | Sinh lại và nạp lại workflow |

## Ví dụ

```bash
TOKEN=$(grep '^TRENDVN_TOKEN=' .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" localhost:5681/api/status | python3 -m json.tool | head
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"daily_limit": 1, "post_windows": [[19, 22]]}' localhost:5681/api/settings
```

## Khung chat tìm sản phẩm

Các điểm cuối này chỉ dành cho trang bảng điều khiển của chính máy này (cùng nguồn, kèm `csrf` của trang); không có token API cho chúng.

- `POST /chat/send` (JSON, thân tối đa 12 MiB): `{csrf, account, text, files:[{name,data}]}` với `data` là base64 (tối đa 3 tệp, 4 MiB/tệp, tổng 8 MiB). Tin chứa link sản phẩm/link rút gọn của TikTok (không kèm tệp) được kiểm như link chia sẻ; còn lại được nhận diện thành sản phẩm. Trả `{id}` của câu trả lời đang chạy.
- `POST /chat/act` (JSON, thân tối đa 16 KiB): `{csrf, action, id, ...}` với `action` là `find` (`id` của tin sản phẩm, `source` là `tiktok|douyin|auto`, `human` có thể là `true` cho cửa sổ tự xác minh, `account` tùy chọn), `pick` (`id` của tin video, `source_id`, `platform`, `confirmed: true`) hoặc `confirm` (`id` của tin link).
- `POST /chat/act` còn có: `login` và `check` (`channel`: `tiktok|douyin`, `account`) mở cửa sổ đăng nhập / đọc cookie của hồ sơ; `clear` xóa lịch sử đã xong; `forget` (`account`, `product_id`) xóa một link đã lưu.
- `GET /fragment/chat`: phần HTML của luồng tin và cột bên cạnh (trang hỏi lại mỗi 2,5 giây khi còn việc đang chạy).
- `POST /api/channel/report` (có token; do agent gọi): `{account, channel, state: ok|out|wall, who}` ghi lại tình trạng đăng nhập của một tài khoản trên một kênh.

Agent nhận các POST xác thực `/api/channel/login` và `/api/channel/check` (`account`, `channel`), `/api/search` (`account,query,queries,source,links`), `/api/search/open` (như trên, mở cửa sổ cho chủ tự xác minh, tối đa 4 phút mỗi trang; worker chờ tối đa 6 phút) và `/api/search/download` (`account,job_id,item`). Mỗi nguồn trả tối đa 20 ứng viên (tối đa 40 khi tìm cả hai; worker xếp hạng và giữ 20); chỉ tải sau khi chủ chọn. Một nguồn lỗi (ở chế độ `auto`) được ghi vào `note` thay vì làm hỏng cả kết quả. Video tìm kiếm có `search_account` và không bao giờ được lịch chuyển sang tài khoản khác.



## Tìm kiếm và xóa bài (1.9)

`POST /chat/send` (phiên giao diện + CSRF): `{account, source:auto|tiktok|douyin|kuaishou|instagram, topic?, sales:bool, category?, text?, files?, request_key?}`. Cùng `request_key` trả lại cùng lượt, không tạo thêm tác vụ; ngoại lệ: nếu câu trả lời cũ đã **lỗi** (`error`, ví dụ trình duyệt bận) thì mã được trả lại và lần gửi này chạy như mới (một lượt mới, một tác vụ mới). Mã thuộc tài khoản khác bị từ chối. Phần chọn thể loại/ngành hàng được đưa vào từ khóa của từng nguồn. `POST /chat/act` thêm `delete_history` với `id` và `dismiss` với `id,platform,source_id`; các thao tác đã có giữ nguyên.

`POST /post-delete` (form giao diện + CSRF): `{id,url,account,confirmed:true}`. Tạo quyền một lần gắn với bản ghi bài đã đăng, rồi gọi tác vụ xóa. Agent nhận `POST /api/post-delete` với `{job_id,grant}`, xin worker `POST /api/post-delete/claim` và gửi `POST /api/post-delete/finish` với `{job_id,grant,outcome:deleted|failed|unknown,reason}`; `deleted` chỉ nhận sau khi agent đã nhận việc (claim), còn `failed`/`unknown` nhận cả trước đó. Nếu worker không nhận được phản hồi của agent (chờ tối đa 420 giây): chưa nhận việc thì ghi `failed` (chưa thử, có thể thử lại), đã nhận thì ghi `unknown` (chủ phải kiểm tra, hệ thống không tự xóa lại). Khởi động lại worker áp dụng cùng quy tắc. Các route API dùng token, không ghi token vào lịch sử; API tác vụ chung không tự tạo được quyền xóa. `performance.delete_state` cho biết tình trạng; trạng thái video và lịch sử đếm bài đã đăng được giữ nguyên.

`POST /post-delete-checked` (form + CSRF): `{id,url,account,confirmed:true,outcome:present|deleted}` (`present` mặc định để giữ tương thích). Chủ đã kiểm tra đúng bài trong tài khoản sở hữu. Chỉ nhận bản ghi `unknown` (và `failed` cho `deleted`: chủ đã tự xóa bài bằng tay) còn khớp URL/tài khoản/danh tính/trạng thái published hiện tại; `present` chuyển sang `failed`, `deleted` chốt bài đã xóa với lý do “Chủ đã kiểm tra” để phân biệt bằng chứng tự động từ TikTok. Không gọi trình duyệt, không xóa lại, không khôi phục quyền xóa cũ; giữ lịch sử đăng và chống trùng.

Agent `POST /api/search` nhận `source` bốn kênh, `queries` theo kênh, `sources` các kênh đã đăng nhập và `require_session:true`; `POST /api/channel/login|check` nhận `{account,channel}`. Chỉ một tác vụ trình duyệt tại một thời điểm.

`GET /fragment/queue` dùng cùng quyền bảng điều khiển, trả riêng vùng hàng chờ và thao tác có CSRF. Chat lấy phần này khi tìm/tải kết thúc để cập nhật bảng mà giữ bản nháp. Dấu chống lặp `request_key` giữ tối thiểu 30 ngày, độc lập với việc ẩn lịch sử; bỏ ứng viên lưu dấu nguồn/ID bị loại để không tìm/tải lại.
