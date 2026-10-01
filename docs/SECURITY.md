# Bảo mật, quyền riêng tư và rủi ro cần biết

## 1. Rủi ro lớn nhất không nằm ở phần mềm

**Bản quyền và tài khoản.** Hệ thống lấy video do người khác tạo và đăng lại trên kênh của bạn. Không có bước xin phép tác giả, và không phần mềm nào xác nhận được bản quyền hay quyền sử dụng. Hậu quả có thể gặp: video bị gỡ, gậy bản quyền, giảm phân phối, khóa kênh; với video có nhạc thương mại (nhóm dễ bị nhất), nhạc có thể bị TikTok tắt tiếng hoặc chặn. Việc đăng lại còn phụ thuộc điều khoản của từng nền tảng nguồn và luật nơi bạn ở. Bạn chịu trách nhiệm về nội dung đăng. Gợi ý giảm rủi ro:

- Bật "Duyệt tay trước khi đăng" trong thời gian đầu và xem từng video.
- Ưu tiên video có âm nhạc gốc của chính người làm hoặc giải trí không dùng nhạc thương mại; hạ "Số bài mỗi ngày" xuống thấp.
- Giữ nguyên quy tắc "Cần duyệt" cho nội dung nhạy cảm/lệch chủ đề (mặc định đã bật).

**Cách làm dựa trên trình duyệt** (không API) phụ thuộc giao diện các trang; các nền tảng có thể đổi giao diện hoặc chặn tự động hóa. Hệ thống được thiết kế để khi gặp bất thường thì *dừng và báo*, không cố vượt.

## 2. Những gì hệ thống tự cấm

| Hành vi | Cách đảm bảo |
|---|---|
| Nhập mật khẩu thay bạn | Không có mã nào làm việc này; đăng nhập chỉ qua cửa sổ Chrome bạn tự thao tác (`./trendvn tiktok login`) |
| Giấu việc tự động hóa với trang web | Không dùng: không tắt cờ `AutomationControlled`, không sửa User-Agent, không giả lập thao tác người. Trình duyệt tự khai đúng là Chrome do chương trình điều khiển |
| Vượt CAPTCHA/xác minh | `looks_blocked` (thu thập) và `has_challenge` (trình đăng) phát hiện, báo lỗi và **tạm dừng đăng** cho tới khi chính bạn giải (`./trendvn tiktok trust`); không có mã giải hay né |
| Gắn nhãn nhầm nguồn Mỹ | Từ chối quét TikTok/Instagram nếu IP thoát ≠ Mỹ (`exit_country`); `ingest` cũng từ chối `country` không khớp nền tảng |
| Đăng khi không chắc | `publish_unknown` chặn mọi lần đăng sau đó; không tự thử lại bài đã bấm Đăng |
| Đăng ngoài luật | Lịch tự động: công tắc, giờ vàng, giới hạn ngày, giãn cách đều kiểm tra ở worker trong một giao dịch. **Đăng thủ công** (nút Đăng ngay) bỏ qua các luật đó vì bạn đã bấm, nhưng vẫn bị chặn khi có một bài đang đăng, có bài chưa xác nhận, hoặc TikTok đang đòi xác minh; mỗi lần bấm chỉ đăng đúng video đã chọn (bấm đúp không đăng hai lần) |
| Đăng file bị đổi | Hash SHA-256 của `final.mp4` phải khớp lúc dựng |
| Tin lời trong video | Prompt coi video là dữ liệu không đáng tin; đầu ra Gemini bị kiểm tra cứng lại |

## 3. Bề mặt tấn công và biện pháp

