# Cài TrendVN trên máy Mac ở nhà (30–60 phút cho Mac mới toanh; 10–15 phút nếu đã có Docker, Python, Chrome)

## 1. Chuẩn bị (làm một lần)

| Cần | Cài |
|---|---|
| **Docker Desktop** | https://www.docker.com/products/docker-desktop/ → mở lên, đợi biểu tượng cá voi đứng yên |
| **Google Chrome** | https://www.google.com/chrome/ |
| **Python 3.10 trở lên** | macOS chỉ kèm Python 3.9 (sau khi cài "Command Line Tools": gõ `xcode-select --install`), **quá cũ** cho agent. Cài thêm: `brew install python@3.12` hoặc tải bản cài tại https://www.python.org/downloads/macos/ . Kiểm tra: `python3.12 --version` |

Có Homebrew thì gọn hơn: `brew install python@3.12` và cài Docker Desktop, Chrome (tên gói cask của Docker có thể là `docker-desktop` hoặc `docker` tùy phiên bản Homebrew). Mở Docker Desktop một lần và bật **Start Docker Desktop when you sign in** (Settings → General) để sau khi khởi động lại Mac, container tự lên.

Google Chrome phải nằm trong thư mục **/Applications** (cài mặc định là vậy).

## 2. Chép dự án sang Mac

Trên **máy đang chạy**, đóng gói (không kèm mật khẩu, khóa hay dữ liệu):

```bash
./trendvn package        # tạo dist/trendvn-1.4.tar.gz và file .sha256
```

Chép file đó sang Mac bằng AirDrop, USB hoặc `scp`, rồi nhấp đúp để giải nén thành thư mục `trendvn-1.4`. **Hãy chuyển thư mục đó vào `~/trendvn`** (thư mục nhà của bạn), đừng để trong Downloads, Documents hay Desktop: macOS hạn chế các chương trình nền truy cập những thư mục này nên agent có thể không chạy được.

## 3. Cài

Mở Terminal:

```bash
cd ~/trendvn      # thư mục bạn vừa chuyển vào
./trendvn install
```

Hoặc nhấp đúp `macos/Cai-dat.command`. Nếu macOS chặn (file tải bằng trình duyệt hoặc AirDrop bị gắn cờ cách ly): Cài đặt hệ thống → Quyền riêng tư & Bảo mật → **Vẫn mở**, hoặc gỡ cờ cách ly cho cả thư mục bằng `xattr -dr com.apple.quarantine ~/trendvn` rồi nhấp đúp lại (cách này cũng áp dụng cho các file `.command` khác). Dùng Terminal với `./trendvn install` thì không bị chặn.

Script tự kiểm tra máy, dựng container, sinh và nạp 6 workflow vào n8n, bật lịch và cài dịch vụ nền. Cuối cùng nó in bảng chẩn đoán: các dòng **✓** là ổn; các dòng vàng **!** (chưa có khóa Gemini, chưa đăng nhập TikTok, Tự đăng đang tắt...) là bình thường ở thời điểm này và chính là 5 việc ở mục 4. Lần đầu build image mất vài phút.

## 4. Năm việc chỉ bạn làm được

