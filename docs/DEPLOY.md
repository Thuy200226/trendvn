# Triển khai: cài, Docker, truy cập từ xa, chuyển máy

## 1. Yêu cầu

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Linux (đã kiểm chứng trên Ubuntu) hoặc macOS ([MAC.md](MAC.md)). Windows: mục 8 |
| Docker | Docker Engine + plugin `docker compose` v2 (Mac: Docker Desktop); user hiện tại chạy được `docker` không cần sudo |
| Python | **3.10 trở lên** cho agent (playwright và yt-dlp yêu cầu), có `venv`. macOS chỉ kèm 3.9: cài thêm `brew install python@3.12` hoặc bản cài từ python.org. `./trendvn` tự chọn bản Python mới nhất có trên máy. Các công cụ còn lại chạy được với python3 hệ thống (3.9) |
| Trình duyệt | **Google Chrome** thật (Playwright điều khiển Chrome cài trên máy, không tải Chromium đóng gói) |
| Đĩa | ≥ 4 GB trống (image Docker ~2 GB; video tải về và dựng lớn dần, dọn định kỳ: [OPERATIONS.md](OPERATIONS.md)) |
| Mạng | Ra internet. Muốn nguồn Mỹ: một proxy/VPN cho IP Mỹ |
| Khóa | Gemini API key (do bạn tạo ở Google AI Studio) |

## 2. Cài đặt mới hoàn toàn

Trên máy nguồn, đóng gói bản sạch (không kèm bí mật, dữ liệu, phiên TikTok, môi trường Python):

```bash
./trendvn package        # tạo dist/trendvn-<phiên bản>.tar.gz + .sha256, sau khi tự kiểm tra
```

Chép sang máy mới (AirDrop, USB, scp), kiểm tra `shasum -a 256 -c trendvn-*.sha256` (Mac) / `sha256sum -c …` (Linux), giải nén rồi:

```bash
tar xzf trendvn-1.4.tar.gz && cd trendvn-1.4
./trendvn install
```

`install` chạy được nhiều lần, mỗi lần không phá dữ liệu đang có. Tham số: `--no-activate` (nạp workflow nhưng chưa bật lịch), `--no-service` (không cài dịch vụ nền cho agent; tự chạy `./trendvn agent run`).

Tám bước của `install` (mỗi bước dùng được riêng): kiểm tra điều kiện → `scripts/setup_env.py` (tạo `.env`, sinh bí mật một lần, chọn dải mạng Docker chưa dùng trong 172.20–172.31, không đổi khóa nào bạn đã đặt) → `./trendvn agent venv` → `./trendvn n8n build` → `./trendvn up` → `./trendvn n8n import` → `./trendvn n8n activate` → `./trendvn agent install`.

Sau đó làm 5 việc chỉ bạn làm được (khóa Gemini, đăng nhập TikTok, đặt đúng tài khoản đích, chờ có video rồi dry-run, bật tự đăng): xem phần cài đặt trong [README](../README.md).

## 3. Docker: có gì bên trong

| Thành phần | Chạy ở đâu | Ghi chú |
|---|---|---|
| `worker` | container, image `trendvn/worker:<phiên bản>` build từ `services/worker/` | Python chuẩn (không cần pip), ffmpeg, bảng điều khiển ở cổng 5681. Chạy bằng uid/gid của bạn, root filesystem chỉ đọc, bỏ mọi capability, `no-new-privileges`, `HEALTHCHECK` |
| `n8n` | container, image `docker.n8n.io/n8nio/n8n:<phiên bản ghim>` | Giao diện ở cổng 5680. Có healthcheck |
| `agent` | **trên máy, không trong Docker** | Cần Chrome thật, màn hình và phiên đăng nhập TikTok; nghe ở cổng 5682 chỉ trên địa chỉ cầu nối Docker (Linux) hoặc `127.0.0.1` (Mac) |

| Tài nguyên | Tên | Chứa gì |
|---|---|---|
| Mạng | `<project>_private` (bridge riêng, dải do `setup_env.py` chọn) | Chỉ hai container và agent thấy nhau |
| Volume | `<project>_n8n_data` | Tài khoản, credential, lịch sử chạy của n8n |
| Thư mục gắn vào | `./data/worker` → `/data` | SQLite, video, khóa Gemini — **thứ đáng sao lưu nhất** |
| Thư mục gắn vào | `./n8n/workflows` → `/import` (chỉ đọc) | Workflow do `build.py` sinh |
| Log | json-file, tự xoay vòng 5 × 10 MB mỗi dịch vụ | `./trendvn logs` |