| Bề mặt | Biện pháp |
|---|---|
| **Cổng dịch vụ** | Mặc định chỉ `127.0.0.1`. Agent chỉ nghe trên địa chỉ cầu nối Docker của dự án, không lộ ra LAN |
| **API worker và agent** | Bearer token 256-bit (`TRENDVN_TOKEN`), so sánh thời gian hằng (`hmac.compare_digest`) |
| **Bảng điều khiển** | Mở không mật khẩu chỉ trên chính máy này; mọi `Host` khác trong `TRENDVN_UI_HOSTS` bắt buộc `TRENDVN_UI_PASSWORD` (cookie phiên HttpOnly SameSite=Strict, khóa 1 phút sau 5 lần sai), không đặt mật khẩu thì bị từ chối. Chỉ trả lời `Host` trong danh sách cho phép; mọi form kiểm tra `Origin` và token CSRF; tiêu đề CSP, `X-Frame-Options: DENY`, `nosniff`; mọi giá trị hiển thị đều được escape (có test chống chèn mã) |
| **Phát video xem trước** | Chỉ đường dẫn nằm trong `data/worker/`, id phải là 32 ký tự hex, hỗ trợ Range, chỉ từ giao diện nội bộ |
| **Cài đặt** | Mỗi khóa cho phép đổi có kiểu và khoảng giá trị chặt; khóa lạ bị từ chối (`validate_settings`) |
| **Tải video** | Chỉ HTTPS, chỉ tên miền CDN của chính nền tảng (`CDN_SUFFIXES`), giới hạn 250 MB, phải là MP4 thật (kiểm tra `ftyp`), ghi qua file `.part` rồi đổi tên |
| **Đường dẫn file** | `attach` chỉ nhận tên file an toàn trong `inbox/`; chống `..` |
| **Thông báo** | Webhook/ntfy chỉ nhận `https`, từ chối địa chỉ nội bộ/riêng tư (chống SSRF); bí mật lưu `data/worker/notify.json` mode 0600, không bao giờ trả về qua API |
| **Khóa Gemini** | `data/worker/gemini.key` mode 0600; không ghi log, không gửi vào n8n; khóa chỉ đi trong header gửi tới Google. Khi lỗi, chỉ hiển thị dòng `message` do Google trả về (không bao giờ chứa khóa) |
| **Nội dung đầu vào (n8n webhook 10)** | Bắt buộc xác thực; JSON không thể ra lệnh đăng: chỉ đưa video vào hàng đợi sau khi qua mọi kiểm tra |
| **n8n** | `N8N_ENCRYPTION_KEY` riêng cho dự án, tắt telemetry, tài khoản chủ do bạn tạo, workflow xuất không chứa bí mật |
| **Cô lập** | n8n, volume, mạng, container, thông tin xác thực đều riêng, không đọc gì từ dự án khác |
| **Container** | worker chạy bằng uid của bạn (không root), root filesystem chỉ đọc, bỏ mọi Linux capability, `no-new-privileges`; log tự xoay vòng nên không đầy đĩa |

## 4. Bí mật ở đâu, cách bảo vệ

| Bí mật | Vị trí | Ghi chú |
|---|---|---|
| `N8N_ENCRYPTION_KEY`, `TRENDVN_TOKEN`, proxy, token thông báo | `.env` (0600, trong `.gitignore`) | Sao lưu cùng dữ liệu; không đưa lên git |
| Khóa Gemini | `data/worker/gemini.key` (0600) | |
| Kênh thông báo | `data/worker/notify.json` (0600) | |
| Phiên TikTok | `data/agent/profiles/publisher` | Ai có thư mục này là đăng nhập được kênh của bạn. Không sao lưu mặc định (`--with-session` mới kèm) |
| Bản sao lưu | `data/backups/*.tar.gz` (0600) | Chứa bí mật; mã hóa hoặc cất nơi an toàn |

Nếu nghi ngờ lộ `TRENDVN_TOKEN`: sửa giá trị trong `.env`, chạy `./trendvn up`, `./trendvn n8n import` (cập nhật credential n8n) rồi `./trendvn agent restart`.

## 5. Dữ liệu rời khỏi máy bạn

| Đích | Dữ liệu | Khi nào |
|---|---|---|
| Google Gemini | Bản xem trước 384px của video cần phân tích; văn bản lời thoại để tạo giọng đọc | Chỉ khi bạn bật "Xử lý video" và có video trong hàng đợi |
| Nền tảng nguồn | Truy cập trang như một trình duyệt bình thường (qua proxy nếu bạn đặt) | Mỗi lần quét |
| TikTok | Video và mô tả khi đăng; đọc hồ sơ công khai của bạn để xác nhận và lấy lượt xem | Khi đăng và khi chốt ngày |
| Telegram/Discord/Slack/ntfy | Nội dung thông báo (tiêu đề video, lý do, đường dẫn bài đăng) | Chỉ khi bạn cấu hình kênh |
| Không đâu khác | Không telemetry; n8n tắt chẩn đoán | |

## 6. Điều hệ thống **không** làm được

- Không xác nhận bản quyền hoặc tính đúng của nội dung; độ chắc chắn của Gemini không phải sự cho phép.
- Không kiểm soát việc TikTok đổi giao diện (trình đăng có thể hỏng; khi hỏng, bài không bị đăng nhầm).
- Không thay thế giới hạn chi phí của Google; hạn mức 12 lần/24 giờ chỉ là chốt chặn cục bộ.
