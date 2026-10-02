# Tham chiếu lệnh

Mọi việc chạy qua **`./trendvn <lệnh>`** (trong thư mục dự án). `make <lệnh>` gọi đúng lệnh đó. `./trendvn help` in bảng này ngắn gọn.
Cột phải là lệnh Docker/hệ thống tương đương, để bạn biết bên dưới có gì và làm được bằng tay khi cần.

## Cài đặt và vòng đời

| Lệnh | Việc | Tương đương |
|---|---|---|
| `./trendvn install [--no-activate] [--no-service]` | Cài lần đầu, chạy lại an toàn: kiểm tra điều kiện → tạo `.env` và bí mật → `.venv` cho agent → sinh workflow → build + chạy container → nạp workflow → bật lịch → cài dịch vụ agent → `doctor` | (8 bước, xem `scripts/install.sh`) |
| `./trendvn up` | Build image nếu đổi, chạy n8n + worker, **chờ tới khi cả hai khỏe** | `docker compose up -d --build --wait` |
| `./trendvn down` | Dừng container, giữ dữ liệu | `docker compose down` |
| `./trendvn restart [worker\|n8n\|agent]` | Khởi động lại một thành phần (bỏ trống = cả ba) | `docker compose restart …` / `systemctl --user restart trendvn-agent` / `launchctl kickstart -k …` |
| `./trendvn update` | Áp dụng bản mới sau khi thay mã: sinh lại workflow → build + chạy lại container (rồi xóa image cũ của chính dự án này, ~570 MB mỗi bản) → nạp workflow (lịch đang bật vẫn bật) → cập nhật gói Python của agent → khởi động lại agent → `doctor` | `n8n build` + `up` + `n8n import` + `agent venv` + `agent restart` |
| `./trendvn status` | Container, agent, workflow đang bật, địa chỉ | `docker compose ps` + kiểm tra agent + `docker compose exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n list:workflow` |
| `./trendvn doctor` | Chẩn đoán đầy đủ; mỗi dòng lỗi có cách sửa; thoát mã 1 nếu có mục bắt buộc lỗi | `scripts/doctor.py` |
| `./trendvn open` | Mở bảng điều khiển trong trình duyệt | `open` (Mac) / `xdg-open` (Linux) |
| `./trendvn uninstall [--purge]` | Gỡ dịch vụ agent, dừng container. `--purge` xóa `data/worker`, `data/agent`, `.venv`, volume n8n (hỏi xác nhận) nhưng GIỮ `data/backups` và `.env` | `docker compose down [-v]` |
| `./trendvn migrate <thư-mục-1.2> [--yes] [--no-service]` | Chuyển hệ thống đang chạy từ thư mục bản 1.2 sang thư mục mới này ([DEPLOY.md](DEPLOY.md) mục 11) | — |
| `./trendvn version` | Số phiên bản | `cat VERSION` |

## Xem log

```bash
./trendvn logs                 # worker + n8n, 100 dòng cuối
./trendvn logs -f              # theo dõi trực tiếp (Ctrl+C để thoát)
./trendvn logs worker -n 300   # chỉ worker, 300 dòng
./trendvn logs n8n -f
./trendvn logs agent -f        # agent Chrome trên máy: data/agent/agent.log
```

| Thành phần | Log nằm ở | Cách xem bằng tay |
|---|---|---|
| worker, n8n | log của container (tự xoay vòng tối đa 5 × 10 MB mỗi dịch vụ) | `docker compose logs -f worker` |
| agent | `data/agent/agent.log` (Mac còn `data/agent/launchd.log` cho lỗi khởi động) | `tail -f data/agent/agent.log` |
| Nhật ký nghiệp vụ (video nào vào/ra trạng thái nào) | Bảng điều khiển → Thêm → Nhật ký | `GET /api/dashboard` |
| Lịch sử chạy workflow | n8n → Executions (giữ 7 ngày) | |

## Build và n8n

| Lệnh | Việc |
|---|---|
| `./trendvn build [--no-cache]` | Build image `trendvn/worker:<phiên bản>` từ `services/worker/` |
| `./trendvn n8n build` | Sinh `n8n/workflows/*.json` từ `n8n/build.py` (đọc `.env`: cổng agent, múi giờ). `--check` chỉ kiểm tra file có khớp mã không |
| `./trendvn n8n import` | Nạp credential (token lấy từ `.env`, không in ra) và 6 workflow vào n8n đang chạy. Lịch đang bật trước đó sẽ được bật lại |
| `./trendvn n8n activate [id…]` | Bật lịch (mặc định `trendvn01daily`, `trendvn02publish`, `trendvn03daily`); n8n tự khởi động lại một lần |
| `./trendvn n8n deactivate [id…]` | Tắt lịch (mặc định tất cả workflow TrendVN) |
| `./trendvn n8n status` | Workflow nào BẬT / tắt |
| `./trendvn n8n export [thư mục]` | Lưu workflow đang có trong n8n ra JSON (mặc định `n8n/exported/`), ví dụ sau khi bạn sửa trong giao diện n8n |

Chi tiết cách hệ thống n8n được sinh ra: [N8N.md](N8N.md).

