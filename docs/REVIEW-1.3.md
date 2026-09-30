# Nhật ký rà soát phiên bản 1.3 (đóng gói để bàn giao)

Bản 1.3 không đổi hành vi hệ thống; nó đổi cách bố trí, đóng gói và vận hành. Vì vậy phần rà soát tập trung vào: cài đặt từ bản đóng gói có chạy đúng không,
mọi lệnh có làm đúng điều tài liệu nói không, và có gì có thể làm mất dữ liệu hoặc ảnh hưởng hệ thống khác trên cùng máy không.
Ba vòng: (1) tự rà tĩnh, (2) tự kiểm thử động trên bản cài sạch, (3) ba người rà soát độc lập, mỗi người một góc nhìn, chỉ đọc mã.

## Vòng 1 — Rà tĩnh (tự động hóa thành `./trendvn test lint`)

Cách làm: những gì rà bằng tay một lần thì dễ hỏng lại, nên mỗi phát hiện được biến thành một phép kiểm tra chạy mỗi lần.

| Kiểm tra | Bắt được gì |
|---|---|
| `n8n/build.py --check` | File workflow trong repo lệch mã sinh |
| Cú pháp Python và shell, mẫu cấm cho bash 3.2/BSD (macOS) | `declare -A`, `mapfile`, `sed -i`, `readlink -f`... |
| `shellcheck` (mức style) | Lỗi trích dẫn, biến chưa đặt, `cd` không kiểm tra |
| Mẫu dịch vụ nền trỏ tới file có thật | **Lỗi thật:** sau khi đổi thư mục, mẫu systemd/launchd vẫn trỏ tới `agent/server.py` và `agent_data/` cũ, nên dịch vụ nền sẽ không bao giờ chạy được. Bản cài thử dùng `--no-service` nên không phát hiện; chỉ lộ ra khi in mẫu ra xem. Nay có kiểm tra (đã thử phá cố ý để chắc kiểm tra bắt được) |
| `scripts/doclint.py` | Lệnh `./trendvn …` trong tài liệu không tồn tại (bắt được `agent venv` có trong mã nhưng thiếu trong trợ giúp), liên kết tương đối hỏng, tàn dư đường dẫn/tên script của bố cục cũ |

Sửa trong vòng này ngoài các mục trên: 5 chỗ tài liệu còn ghi lệnh/đường dẫn cũ, thông báo lỗi trong giao diện và agent trỏ tới `./trendvn tiktok trust`, kiểm tra phiên bản `docker compose` ≥ 2.20 khi cài, từ chối cài vào đường dẫn có dấu cách hoặc ký tự đặc biệt (dịch vụ nền không xử lý được), worker ghi log có ích (khởi động, từng lệnh gọi API, lỗi kèm traceback; không ghi token, cookie, thân yêu cầu, chuỗi truy vấn).

## Vòng 2 — Kiểm thử động trên bản cài sạch

Cách làm: `./trendvn package` → giải nén vào thư mục trống → project Docker và cổng riêng → cài thật. Lặp lại sau mỗi lần sửa.

| Việc | Kết quả |
|---|---|
| `install` từ bản đóng gói (build image, sinh + nạp workflow, bật lịch) | thành công, 2 container `healthy` |
| Chạy `install` lần hai | thành công, không phá dữ liệu |
| Container bị siết (root filesystem chỉ đọc, bỏ mọi capability, `no-new-privileges`, uid người dùng) | worker vẫn `healthy`, bảng điều khiển đủ 6 tab |
| `n8n deactivate / activate 01 / import / export / status` | đúng; **nạp lại không làm tắt lịch đang bật** |
| `agent start / status / logs / stop` (tiến trình nền) | đúng |
| `backup --keep`, `restore` bản sao lưu do chính nó tạo | đúng |
| `restore` một bản sao lưu của **1.2** thật (dữ liệu và n8n của hệ thống thật) | đúng: dữ liệu đọc được, bảng điều khiển hiện đúng hàng đợi, khóa mạng của máy giữ nguyên |
| `restart`, `down`, `up`, `update`, `uninstall`, `uninstall --purge` | đúng; `--purge` xóa sạch `data/`, `.venv`, volume |
| `test container`: toàn bộ test trong image có ffmpeg + dựng video thật | 159/159 |
| `test e2e`: Chrome thật, 7 kích thước × 6 tab, mọi luồng bấm nút | 76/76 |

### Sự cố trong lúc kiểm thử: tôi làm dừng nhầm hệ thống thật trong vài phút