Lệnh Docker thuần tương đương (khi bạn muốn tự tay; luôn chạy trong thư mục dự án, cần `.env`):

```bash
export TRENDVN_VERSION=$(cat VERSION)     # để image mang nhãn phiên bản; bỏ qua thì là 'dev'
docker compose build worker               # = ./trendvn build
docker compose up -d --wait               # = ./trendvn up (thêm --build để dựng lại)
docker compose ps                         # trạng thái + healthy
docker compose logs -f --tail 100 worker  # = ./trendvn logs worker -f
docker compose exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n list:workflow   # workflow trong n8n (= ./trendvn n8n status)
docker compose down                       # = ./trendvn down   (KHÔNG thêm -v: sẽ xóa volume n8n)
```

Hai bản trên một máy: đặt `COMPOSE_PROJECT_NAME`, `TRENDVN_N8N_PORT`, `TRENDVN_WORKER_PORT`, `TRENDVN_AGENT_PORT` khác nhau trong `.env` của bản thứ hai và cài với `--no-service`.

## 4. Đăng nhập n8n (và bảng điều khiển) từ máy khác

**Trả lời ngắn: được.** Mặc định cả hai chỉ mở trên chính máy chủ (`127.0.0.1`), vì n8n và bảng điều khiển chứa khả năng đăng bài lên kênh của bạn. Ba cách, theo thứ tự nên chọn:

### Cách A — Đường hầm SSH (khuyên dùng, không đổi cấu hình, không mở cổng)

Trên **máy khác** (laptop của bạn):

```bash
ssh -N -L 5680:127.0.0.1:5680 -L 5681:127.0.0.1:5681 <user>@<máy-chủ>
```

Để cửa sổ đó chạy, rồi mở **http://localhost:5680** (n8n) và **http://localhost:5681** (bảng điều khiển) ngay trên laptop. Không cần đổi gì trong `.env`.

### Cách B — VPN riêng (Tailscale, WireGuard)

Trên máy chủ, sửa `.env` (thay `100.64.0.5` bằng địa chỉ VPN của máy chủ):

```
TRENDVN_BIND=100.64.0.5
TRENDVN_N8N_URL=http://100.64.0.5:5680
TRENDVN_N8N_HOST=100.64.0.5
TRENDVN_UI_HOSTS=100.64.0.5:5681
TRENDVN_UI_PASSWORD=<mật-khẩu-dài-ít-nhất-12-ký-tự>
```

rồi `./trendvn up`. Các cổng chỉ nghe trên địa chỉ VPN, nên người ngoài VPN không thấy. Bảng điều khiển chỉ trả lời các `Host` nằm trong `TRENDVN_UI_HOSTS` (chống truy cập nhầm qua tên lạ).

### Cách C — Tên miền + HTTPS (chỉ khi thật cần)

Đặt reverse proxy (Caddy hoặc nginx) có TLS và **xác thực riêng** phía trước cổng 5680/5681, giữ `TRENDVN_BIND=127.0.0.1`, rồi:

```
TRENDVN_N8N_URL=https://n8n.ten-mien.com
TRENDVN_N8N_HOST=n8n.ten-mien.com
TRENDVN_N8N_PROTOCOL=https
TRENDVN_N8N_SECURE_COOKIE=true
TRENDVN_UI_HOSTS=dieukhien.ten-mien.com
TRENDVN_UI_PASSWORD=<mật-khẩu-dài-ít-nhất-12-ký-tự>
```

**Không** đặt `TRENDVN_BIND=0.0.0.0` rồi mở thẳng ra Internet. Bảng điều khiển chỉ mở không cần mật khẩu trên chính máy này; với bất kỳ `Host` nào khác trong `TRENDVN_UI_HOSTS` nó **bắt buộc** `TRENDVN_UI_PASSWORD` (trang đăng nhập, chặn đoán sai sau 5 lần). Không đặt mật khẩu thì các Host đó bị từ chối. Đường hầm SSH (cách A) không cần mật khẩu vì bạn vào bằng `localhost`.

### Bạn cần biết khi sửa workflow từ xa