## Agent trình duyệt và TikTok

| Lệnh | Việc |
|---|---|
| `./trendvn agent install` / `uninstall` | Cài / gỡ dịch vụ nền (systemd người dùng trên Linux, launchd trên Mac); chỉ đụng dịch vụ của **thư mục này** |
| `./trendvn agent start` / `stop` / `restart` / `status` | Điều khiển dịch vụ (không có systemd/launchd thì dùng tiến trình nền + pid file) |
| `./trendvn agent logs [-f] [-n N]` | Log agent |
| `./trendvn agent run` | Chạy trong terminal này (Ctrl+C dừng), tiện gỡ lỗi |
| `./trendvn agent venv` / `update` | Tạo lại `.venv` / nâng yt-dlp và playwright rồi khởi động lại |
| `./trendvn tiktok login [phút] [--account ID]` | Mở Chrome thật để **bạn** đăng nhập TikTok một lần (không bao giờ tự nhập mật khẩu). Mỗi tài khoản có hồ sơ Chrome riêng; không có `--account` là tài khoản `main` (tài khoản mặc định). `ID` là mã hiện trong thẻ tài khoản ở bảng điều khiển |
| `./trendvn tiktok trust [phút] [--account ID]` | Giải hình xác minh của TikTok một lần |
| `./trendvn tiktok dry-run` | Tải video lên TikTok Studio, điền mô tả, chụp ảnh rồi dừng — **không đăng**. Ảnh: `data/worker/exports/shot_*.png` (tên in trong kết quả; nút "Xem thử" trên bảng điều khiển cũng hiện ảnh). Cần đã có video xử lý xong; báo `"status": "idle"` nghĩa là chưa có. Ảnh lỗi nằm ở `data/agent/shots/` |
| `./trendvn tiktok status [--account ID]` / `verify` / `stats` | Kiểm tra phiên của một tài khoản / đối chiếu bài chưa xác nhận (trên đúng tài khoản đã đăng) / đọc lượt xem của mọi tài khoản đang bật |

## Dữ liệu và bàn giao

| Lệnh | Việc |
|---|---|
| `./trendvn backup [--with-session] [--keep N]` | `data/backups/trendvn-<ngày-giờ>.tar.gz` (0600): SQLite, khóa Gemini, thông báo, `.env`, dữ liệu n8n. `--with-session` kèm phiên TikTok; `--keep N` giữ N bản mới nhất |
| `./trendvn restore <file> [--yes]` | Khôi phục (ghi đè, hỏi xác nhận). Giữ khóa mạng/uid của máy hiện tại; đọc được bản sao lưu từ 1.2 |
| `./trendvn package` | Kiểm tra rồi đóng gói `dist/trendvn-<phiên bản>.tar.gz` + `.sha256`: chỉ mã nguồn, không `.env`, không `data/`, không `.venv` |

Sao lưu định kỳ (cron; cron dùng PATH rất ngắn nên phải khai báo để tìm thấy `docker`): `0 3 * * 0 PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; cd /đường/dẫn/trendvn && ./trendvn backup --keep 8`.

## Kiểm thử và định dạng mã

| Lệnh | Việc |
|---|---|
| `./trendvn fmt` | Định dạng mã Python (black) và sửa lỗi lint an toàn (ruff). Cần `python3 -m pip install -r requirements-dev.txt` |

### Kiểm thử

| Lệnh | Việc |
|---|---|
| `./trendvn test` | `lint` + `unit` (vài chục giây) |
| `./trendvn test lint` | Workflow khớp mã sinh · cú pháp Python/shell · script chạy được trên bash 3.2 của macOS · `compose.yaml` hợp lệ · shellcheck nếu có |
| `./trendvn test unit` | Hơn 150 test đơn vị/tích hợp trên máy |
| `./trendvn test container` | Build image rồi chạy lại **toàn bộ** test trong image (có ffmpeg) và dựng video thật |
| `./trendvn test e2e` | Chrome thật: bố cục ở 7 kích thước × 6 tab và mọi luồng bấm nút (cần `.venv`; `TRENDVN_SAMPLE=video.mp4` để có video thật) |
| `./trendvn test all` | Tất cả các mục trên |

## Biến môi trường hay đổi (`.env`)

Mẫu và giải thích từng biến: [.env.example](../.env.example). Thêm dòng vào `.env` rồi `./trendvn up` (container) hoặc `./trendvn agent restart` (agent).

| Biến | Tác dụng |
|---|---|
| `COMPOSE_PROJECT_NAME` | Tên project Docker (mặc định `trendvn`); đổi khi chạy hai bản trên một máy |
| `TRENDVN_N8N_PORT`, `TRENDVN_WORKER_PORT`, `TRENDVN_AGENT_PORT` | Cổng (mặc định 5680, 5681, 5682) |
| `TRENDVN_BIND` | `127.0.0.1` (mặc định, chỉ máy này) hoặc `0.0.0.0` (kèm `TRENDVN_UI_PASSWORD`) |
| `TRENDVN_US_PROXY` | Proxy Mỹ cho nguồn TikTok/Instagram |
| `TRENDVN_TZ` | Múi giờ của lịch và giờ vàng |