Bước `restore` bản sao lưu 1.2 lần đầu chạy trong thư mục thử với cấu hình **gộp sai**: `.env` lấy từ bản sao lưu nên mất `COMPOSE_PROJECT_NAME` của thư mục thử,
Docker quay về tên mặc định `trendvn` — trùng tên với hệ thống 1.2 đang chạy thật. Lệnh `docker compose down` rồi khôi phục volume n8n đã chạy lên **hệ thống thật**:
hai container bị xóa (khoảng 3 phút), volume n8n bị ghi đè bằng bản sao lưu lúc 10:45. Dữ liệu worker (`runtime/`, hàng đợi, video, khóa) nằm ngoài volume nên không bị đụng.
Khắc phục ngay: `docker compose up -d` ở thư mục 1.2 và nạp lại 6 workflow; lịch tự động vốn đang tắt nên không mất bài, không đăng nhầm.

Sửa tận gốc (đều có kiểm thử, đã thử với một project giả `guardtest`, không đụng hệ thống thật):
1. **`guard_project`**: mọi lệnh làm thay đổi (`up`, `down`, `restart`, `update`, `backup`, `restore`, `uninstall`, `n8n import/activate/deactivate`) từ chối chạy nếu project Docker này đang chạy từ **thư mục khác**, và nói rõ cách chuyển hoặc chạy song song. Bỏ qua được bằng `TRENDVN_ALLOW_TAKEOVER=1`.
2. **Gộp `.env` khi khôi phục** đổi thành: giá trị của máy hiện tại luôn thắng; bản sao lưu chỉ đóng góp hai khóa bí mật bắt buộc (`N8N_ENCRYPTION_KEY`, `TRENDVN_TOKEN`) và các tùy chọn máy này chưa đặt.
3. Trước khi ghi đè, `restore` in rõ project và volume sẽ bị ghi đè.
4. Mọi thử nghiệm phá hủy về sau đặt tên project riêng, và so sánh mã container của hệ thống thật trước/sau (không đổi).

## Vòng 3 — Ba người rà soát độc lập

Ba tác tử chỉ đọc mã (không được chạy Docker hay dịch vụ), mỗi người một góc: (A) shell/CLI và macOS, (B) Docker, n8n, đóng gói, bảo mật, (C) tài liệu và hành trình của người dùng mới trên Mac.
Họ báo tổng cộng 38 phát hiện thật (một vài mục trùng nhau; không tính các mục "đã đúng"). Tất cả được xử lý, hoặc ghi rõ lý do nếu không sửa. Đáng chú ý nhất, theo mức ảnh hưởng tới lần cài trên Mac của bạn:

