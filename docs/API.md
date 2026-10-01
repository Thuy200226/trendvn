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
| `POST /api/media/pending` | `{limit}` | Ứng viên chưa có video |
| `POST /api/attach` | `{id, filename}` | Gắn file đã tải trong `data/worker/inbox`; trả `queued` hoặc `duplicate` |
| `POST /api/media/failed` | `{id, reason}` | Ghi tải lỗi (lần thứ 3 thành `failed`) |
| `POST /api/process` | `{max}` (1–8) | Xử lý tối đa `max` video liên tiếp; dừng khi `disabled`, `blocked`, `idle`, `rate_limited` |
| `POST /api/housekeeping` | `{}` | Dọn tác vụ treo |
| `POST /api/heartbeat` | `{component: discovery\|publisher, ok, detail}` | Cập nhật tình trạng; `detail` dạng object được **gộp** với lần trước |
| `POST /api/publish/claim` | `{}` | `{status: claimed\|disabled\|blocked\|wait\|limit\|idle, ...}`; khi `claimed` kèm `id, lease, caption, output_file, output_hash, account` (mã tài khoản, agent dùng để mở đúng hồ sơ Chrome), `target` (tên TikTok), `visibility`. Lịch tự động thử lần lượt các tài khoản (tài khoản đăng lâu nhất trước), mỗi tài khoản theo giờ vàng, giới hạn ngày và giãn cách riêng, và chọn video điểm cao nhất thuộc chủ đề tài khoản đó nhận |
| `POST /api/publish/finish` | `{id, lease, outcome: published\|failed\|unknown\|duplicate, url, reason}` | `lease` phải đúng; `url` phải là địa chỉ `*.tiktok.com` |
| `POST /api/publish/peek` | `{}` | Bài kế tiếp (chạy thử, không đổi trạng thái) |
| `POST /api/publish/unresolved`, `/api/publish/resolve` | `{}` / `{id, outcome: published\|failed, url}` | Bài chưa xác nhận |
| `POST /api/stats` | `{items:[{video_id, views, likes, comments, shares}]}` | Khớp bài đã đăng theo `/video/<id>` |
| `POST /api/publisher/challenge` | `{active: bool}` | Bật/tắt trạng thái "TikTok đang đòi xác minh": bật thì `publish/claim` trả `blocked` cho tới khi tắt |
| `POST /api/accounts` | `{}` | `{accounts, wanted_topics}` |
| `POST /api/accounts/add` | `{username, topics:[...], id?, label?, enabled?, daily_limit?, min_gap?, windows?, visibility?}` | Thêm tài khoản (tối đa 10). Giới hạn bỏ trống/`null` = dùng cài đặt chung |
| `POST /api/accounts/update` | `{id, ...các trường như trên}` | Sửa; không cho tắt tài khoản cuối cùng đang bật |
| `POST /api/accounts/delete` | `{id}` | Xóa; không xóa tài khoản cuối cùng hoặc tài khoản đang có bài chưa xác nhận |
| `POST /api/settings` | Một phần của cài đặt (xem `validate_settings`) | Trả `{changed:[...]}` |
| `POST /api/notify` | `{kind:"summary"}` hoặc `{kind:"text", text}` | Gửi qua các kênh đã cấu hình; trả kênh nào thành công |

### Tác vụ nền (nút trên bảng điều khiển)

| Đường dẫn | Nội dung | Ghi chú |
|---|---|---|
| `POST /api/tasks/start` (token) | `{kind: update\|collect\|process\|publish\|dryrun\|stats, job_id?}` | Trả `{id}`; `409`-tương-đương là lỗi 400 "Đang có một việc dùng trình duyệt..." khi trùng khóa |
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