1. `./trendvn open` (hoặc http://localhost:5681) → **Thêm → Cài đặt**: dán khóa Gemini (tạo ở https://aistudio.google.com/apikey), bật "Xử lý video".
2. Đăng nhập TikTok một lần (bạn tự nhập trong cửa sổ Chrome hiện ra): `./trendvn tiktok login` (hoặc nhấp đúp `macos/Dang-nhap-TikTok.command`).
3. **Thêm → Cài đặt → Lịch đăng → "Tài khoản TikTok đích"**: đổi thành đúng kênh bạn vừa đăng nhập (mặc định là một tài khoản mẫu; nếu sai, mọi bài đăng sẽ không xác nhận được và việc đăng tự dừng).
4. Chờ có video để thử. Lần quét đầu chỉ **ghi mốc**, chưa tải gì; video chỉ xuất hiện từ lần quét thứ hai. Bấm **▶ Bắt đầu** ở Tổng quan, bấm lại sau vài giờ (hoặc chờ lịch 3 giờ) cho tới khi tab **Đăng bài** có video. Rồi chạy thử, **không đăng thật**; một cửa sổ Chrome thật sẽ hiện lên khoảng 1–2 phút, đừng đóng giữa chừng:
   ```bash
   ./trendvn tiktok dry-run
   ```
   Kết quả `"status": "idle"` nghĩa là chưa có video dựng xong (không phải lỗi). Nếu TikTok hiện hình xác minh, tự giải trong cửa sổ đó (không giải thay được). Xem ảnh chụp: `data/worker/exports/shot_*.png` (tên in trong kết quả; nút "Xem thử" trên tab Đăng bài cũng hiện ảnh).
5. Vào bảng điều khiển bật **"Tự đăng"**. Mẹo: vài bài đầu đặt Cài đặt → Chế độ hiển thị = "Chỉ mình tôi" để xem thử trong TikTok Studio, ổn rồi đổi sang "Mọi người".

## Dùng hằng ngày

```bash
./trendvn status          # mọi thứ có chạy không
./trendvn logs -f         # xem log trực tiếp (worker + n8n); ./trendvn logs agent -f cho agent
./trendvn restart         # khởi động lại
./trendvn doctor          # chẩn đoán, mỗi lỗi kèm cách sửa
```

Nhấp đúp `macos/Mo-bang-dieu-khien.command` để mở bảng điều khiển. Lưu ý: `./trendvn down` chỉ dừng n8n và worker; **agent (Chrome) vẫn chạy**, dừng nó bằng `./trendvn agent stop`. Sau khi khởi động lại Mac: đăng nhập tài khoản macOS, để Docker Desktop tự chạy (đã bật ở mục 1), container và agent tự lên; kiểm tra bằng `./trendvn status`.

Danh sách đầy đủ: [COMMANDS.md](COMMANDS.md).

## n8n có cần đăng nhập hay đóng gói gì thêm không?

**Không.** n8n ở đây chạy ngay trên Mac của bạn, không phải tài khoản trên mạng. `./trendvn install` đã sinh và nạp sẵn đủ 6 workflow cùng thông tin xác thực ([N8N.md](N8N.md)). Lần đầu mở **http://localhost:5680**, n8n bắt bạn tạo tài khoản chủ mới (email và mật khẩu tùy chọn). Muốn giữ nguyên tài khoản, lịch sử và cài đặt của máy cũ thì làm thêm: `./trendvn backup` ở máy cũ, chép file trong `data/backups/` sang Mac, cài xong chạy `./trendvn restore data/backups/<file>`.

## Lưu ý riêng cho Mac

- **Mac phải bật và không ngủ** thì lịch mới chạy. Cắm sạc, đặt "Ngăn Mac tự ngủ khi cắm sạc" trong Cài đặt hệ thống; gập màn hình laptop sẽ làm máy ngủ. Dịch vụ nền đã dùng `caffeinate` để máy không tự ngủ khi đang làm việc.
- **Chỉ một máy chạy tự động cho một kênh TikTok.** Tắt máy cũ (`./trendvn uninstall`) trước khi bật máy mới.
- **TikTok và Instagram Mỹ** cần IP Mỹ. Ở nhà Việt Nam thì hai nguồn này bị bỏ qua (Douyin và Kuaishou vẫn chạy). Có proxy/VPN Mỹ thì thêm vào `.env`: `TRENDVN_US_PROXY=http://user:pass@host:port`, rồi `./trendvn agent restart`.
- **Gỡ hẳn:** `./trendvn uninstall` (giữ dữ liệu) hoặc `./trendvn uninstall --purge`.

## Nếu gặp lỗi

| Lỗi | Cách xử lý |
|---|---|
| "Docker Desktop chưa chạy" | Mở ứng dụng Docker, đợi khởi động xong, chạy lại |
| "Chưa có Google Chrome" | Cài Chrome vào thư mục Applications |
| Mục "Agent trình duyệt chạy" đỏ | `./trendvn agent status`, rồi `./trendvn agent logs` (lỗi khởi động nằm ở `data/agent/launchd.log`) |
| n8n không gọi được agent | Kiểm tra dòng `TRENDVN_AGENT_HOSTREF=host-gateway` và `TRENDVN_AGENT_BIND=127.0.0.1` trong `.env` |
| macOS chặn file `.command` | Quyền riêng tư & Bảo mật → Vẫn mở, hoặc `xattr -dr com.apple.quarantine ~/trendvn`; hoặc dùng Terminal với `./trendvn …` |
| Cài dừng ở bước Python ("Cần Python 3.10") | `brew install python@3.12` rồi chạy lại `./trendvn install` |

> Ghi chú trung thực: đã chạy thật trên Linux: cài sạch từ bản đóng gói (bỏ bước dịch vụ nền), n8n gọi agent, sao lưu và khôi phục; đăng thật lên TikTok và phân tích bằng Gemini cũng đã chạy thật (ở bản trước). Dịch vụ nền systemd/launchd mới được kiểm tra tĩnh (nội dung sinh ra hợp lệ và trỏ đúng file). **Toàn bộ phần macOS chưa được chạy thử trên máy Mac thật** (launchd, `host-gateway` của Docker Desktop, Python 3.10+ qua Homebrew, cờ cách ly file); các script chỉ dùng cú pháp chạy được trên bash 3.2/BSD của macOS (có phép kiểm tra tự động). Nếu có gì lạ, gửi kết quả `./trendvn doctor` để sửa nhanh.
