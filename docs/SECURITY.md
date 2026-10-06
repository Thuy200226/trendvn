# Bảo mật, quyền riêng tư và rủi ro cần biết

## 1. Rủi ro lớn nhất không nằm ở phần mềm

**Bản quyền và tài khoản.** Hệ thống lấy video do người khác tạo và đăng lại trên kênh của bạn. Không có bước xin phép tác giả, và không phần mềm nào xác nhận được bản quyền hay quyền sử dụng. Hậu quả có thể gặp: video bị gỡ, gậy bản quyền, giảm phân phối, khóa kênh; với video có nhạc thương mại (nhóm dễ bị nhất), nhạc có thể bị TikTok tắt tiếng hoặc chặn. Việc đăng lại còn phụ thuộc điều khoản của từng nền tảng nguồn và luật nơi bạn ở. Bạn chịu trách nhiệm về nội dung đăng. Gợi ý giảm rủi ro:

- Bật "Duyệt tay trước khi đăng" trong thời gian đầu và xem từng video.
- Ưu tiên video có âm nhạc gốc của chính người làm hoặc giải trí không dùng nhạc thương mại; hạ "Số bài mỗi ngày" xuống thấp.
- Chỉ chạm "giới hạn cứng" (tình dục, trẻ em gặp nguy, máu me thật, thù ghét, tự hại/tội phạm, lời khuyên nguy hiểm, đời tư) mới bị chặn chờ bạn; chính trị, drama, xung đột, tin nóng được đăng bình thường. Nội dung càng gây tranh cãi thì rủi ro bị gỡ/giảm phân phối càng cao, đó là đánh đổi bạn đã chọn.

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
| Tin lời trong video | Prompt coi video là dữ liệu không đáng tin và nhắc lại ngay sau video; đầu ra Gemini bị kiểm tra cứng lại: từ chối khóa JSON lặp, nhiều đối tượng, mô tả không phải chuỗi; mô tả và phụ đề bị lọc liên kết, @tên, số điện thoại, email, ký tự ẩn/đảo chiều (`domain/text.py`) |

## 3. Bề mặt tấn công và biện pháp