- Lần đầu mở n8n, nó yêu cầu **tạo tài khoản chủ (owner)**: email và mật khẩu do bạn chọn. Tài khoản này lưu trong volume `<project>_n8n_data`; nó nằm trong bản sao lưu.
- Sửa và bấm chạy workflow từ xa **vẫn chạy trên máy chủ**: Chrome, phiên đăng nhập TikTok và video đều ở máy chủ. Bạn chỉ điều khiển từ xa.
- Workflow gọi `http://worker:8080` và `http://trendvn-agent:<cổng>`, hai tên chỉ tồn tại trong mạng Docker của dự án. Vì vậy **không cần và không nên tự đóng gói hay nhập workflow tay** vào n8n của máy khác: `./trendvn install` đã nạp sẵn đủ 6 workflow và thông tin xác thực trên máy mới ([N8N.md](N8N.md)).
- Không dán khóa `TRENDVN_TOKEN` vào workflow: nó nằm trong credential "TrendVN · Worker riêng" do `./trendvn n8n import` tạo.

## 5. Nguồn Mỹ: proxy hoặc VPN

TikTok và Instagram trả nội dung theo IP. Thêm vào `.env`:

```
TRENDVN_US_PROXY=http://user:pass@host:port       # cũng nhận socks5://
```

rồi `./trendvn agent restart`. Agent kiểm tra quốc gia của IP thoát trước mỗi lần quét; nếu không phải Mỹ, hai nguồn này bị bỏ qua và bảng điều khiển ghi rõ lý do. Chỉ trình duyệt thu thập dùng proxy; tải video về cũng đi qua proxy đó, còn trình đăng TikTok của bạn **không** dùng proxy.

## 6. Sao lưu, khôi phục, chuyển máy

```bash
./trendvn backup                       # data/backups/trendvn-<ngày-giờ>.tar.gz (0600): SQLite, khóa Gemini, thông báo, .env, dữ liệu n8n
./trendvn backup --with-session        # kèm phiên đăng nhập TikTok
./trendvn restore data/backups/<file>  # trên thư mục đã cài; hỏi xác nhận trước khi ghi đè
```

**Chuyển sang máy mới** (thứ tự này tránh hai máy cùng đăng vào một kênh):

```bash
# Máy CŨ
./trendvn n8n deactivate                 # tắt lịch trước, để hai máy không cùng đăng
./trendvn backup --with-session
./trendvn uninstall
# Máy MỚI
tar xzf trendvn-1.4.tar.gz && cd trendvn-1.4
./trendvn install --no-activate
./trendvn restore <bản sao lưu>          # dữ liệu, n8n, phiên TikTok; lịch tự động được để TẮT
./trendvn doctor
./trendvn tiktok login                   # phiên mang sang có thể bị TikTok hỏi lại
./trendvn tiktok dry-run
./trendvn n8n activate                   # bật lịch ở máy mới khi mọi thứ ổn
```

> **Chỉ một máy chạy tự động cho một tài khoản TikTok.** Hai máy cùng đăng vào một kênh sẽ đăng trùng vì không chia sẻ hàng đợi.

`N8N_ENCRYPTION_KEY` trong `.env` mã hóa thông tin trong n8n: mất khóa này thì credential đã lưu trong n8n không đọc được. Sao lưu `.env` cùng dữ liệu (`backup` đã làm việc này).

## 7. Tự khởi động cùng máy

- Container có `restart: unless-stopped`: tự lên khi Docker lên.
- Agent chạy dưới `systemd --user` (Linux) hoặc `launchd` (Mac). Linux: để nó chạy ngay khi máy khởi động, kể cả chưa có ai đăng nhập: `sudo loginctl enable-linger $USER`. Mac: chạy khi bạn đăng nhập.
- Agent cần Docker đã tạo mạng của dự án để nghe trên địa chỉ cầu nối; nếu lên trước Docker, nó tự thử lại mỗi 15 giây.

## 8. macOS và Windows

- **macOS:** `install` nhận biết macOS: tìm Chrome trong `/Applications`, cài agent bằng `launchd` (`~/Library/LaunchAgents/vn.trendvn.agent.plist`, chạy kèm `caffeinate` để Mac không tự ngủ khi đang làm việc). Docker Desktop chạy container trong một máy ảo nên không có địa chỉ cầu nối như Linux: `setup_env.py` tự đặt `TRENDVN_AGENT_BIND=127.0.0.1` và `TRENDVN_AGENT_HOSTREF=host-gateway` để n8n gọi được agent trên Mac. Hướng dẫn từng bước: [MAC.md](MAC.md). Đã chạy thật trên Linux: cài sạch từ bản đóng gói (bỏ bước dịch vụ nền), n8n gọi agent, sao lưu và khôi phục. Chỉ mới kiểm tra tĩnh: dịch vụ nền systemd/launchd (nội dung sinh ra hợp lệ, trỏ đúng file). Chưa chạy thử trên máy Mac thật: toàn bộ phần macOS (launchd, `host-gateway` của Docker Desktop, Python 3.10+ qua Homebrew).
- **Windows:** dùng WSL2 (Ubuntu) chạy toàn bộ như Linux, nhưng Chrome thật phải chạy trong WSL (cài `google-chrome` trong Ubuntu) và cần WSLg để hiện cửa sổ đăng nhập.

