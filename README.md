# TrendVN

Hệ thống tự động đăng lại video xu hướng lên kênh TikTok của bạn: mỗi ngày thu thập video đang thịnh hành
(Douyin, Kuaishou ở Trung Quốc; TikTok, Instagram Reels ở Mỹ) → phát hiện video **mới** → giữ nguyên nhạc, thêm
**Vietsub** hoặc **lồng tiếng Việt** (Google Gemini) → đăng qua trình duyệt Chrome thật vào giờ vàng. Có bảng điều khiển
(dùng được trên điện thoại) để xem hàng đợi, sửa mô tả, bấm **Đăng ngay**, và lịch chạy hoàn toàn tự động bằng n8n riêng.

```
 Chrome trên máy (agent)  ── thu thập / đăng ──►  worker (Docker) ◄── lịch ── n8n (Docker)
   Playwright + yt-dlp                            SQLite · ffmpeg · Gemini · bảng điều khiển
```

## Cài đặt (Mac hoặc Linux; Mac mới toanh khoảng 30–60 phút vì phải tải Docker Desktop và build lần đầu)

Cần: Docker (Desktop trên Mac), **Python 3.10+** (macOS chỉ kèm 3.9: cài thêm `brew install python@3.12`), Google Chrome bản của Google. Hướng dẫn từng bước trên Mac: [docs/MAC.md](docs/MAC.md).

```bash
tar xzf trendvn-1.5.tar.gz && cd trendvn-1.5     # hoặc nhấp đúp macos/Cai-dat.command
./trendvn install                                # cấu hình, build Docker, nạp workflow n8n, bật lịch, cài agent
```

Rồi 5 việc chỉ bạn làm được:
1. `./trendvn open` → Thêm → Cài đặt: dán khóa Gemini (lấy ở https://aistudio.google.com/apikey), bật **Xử lý video**.
2. `./trendvn tiktok login`: tự đăng nhập TikTok một lần trong cửa sổ Chrome hiện ra.
3. Thêm → Cài đặt → Lịch đăng: đặt **Tài khoản TikTok đích** đúng kênh bạn vừa đăng nhập (mặc định là một tài khoản mẫu).
4. Bấm **▶ Bắt đầu** ở Tổng quan (lần quét đầu chỉ ghi mốc, nên bấm lại sau vài giờ hoặc chờ lịch 3 giờ) cho tới khi tab **Đăng bài** có video, rồi `./trendvn tiktok dry-run` (chạy thử, không đăng; báo `"status": "idle"` nghĩa là chưa có video dựng xong, không phải lỗi).
5. Bật **Tự đăng** khi hài lòng.

## Lệnh hay dùng

| Việc | Lệnh |
|---|---|
| Chạy / dừng / khởi động lại | `./trendvn up` · `./trendvn down` · `./trendvn restart [worker\|n8n\|agent]` |
| Xem log | `./trendvn logs -f` · `./trendvn logs worker\|n8n\|agent -n 200` |
| Build lại image Docker | `./trendvn build` (thêm `--no-cache` nếu cần) |
| Build lại hệ thống n8n từ mã | `./trendvn n8n build` → `./trendvn n8n import` |
| Bật / tắt lịch tự động | `./trendvn n8n activate` · `./trendvn n8n deactivate` |
| Sức khỏe hệ thống | `./trendvn status` · `./trendvn doctor` |
| Chuyển hệ thống đang chạy từ thư mục bản 1.2 | giải nén bản này ở thư mục mới, rồi `./trendvn migrate <thư-mục-1.2>` (docs/DEPLOY.md mục 11) |
| Áp dụng bản mới | giải nén bản mới đè lên thư mục đang chạy (`tar xzf trendvn-X.tar.gz --strip-components=1`), rồi `./trendvn update` |
| Sao lưu / khôi phục | `./trendvn backup` · `./trendvn restore <file>` |
| Đóng gói chép sang máy khác | `./trendvn package` |
| Kiểm thử | `./trendvn test` (nhanh) · `./trendvn test all` (đầy đủ, gồm Docker và Chrome thật) |

Toàn bộ lệnh, kèm lệnh `docker compose` tương đương: [docs/COMMANDS.md](docs/COMMANDS.md). `make help` cũng chạy được.

## Bố cục thư mục

```
trendvn                 lệnh duy nhất cho mọi việc (Makefile là lối tắt)
compose.yaml  .env.example  VERSION  CHANGELOG.md
services/worker/        image Docker: hàng đợi, luật, Gemini, ffmpeg, bảng điều khiển
  src/trendvn_worker/     domain/ store/ ai/ media/ web/ ui/ + tasks.py pipeline.py (mỗi thư mục một việc)
services/agent/         Chrome trên máy: thu thập và đăng TikTok
  src/trendvn_agent/      collector/ (sources/ mỗi nền tảng một file) publisher/ browser.py server.py
n8n/                    build.py sinh 6 workflow từ mã · manage.py nạp/bật/xuất · workflows/*.json
scripts/                install · backup · restore · doctor · package · fmt · service (systemd, launchd)
macos/                  file nhấp đúp cho Mac
tests/                  worker/ agent/ tools/ (hơn 320 test) + e2e/ (giao diện bằng Chrome thật)
docs/                   tài liệu chi tiết
data/                   (tự tạo, không đóng gói) dữ liệu: worker/ agent/ backups/
```

## Tài liệu

[Mac](docs/MAC.md) · [Lệnh](docs/COMMANDS.md) · [Triển khai](docs/DEPLOY.md) · [Vận hành](docs/OPERATIONS.md) ·
[Kiến trúc](docs/ARCHITECTURE.md) · [n8n](docs/N8N.md) · [Prompt Gemini](docs/PROMPTS.md) · [Bảo mật](docs/SECURITY.md) ·
[API](docs/API.md) · [Quy tắc cho agent](AGENTS.md) · [Lộ trình 1.4](docs/ROADMAP.md) · [Rà soát 1.3](docs/REVIEW-1.3.md) · [Thay đổi](CHANGELOG.md)

## Giới hạn cần biết

- **Chỉ một máy chạy tự động cho một kênh TikTok**; máy còn lại chỉ dùng để thử.
- **TikTok đôi khi hiện hình xác minh.** Hệ thống không giải hay vượt: nó tạm dừng đăng và báo bạn giải một lần
  (`./trendvn tiktok trust`, hoặc nhấp đúp `macos/Xac-minh-TikTok.command`).
- **Nguồn Mỹ** cần IP Mỹ (`TRENDVN_US_PROXY` trong `.env`); không có thì tự bỏ qua, không bao giờ gắn nhầm nội dung Việt là xu hướng Mỹ.
- **Bản quyền và điều khoản nền tảng là trách nhiệm của bạn.** Hệ thống chỉ chặn trùng lặp và nội dung nhạy cảm theo quy tắc, không kiểm tra bản quyền.
- Mặc định tất cả chỉ mở trên chính máy này (`127.0.0.1`). Xem từ xa: dùng đường hầm SSH/VPN ([docs/DEPLOY.md](docs/DEPLOY.md)).