| Bề mặt | Biện pháp |
|---|---|
| **Cổng dịch vụ** | Mặc định chỉ `127.0.0.1`. Agent chỉ nghe trên địa chỉ cầu nối Docker của dự án, không lộ ra LAN |
| **API worker và agent** | Bearer token 256-bit (`TRENDVN_TOKEN`), so sánh thời gian hằng (`hmac.compare_digest`) |
| **Bảng điều khiển** | Mở không mật khẩu chỉ khi `Host` là localhost **và** kết nối đến từ chính máy này (127.0.0.1, `::1` hoặc cổng cầu nối Docker của dự án); một `Host` giả từ mạng không đủ; yêu cầu mang tiêu đề của reverse proxy (`X-Forwarded-For`, `X-Real-IP`, `Forwarded`...) không bao giờ được coi là cục bộ. Mọi `Host` khác trong `TRENDVN_UI_HOSTS` bắt buộc `TRENDVN_UI_PASSWORD` (phiên lưu **trên máy chủ** (mã ngẫu nhiên, hiệu lực 7 ngày, tối đa 64 phiên): `/logout` và hết hạn vô hiệu hóa mã đó thật, khởi động lại worker (cũng là cách đổi mật khẩu) đăng xuất tất cả; cookie HttpOnly SameSite=Strict; khóa 1 phút sau 5 lần sai), không đặt mật khẩu thì bị từ chối. Chỉ trả lời `Host` trong danh sách cho phép; mọi form kiểm tra `Origin` và token CSRF; CSP không còn `script-src 'unsafe-inline'` (script duy nhất được phép theo mã băm, không có `onclick` trong HTML), `base-uri 'none'`, `Permissions-Policy`, `X-Frame-Options: DENY`, `nosniff`; mọi giá trị hiển thị đều được escape (có test chống chèn mã) |
| **Kết nối HTTP** | Hết hạn socket 30 giây **cho mỗi lần đọc** (chặn client đứng im; **không** chặn kiểu nhỏ giọt từng byte: giới hạn 48 luồng cùng lúc, dư thì trả 503, là chốt chặn, và cổng mặc định chỉ nghe localhost), hàng đợi nghe 64, thân yêu cầu tối đa 2 MiB (worker) / 1 MiB (agent), `Content-Length` âm hoặc lạ bị từ chối, không lộ phiên bản Python; log làm sạch ký tự điều khiển (kể cả C1), và ghi địa chỉ nguồn của mọi 401/403 |
| **Phát video xem trước** | Chỉ đường dẫn nằm trong `data/worker/`, id phải là 32 ký tự hex, hỗ trợ Range, chỉ từ giao diện nội bộ |
| **Cài đặt** | Mỗi khóa cho phép đổi có kiểu và khoảng giá trị chặt; khóa lạ bị từ chối (`validate_settings`) |
| **Tải video** | Chỉ HTTPS, cú pháp URL chặt (không `\`, không `@`, không cổng, không địa chỉ IP, không khoảng trắng/ký tự điều khiển), chỉ tên miền CDN của chính nền tảng (`CDN` trong từng file nguồn), **mỗi lần chuyển hướng cũng bị kiểm tra trước khi gọi** (`fetch_media`), giới hạn 250 MB, phải là MP4 thật (kiểm tra `ftyp` trên 12 byte đầu), ghi qua file `.part` rồi đổi tên. Proxy của yt-dlp đi qua biến môi trường, không nằm trên dòng lệnh (`ps` không thấy mật khẩu) |
| **Đường dẫn file** | `attach` chỉ nhận tên file an toàn trong `inbox/`; chống `..` |
| **Thông báo** | Webhook/ntfy chỉ nhận `https` trên tên miền công khai (không IP dưới mọi dạng, không `localhost`/`.local`/`.internal`), lúc gửi tên phải phân giải ra địa chỉ công khai, không đi theo chuyển hướng 3xx, tin nhắn không bao giờ @everyone (`allowed_mentions`); bí mật lưu `data/worker/notify.json` mode 0600, không bao giờ trả về qua API |
| **Khóa Gemini** | `data/worker/gemini.key` mode 0600; không ghi log, không gửi vào n8n; khóa chỉ đi trong header gửi tới Google. Khi lỗi, chỉ hiển thị dòng `message` do Google trả về (không bao giờ chứa khóa) |
| **Nội dung đầu vào (n8n webhook 10)** | Bắt buộc xác thực; JSON không thể ra lệnh đăng: chỉ đưa video vào hàng đợi sau khi qua mọi kiểm tra |
| **n8n** | `N8N_ENCRYPTION_KEY` riêng cho dự án, tắt telemetry, tài khoản chủ do bạn tạo, workflow xuất không chứa bí mật |
| **Cô lập** | n8n, volume, mạng, container, thông tin xác thực đều riêng, không đọc gì từ dự án khác |
| **Container** | worker chạy bằng uid của bạn (không root), root filesystem chỉ đọc; cả hai container bỏ mọi Linux capability, `no-new-privileges`, giới hạn RAM (worker 4 GB, n8n 2 GB) và số tiến trình (512); log tự xoay vòng nên không đầy đĩa |

## 4. Bí mật ở đâu, cách bảo vệ

| Bí mật | Vị trí | Ghi chú |
|---|---|---|
| `N8N_ENCRYPTION_KEY`, `TRENDVN_TOKEN`, proxy, token thông báo | `.env` (0600, trong `.gitignore`) | Sao lưu cùng dữ liệu; không đưa lên git |
| Khóa Gemini | `data/worker/gemini.key` (0600) | |
| Kênh thông báo | `data/worker/notify.json` (0600) | |
| Phiên TikTok | `data/agent/profiles/publisher` (tài khoản `main`) và `publisher-<mã>` (mỗi tài khoản thêm một thư mục) | Ai có thư mục này là đăng nhập được kênh của bạn. Không sao lưu mặc định (`--with-session` mới kèm) |
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

## 7. Rủi ro đã biết và được chấp nhận (cập nhật 2026-10-02)

| Rủi ro | Vì sao chấp nhận | Giảm thiểu |
|---|---|---|
| Một token dùng chung cho n8n, worker và agent | Hệ thống một chủ, một máy; tách quyền cần thêm bộ cấp phát và sẽ làm phức tạp việc cài đặt | Token 256-bit trong `.env` (0600); cổng chỉ nghe localhost và cầu nối riêng; lộ token thì đổi theo mục 4 |
| Người có token có thể bấm "đăng ngay" qua API, bỏ qua lịch tự động | Đó chính là nút đăng thủ công; vẫn bị chặn khi có bài đang đăng/chưa xác nhận/đang bị xác minh | Chỉ chủ có token |
| yt-dlp không ghim phiên bản | Instagram đổi liên tục, bản cũ hỏng trong vài tuần | Chỉ chạy với URL đã qua kiểm tra miền, kết quả vẫn phải là MP4 thật; cập nhật chủ động bằng `./trendvn update` |
| Phân giải DNS lúc gửi thông báo và lúc kết nối là hai bước (DNS rebinding) | Kênh chỉ do chủ cấu hình; chặn hoàn toàn cần tự kết nối theo IP | Tên miền công khai bắt buộc, không IP, không theo chuyển hướng, kiểm tra lại địa chỉ ngay trước khi gửi |
| `style-src 'unsafe-inline'` còn trong CSP | Giao diện dùng thuộc tính `style` ở nhiều nơi; thay bằng lớp CSS là việc lớn, lợi ích nhỏ vì script đã bị khóa | Mọi giá trị hiển thị được escape; không có script nội tuyến ngoài file đã băm |
| Không có TLS giữa trình duyệt và bảng điều khiển ở localhost | Cùng máy; TLS cần chứng chỉ | Khi mở ra ngoài, dùng đường hầm SSH hoặc proxy TLS và đặt `TRENDVN_UI_HTTPS=1` |
| Docker Desktop (macOS/Windows) có thể trình địa chỉ nguồn khác cổng cầu nối | Chưa kiểm chứng trên máy thật | Nếu bảng điều khiển báo "không phải máy này", thêm địa chỉ đó vào `TRENDVN_TRUSTED_PEERS` (thông báo có ghi sẵn địa chỉ) |
| yt-dlp đọc proxy từ biến môi trường `HTTP(S)_PROXY`/`ALL_PROXY` | Đã kiểm chứng bằng test rằng mật khẩu không còn trên dòng lệnh; **chưa** chạy với một proxy thật (chưa có proxy Mỹ) | Khi có proxy, chạy thử một reel và xem `./trendvn doctor` |
| Bộ lọc văn bản (`domain/text.py`) là heuristic | Có thể còn lọt một dạng liên kết/số điện thoại lạ, hoặc cắt nhầm một cụm hiếm (tên miền ASCII viết thường, số 10-11 chữ số bắt đầu bằng 0) | Mô tả vẫn do chủ xem được trước khi đăng; lọc cuối cùng nằm ở `build_caption` |
| `PrivateTmp` cho dịch vụ agent | Chrome có cửa sổ cần ổ cắm X11 trong `/tmp`; cô lập `/tmp` làm hỏng nó | `NoNewPrivileges=true`; agent chỉ nghe cầu nối riêng |

## Tìm sản phẩm (khung chat)

Đầu vào của khung chat là dữ liệu không tin cậy: lời nhắn, ảnh, PDF/DOCX/TXT, trang web và nội dung Gemini đọc ra đều không bao giờ là lệnh. Các lớp chặn:

- **Cổng vào.** `POST /chat/send` và `/chat/act` chỉ nhận từ giao diện cục bộ (`local_ui`: chính máy này, hoặc phiên đăng nhập mật khẩu của chủ khi mở từ xa), cùng nguồn (Origin), kèm CSRF của trang; thân tối đa 12 MiB cho tin có tệp và 16 KiB cho thao tác. Tệp: tối đa 3, 4 MiB/tệp, tổng 8 MiB; kiểm chữ ký tệp, DOCX giải nén có giới hạn và cấm DOCTYPE/ENTITY. Chỉ phần chữ của lời nhắn (tối đa 1.000 ký tự) và tên tệp vào nhật ký chat; **nội dung ảnh/tệp chỉ nằm trong bộ nhớ của tiến trình** cho đến khi nhận diện xong, không ghi xuống đĩa và mất khi khởi động lại.
- **Mạng ra.** `search/fetch.py` chỉ nối tới địa chỉ HTTPS công khai, không thông tin đăng nhập, cổng 443; DNS được kiểm (mọi địa chỉ phải là địa chỉ công khai) và ghim cho kết nối; mỗi chuyển hướng được kiểm lại. Khi kiểm link chia sẻ, chỉ các host `tiktok.com` được yêu cầu: một bước chuyển hướng sang nơi khác được ghi lại nhưng **không bao giờ được gọi**. Chuyển hướng chỉ đọc đầu phản hồi; tiêu đề trang đọc từ 256 KiB đầu bằng mẫu tuyến tính; mọi lần tải có hạn tổng 25 giây (chặn máy chủ nhỏ giọt từng byte) và chỉ ký tự ASCII, không số IP; trang đọc làm tài liệu cho Gemini được rút chữ bằng bộ đọc tuyến tính (bộ HTML chuẩn chạy bậc hai trên đầu vào độc hại), bỏ phần truy vấn của link trước khi gửi đi. Không kết nối được tới mạng riêng, địa chỉ chuyển dịch NAT64 hay multicast.
- **Link hoa hồng.** Hệ thống **không đăng nhập Shop/Affiliate** và không thể chứng minh link thuộc tài khoản nào. Cái nó chứng minh được là *mã sản phẩm* trong link trùng mã sản phẩm đang bàn. Dấu hiệu nhà sáng tạo (tham số như `share_creator_id`) chỉ được so với các link chính chủ đã xác nhận trước đó trên cùng tài khoản; link đầu tiên luôn cần chủ bấm xác nhận. Link khác sản phẩm hoặc không đọc được mã thì không thể xác nhận. Link được lưu chỉ trong SQLite cục bộ (`commission_links`) và không ghi vào log. Khi một tin có cả tệp và link, trang của link được đọc và chữ của nó chuyển cho Gemini (Google) như tài liệu; phần truy vấn (nơi có mã người chia sẻ) bị cắt khỏi địa chỉ trước khi gửi.
- **Tìm video.** TikTok chạy trong hồ sơ Chrome của đúng tài khoản; kiểm tên đăng nhập thật trước khi lấy kết quả (khi chủ mở cửa sổ tự xác minh: kiểm sau khi có kết quả, nên một cửa sổ đăng nhập nhầm tài khoản đã bị cuộn trang trước khi bị từ chối). Douyin chạy trong hồ sơ riêng (`search-cn-<mã>`) mà chủ tự đăng nhập; hệ thống không đọc được phiên đó là của ai nên không kiểm tên đăng nhập. CAPTCHA chỉ được phát hiện và chuyển cho chủ, không giải. Video chỉ vào hàng đợi khi chủ tích xác nhận đã xem, được ghim vào tài khoản đã tìm và luôn cần duyệt trước khi đăng.
- **Đăng nhập kênh.** Cửa sổ đăng nhập (TikTok, Douyin) là Chrome thật do chủ tự thao tác; agent không gõ mật khẩu, không đọc nội dung phiên. Nó chỉ xem *tên* cookie phiên của kênh (và giá trị `LOGIN_STATUS`/cookie phiên không rỗng) trong hồ sơ riêng của tài khoản để biết đã đăng nhập chưa, rồi gửi về worker đúng ba thông tin: tài khoản, kênh, trạng thái (`ok|out|wall`), kèm tên `@tài_khoản` với TikTok. Phiên chỉ nằm trong `data/agent/profiles/` (không vào git, gói, log hay API). Cửa sổ giữ khóa trình duyệt của agent tối đa 10 phút (việc dùng trình duyệt khác bị báo bận). Xóa lịch sử chỉ xóa nhật ký chat, không đụng tới phiên đăng nhập.
- **Giới hạn đã biết.** Hệ thống không thể biết link hoa hồng có đúng của tài khoản chủ hay không nếu chủ xác nhận nhầm; tham số "mã nhà sáng tạo" được nhận diện bằng quy tắc theo tên tham số (heuristic), TikTok có thể đổi dạng link mà không báo.