| Phát hiện | Vì sao quan trọng | Xử lý |
|---|---|---|
| **Python 3.9 của macOS không cài được agent**: `playwright` và `yt-dlp` đều yêu cầu Python ≥ 3.10 (kiểm tra trên PyPI), còn tài liệu và `install.sh` chỉ đòi 3.9 | Cài trên Mac mới sẽ dừng ở bước 3 với lỗi pip khó hiểu (lỗi này có từ bản 1.2) | `install` đòi Python 3.10+ cho agent, tự chọn bản mới nhất trên máy (`python3.13` … `python3.10`, Homebrew), hướng dẫn `brew install python@3.12`; `.venv` dựng bằng Python cũ được dựng lại; `doctor` kiểm tra; lint kiểm tra công cụ máy chủ vẫn chạy được trên cú pháp 3.9 |
| **Chuyển từ 1.2 sẽ làm n8n không khởi động**: cài mới sinh khóa mã hóa mới, còn volume n8n cũ chỉ đọc được bằng khóa cũ (đã thử thật: "Mismatching encryption keys") | Mất n8n sau khi chuyển thư mục | `install` từ chối sinh khóa mới khi còn volume cũ; hướng dẫn chuyển đã sửa (chép `.env` cũ trước) |
| **Cài dịch vụ nền hỏng trên Linux dùng Wayland** (`sed` gặp xuống dòng, để lại file dịch vụ rỗng) | Cài dừng ở bước 8 | Dịch vụ nền sinh bằng Python (`scripts/render_service.py`), có kiểm tra tự động, thử với Wayland/X11/không có/ký tự lạ |
| **Kiểm tra Chrome sai**: nhận Chromium/snap và `~/Applications`, trong khi Playwright chỉ dùng Google Chrome ở vị trí chuẩn | Cài "thành công" nhưng mọi việc trình duyệt hỏng | `install` và `doctor` kiểm tra đúng chỗ; `doctor` mở thử Chrome bằng Playwright |
| **Dry-run của người mới không có gì để chạy** (lần quét đầu chỉ ghi mốc) và **ảnh chụp không nằm ở chỗ tài liệu nói** | Người mới tưởng hỏng | Tài liệu và thông báo cuối `install` viết lại thành 5 việc, có bước đặt "Tài khoản TikTok đích" |
| **Chuyển máy có thể đăng trùng**: dữ liệu n8n khôi phục nhớ lịch đang bật | Hai máy cùng đăng một kênh | `restore` tắt lịch trong dữ liệu n8n **trước khi** n8n khởi động; quy trình chuyển máy sắp lại thứ tự |
| `restore` gộp `.env` trước khi kiểm tra bản sao lưu, thông báo "chưa thay đổi gì" sai | `.env` mang khóa lạ, n8n không lên | Kiểm tra bản sao lưu trước; chỉ lấy khóa bí mật khi bản sao lưu có dữ liệu n8n đi kèm |
| `docker compose cp` tạo file root 0600 mà người dùng n8n không đọc được; token có thể nằm lại trong container | Nạp credential hỏng trên Mac (uid 501); lộ token | Token đi qua stdin vào file 0600 do chính người dùng n8n tạo, xóa sau khi dùng; đã chạy workflow 00 thật để chứng minh credential dùng được |
| `hmac.compare_digest` ném lỗi với ký tự có dấu | Mật khẩu tiếng Việt không đăng nhập được; header lạ gây 500 | So sánh theo bytes ở worker và agent, có test (đã chứng minh test hỏng khi hoàn nguyên bản sửa) |
| `cp .env.example .env` khiến bí mật bị coi là "đã có" (chú thích cuối dòng bị đọc thành giá trị); các bộ đọc `.env` mỗi nơi một kiểu | Khóa rỗng, n8n và agent không chạy | Một bộ đọc chung `scripts/envfile.py` theo quy tắc của Compose; dòng bí mật trong ví dụ để dạng chú thích; có test |
| `--purge` xóa cả `data/backups`; hỏi xác nhận sau khi đã gỡ dịch vụ | Mất bản sao lưu; gỡ dở dang | Hỏi trước, giữ `data/backups` và `.env` |
| `logs agent` không hiện lỗi khi khởi động (file chưa tồn tại) | Không thấy nguyên nhân agent chết | Hiện mọi file log có, hoặc journal của systemd |
| Sao lưu chép volume n8n lúc n8n đang chạy; file tgz dở dang vẫn bị đóng gói | Bản sao lưu n8n có thể hỏng | Dừng n8n vài giây khi chép, luôn bật lại; xóa file dở; `restore` kiểm tra trước khi xóa |
| `doctor` chỉ kiểm tra agent từ máy chủ | Tường lửa chặn container tới agent mà vẫn báo xanh | Thêm kiểm tra từ bên trong container và cách mở cổng cho ufw |
| macOS không cho dịch vụ nền đọc Documents/Desktop/Downloads; đường dẫn có dấu cách/ký tự đặc biệt làm hỏng file dịch vụ | Agent không chạy sau khi cài | `install` từ chối và chỉ chuyển vào `~/trendvn` |
| Tệp kiểu `.env.bak` có thể lọt vào bản đóng gói; bản đóng gói không tái tạo được | Rò bí mật; khó đối chiếu | Loại mọi `.env*` trừ `.env.example`; đóng gói xác định (cùng mã cho cùng sha256) |
| Tài liệu: thời gian cài 15 phút (thực tế 30–60 phút), lời khuyên Gatekeeper cũ (macOS 15+), `brew` cask đổi tên, lệnh n8n thủ công thiếu biến, cron thiếu PATH, số phút chờ sai (15 → 45), tên workflow, lời khẳng định "kiểm chứng trọn vẹn" quá lời | Người dùng mới bị kẹt hoặc hiểu sai | Sửa từng mục; phần "chưa kiểm chứng trên Mac" viết lại chính xác |

Không sửa (ghi nhận): `pick_subnet` chỉ nhìn mạng Docker chứ không nhìn route của VPN (trùng dải chỉ hiện ra như một lỗi Docker rõ ràng khi `up`; có thể đặt `TRENDVN_SUBNET` thủ công).

## Kết quả cuối (trên bản đóng gói cuối cùng, cài vào thư mục trống với project và cổng riêng)