## 9. Cập nhật phiên bản

Giải nén bản mới **đè lên thư mục đang chạy** (bản đóng gói không chứa `.env` và `data/` nên chúng được giữ nguyên), rồi cập nhật:

```bash
cd ~/trendvn                                              # thư mục đang chạy
tar xzf ~/Downloads/trendvn-<phiên-bản-mới>.tar.gz --strip-components=1   # file của bản cũ mà bản mới không còn dùng thì tự xóa nếu muốn
./trendvn update                  # build lại image, sinh + nạp lại workflow (lịch giữ nguyên), cập nhật gói Python của agent, khởi động lại, doctor
./trendvn tiktok dry-run          # luôn thử lại sau khi cập nhật, vì TikTok có thể đổi giao diện
```

Nếu `doctor` báo "Worker đúng phiên bản của mã" lỗi: container còn chạy image cũ, chạy `./trendvn update`.

## 10. Gỡ cài đặt

```bash
./trendvn uninstall           # dừng dịch vụ và container, GIỮ dữ liệu
./trendvn uninstall --purge   # xóa cả dữ liệu, phiên TikTok, n8n (hỏi xác nhận, không hoàn tác)
```

## 11. Chuyển từ bản 1.2 (thư mục cũ) sang bản mới (1.3 trở lên) trên cùng một máy

Từ bản 1.3 đổi bố cục thư mục (bảng đường dẫn cũ → mới nằm ở [CHANGELOG](../CHANGELOG.md)). Docker nhận diện một hệ thống bằng **tên project** (`trendvn`), không phải bằng thư mục,
nên bản 1.2 đang chạy và bản mới giải nén dùng **cùng tên**: `./trendvn` từ chối dừng hay ghi đè container của thư mục kia (`guard_project`). Chuyển bằng một lệnh, chạy trong thư mục **mới**
(vừa giải nén, chưa cài):

```bash
tar xzf trendvn-1.4.tar.gz && cd trendvn-1.4
./trendvn migrate <thư-mục-1.2>
```

`migrate` kiểm tra hết mọi thứ **trước** khi dừng bất cứ thứ gì (thư mục cũ đúng là bản 1.2, không có việc nào đang chạy, thư mục mới còn trống), rồi: sao lưu bằng `backup.sh` cũ → dừng agent và container cũ (mất dịch vụ vài phút) → chép `.env`, `runtime/` → `data/worker`, `agent_data/` → `data/agent` (giữ phiên đăng nhập TikTok, bỏ bộ nhớ đệm Chrome) → `./trendvn install --no-activate` → đối chiếu số video theo trạng thái. Trạng thái bạn đang để **giữ nguyên**: lịch n8n đang bật vẫn bật, đang tắt vẫn tắt, "Tự đăng" và mọi cài đặt không đổi. Thư mục 1.2 được giữ nguyên làm dự phòng; nếu có bước nào hỏng, `migrate` in sẵn các lệnh để quay về thư mục cũ.

Vì sao dùng đúng `.env` cũ: `docker compose down` giữ lại volume n8n, và n8n từ chối khởi động nếu khóa mã hóa khác khóa đã tạo ra volume đó. (Đi bằng tay cũng được: chép `.env` cũ vào thư mục mới **trước khi** `./trendvn install`, rồi `./trendvn restore` bản sao lưu.)

Muốn chạy hai bản **song song** để so sánh: trong `.env` của bản mới đặt `COMPOSE_PROJECT_NAME`, `TRENDVN_N8N_PORT`, `TRENDVN_WORKER_PORT`, `TRENDVN_AGENT_PORT` khác bản cũ, và cài bằng `--no-service` (chỉ một agent có thể giữ dịch vụ nền `trendvn-agent`). Đừng để hai bản cùng bật lịch đăng vào một kênh TikTok.