| Kiểm tra | Kết quả |
|---|---|
| `./trendvn test lint` (workflow khớp mã, Python/shell, bash 3.2, mẫu dịch vụ nền, tài liệu khớp mã) | OK |
| Bộ test trên máy / trong image Docker có ffmpeg / dựng video thật | 167 / 167 / đạt |
| Chrome thật, 7 kích thước × 6 tab, mọi luồng nút | 76/76 |
| `install` từ bản đóng gói, bật lịch, workflow 00 chạy thật với credential vừa nạp | thành công |
| `doctor`: 15 mục xanh (gồm gọi agent từ container, Python 3.10, mở thử Chrome) | đạt; mục vàng còn lại là việc của người dùng |
| `backup` → `restore`: lịch tự động được tắt trước khi n8n lên | đúng |
| `export`, `update`, `uninstall`, `uninstall --purge` | đúng |
| Container: root filesystem chỉ đọc, bỏ mọi capability, `no-new-privileges`, init | đúng khi chạy thật |
| Hệ thống thật (1.2) đang chạy: mã container trước và sau mọi bước thử | không đổi |
| Bản đóng gói tạo hai lần | cùng sha256 |

## Chưa kiểm chứng, nói thẳng

- **macOS thật:** launchd, `host-gateway` của Docker Desktop, Python 3.10+ qua Homebrew, cờ cách ly file, đường dẫn Chrome. Script chỉ dùng cú pháp bash 3.2/BSD (có kiểm tra tự động) nhưng chưa chạy trên Mac.
- **Dịch vụ nền systemd/launchd thật:** chỉ kiểm tra nội dung sinh ra và đường dẫn; chưa cài thật vì sẽ ghi đè dịch vụ agent của hệ thống đang chạy.
- **Chuyển hệ thống thật từ 1.2 sang 1.3:** quy trình ở `docs/DEPLOY.md` mục 11 đã được thử từng phần (khôi phục bản sao lưu 1.2 thật vào bản cài sạch, chặn khóa n8n lệch) nhưng chưa chạy trọn vẹn trên chính hệ thống đang chạy.
- Bản 1.3 chưa được chạy dài ngày với lịch thật; TikTok có thể hiện hình xác minh bất kỳ lúc nào (hệ thống dừng đăng và báo, không vượt).

## Vòng 4 — Chuyển hệ thống đang chạy sang thư mục mới

Yêu cầu tiếp theo là chạy lại mọi thứ từ thư mục mới. Việc này phải dừng hệ thống 1.2 đang chạy và thay dịch vụ agent của máy, và **trình phân quyền tự động đã từ chối** lệnh dừng đó khi tôi thử chạy trực tiếp; vì vậy hệ thống thật chưa được đụng tới. Thay vào đó:

1. Chạy `./trendvn test all` ngay trong thư mục mới: lint, 167 test trên máy, 167 test trong image Docker, dựng video thật, 76 kiểm tra Chrome thật: **đạt hết**.
2. Viết `./trendvn migrate <thư-mục-1.2>` (một lệnh, có đường lui) và **diễn tập** nó trên một bản sao cô lập của hệ thống 1.2 (project Docker và cổng riêng, dữ liệu thật lấy từ bản sao lưu, một workflow đang bật). Kết quả (lần diễn tập cuối): sao lưu, dừng bản cũ, chép dữ liệu (bỏ bộ nhớ đệm, giữ hồ sơ), cài, đối chiếu **khớp từng trạng thái** (19 baseline, 35 candidate, 3 queued, 1 ready), hai workflow đang bật (01 và 03) vẫn bật, credential n8n dùng được (workflow 00 chạy thành công), khóa bí mật giữ nguyên. Hệ thống thật trước và sau: mã container không đổi, file dịch vụ agent không đổi.
3. **Diễn tập lần đầu thất bại, và đó là điều diễn tập để bắt:** máy này có `/usr/bin/python3.12` nhưng thiếu gói `venv`, nên bước tạo môi trường Python của agent lỗi **sau khi bản cũ đã bị dừng** (đường lui in ra đúng nhưng vẫn là mất dịch vụ). Đã sửa hai chỗ: chọn Python phải kiểm tra được cả `venv` (ưu tiên Python hệ thống, chỉ dùng Python của conda khi không còn lựa chọn nào khác), và `migrate` chạy toàn bộ kiểm tra điều kiện của máy (Docker, Compose, Python, Chrome) **trước** khi dừng bất cứ thứ gì. Diễn tập lại trên bản cuối: đạt.
4. Diễn tập cố ý dùng `--no-service`, nên phần thay dịch vụ nền systemd/launchd của `migrate` **chưa được chạy thật**: mã dừng dịch vụ chỉ chạm dịch vụ có `WorkingDirectory` đúng bằng thư mục cũ; việc cài dịch vụ mới dùng lại `scripts/agent.sh install` đã kiểm tra nội dung sinh ra.

