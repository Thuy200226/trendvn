# Nhật ký rà soát phiên bản 1.2

> Ghi chú: đây là tài liệu lịch sử của bản 1.2; các đường dẫn trong đó (`worker/`, `agent/`, `runtime/`, `agent_data/`, `install.sh`...) là của bố cục cũ. Bảng đối chiếu sang bố cục 1.3 nằm ở [CHANGELOG](../CHANGELOG.md).

Mục tiêu: giao diện dùng tốt trên điện thoại, nhanh, không phát sinh lỗi, và chất lượng video, mô tả, hashtag đủ tốt để đăng. Bốn vòng rà soát, cộng các thử nghiệm bằng dịch vụ thật. Mọi phát hiện dưới đây đều đã được tái hiện bằng mã hoặc bằng chạy thật trước khi sửa.

## Vòng 1 — Giao diện (Chrome thật, tự động)

> **Cập nhật sau phản hồi khi dùng thật:** hàng đợi tách thành tab riêng (6 tab), thanh trạng thái thành thẻ, hướng dẫn khi tab Đăng bài trống; bộ kiểm tra nay chạy 6 tab × 7 kích thước và kiểm tra riêng thanh dưới (nhãn không xuống dòng, không chạm nhau).

Công cụ: `tests/ui_e2e.py` dựng một worker thật với dữ liệu mẫu (có video) cùng một agent giả, mở Chrome thật ở 7 kích thước (320×640, 360×740, 375×812, 414×896, 768×1024, 1280×900, 1440×900) và 6 tab. Mỗi trang được kiểm tra: tràn ngang, các khối chồng lên nhau (so từng cặp hộp), thẻ dính sát nhau, nút nhỏ hơn 44 px, chữ bị cắt, cỡ chữ nhỏ hơn 11 px, thanh dưới che cuối trang. Sau đó bấm thử toàn bộ luồng: Bắt đầu, Thu thập, Xử lý, Đăng ngay, Xem thử, Sửa mô tả, Khôi phục, Bỏ video, bấm đúp, agent bận, agent tắt.

| # | Lỗi tìm thấy | Mức độ | Cách sửa |
|---|---|---|---|
| 1 | **Mọi nút gửi form bị từ chối** ("Local form only"): tiêu đề `Referrer-Policy: no-referrer` khiến Chrome gửi `Origin: null` cho form cùng trang. Đã tồn tại từ 1.0 (trước đó chỉ xem trang, chưa bấm form trong trình duyệt) | nghiêm trọng | `same-origin` và chấp nhận `Origin: null` chỉ khi `Sec-Fetch-Site: same-origin`; vẫn bắt buộc CSRF |
| 2 | Chính sách bảo mật chặn biểu tượng trang (lỗi console) | thấp | `img-src 'self' data:` |
| 3 | `.wrap` ghi đè khoảng đệm dưới của `main`: chân trang dính sát thanh điều hướng dưới trên điện thoại | trung bình | tách lề trái/phải khỏi lề trên/dưới |
| 4 | Bấm menu trên màn hình rộng thì tiêu đề mục bị thanh đầu trang che | trung bình | `scroll-margin-top` |
| 5 | Nút làm mới 38–41 px; menu trên 35 px (dưới 44 px cho cảm ứng) | thấp | nâng lên 44 px |
| 6 | Bấm Đăng ngay chuyển sang tab Đăng bài nhưng tiến độ chỉ hiện ở tab Tổng quan: không thấy kết quả | trung bình | bảng tiến độ có mặt ở tab liên quan (Đăng bài, Đã đăng) |
| 7 | Tab Đăng bài thiếu khoảng cách đều giữa các khối | thấp | hệ khoảng cách chung `.stack` |

Kết quả cuối: **58 kiểm tra đạt, 0 lỗi** (35 bố cục + 23 luồng bấm nút, kể cả không có lỗi console).

## Vòng 2 — Hiệu suất (30.000 video, 150.000 sự kiện, 100.000 quan sát)

| Thao tác | Trước | Sau chỉ mục |
|---|---|---|
| Dữ liệu bảng điều khiển | 63 ms | **20 ms** |
| Trạng thái API (collector và n8n gọi liên tục) | 13 ms | **8 ms** |
| Cả trang (dữ liệu + HTML) | 66 ms | **22 ms** |
| Nhập 100 video | 9 ms | 11 ms |
| HTML gửi đi | 134 KB | **16 KB** sau gzip |

Khác: video xem trước không tải khi chưa bấm (`preload=none` + ảnh poster), trang chỉ hỏi một đoạn HTML nhỏ để cập nhật tiến độ (thay vì tải lại cả trang), nền mờ dựng bằng ảnh thu nhỏ rồi phóng (nhanh hơn khoảng 4 lần), file dựng giới hạn 4 Mbps (video 78 giây: 54 MB → 41 MB; video 4K thu về 1080×1920). Một số liệu thật khác: dựng video dọc 78 giây mất 36 giây, video dọc 36 giây mất 7 giây.

## Vòng 3 — Rà soát độc lập đọc mã (một tác tử riêng, chỉ đọc)

Nhận 22 phát hiện. Đã kiểm chứng và sửa tất cả; các mục đáng chú ý:

| # | Phát hiện | Mức | Xử lý |
|---|---|---|---|
| 1 | Lỗi trước khi bấm Đăng (Chrome không mở...) để lại bài `publishing`, sau 15 phút thành "đã bấm Đăng chưa xác nhận" và chặn mọi lần đăng | cao | `publish_one` không bao giờ ném lỗi: trước khi bấm = `failed`, sau khi bấm = `unknown` (có test) |
| 2 | Đăng tay thất bại trên video chờ duyệt lặng lẽ duyệt nó cho lịch tự đăng | trung bình | nhớ `prev_state`, khôi phục khi thất bại |
| 3 | Một video lỗi mãi chặn cả kênh (lịch chọn lại nó mỗi 30 phút, mỗi lần mở Chrome) | trung bình | nghỉ 1 giờ sau lỗi, 3 lần thì vào Cần xem |
| 4 | Không có nút duyệt video cho lịch tự đăng khi bật "duyệt tay" | trung bình | thêm nút "Duyệt cho lịch tự đăng" |
| 5 | Ô để trống bị bỏ qua: xóa giờ vàng không có tác dụng, xóa một ngưỡng lại tắt luôn ngưỡng đó | trung bình | đọc cả ô trống, gộp ngưỡng theo nguồn |
| 6 | Mở bảng điều khiển ra ngoài máy không có xác thực | trung bình | bắt buộc `TRENDVN_UI_PASSWORD` (cookie HttpOnly, khóa sau 5 lần sai), doctor cảnh báo |
| 7 | Công tắc "Tự đăng" bật chỉ với một chạm | trung bình | hỏi xác nhận khi bật |
| 8 | Phụ đề rơi vào vùng chữ của TikTok với video vuông, 4:5, 3:4 và video dọc | trung bình | `caption_zone`: dải mờ dưới hoặc trên, hoặc cao hơn, luôn tránh y > 1440 |
| 10 | Video có cờ xoay 90° bị bóp méo | thấp | đọc kích thước hiển thị |
| 11–12 | Nền mờ chậm, video quá lớn không thu nhỏ, `-level` sai | thấp | sửa như trên |
| 13 | Duyệt lại video "có thể trùng hình" không có tác dụng | thấp | bỏ qua kiểm tra trùng hình khi bạn đã duyệt |
| 14 | `hashtags` hỏng làm sập cả bảng điều khiển và lịch đăng | thấp | bảo vệ kiểu dữ liệu, một dòng hỏng không kéo cả trang |
| 15–16 | Xuống dòng CRLF, Unicode tổ hợp, bộ đếm hashtag; số quá lớn gây lỗi 500 | thấp | chuẩn hóa NFC/CRLF, regex Unicode, chặn số |
| 17 | Ngưỡng 15 phút có thể cắt ngang một lần đăng chậm | thấp | nâng lên 45 phút (tối đa lý thuyết của một lần đăng khoảng 20 phút) |
| 18 | Đăng tay trùng mô tả thì mất video | thấp | trả về cho bạn sửa mô tả |
| 19–20 | Mô tả rỗng vẫn đăng; lỗi tạo thư mục để job kẹt `processing` | thấp | vào Cần xem; `mkdir` trong `try`, dọn tác vụ treo trước khi xử lý |
| 21–22 | macOS: khởi động lại dịch vụ, thư mục Downloads, sao lưu qua chia sẻ file; gói thiếu `.env.example` | thấp | sửa, hướng dẫn `~/trendvn`, sao lưu trong container |

Bên rà soát cũng xác nhận ổn: cấp phát đăng nguyên tử (30 lượt đồng thời chỉ 1 thành công), không thể đăng nhầm video (hash), chống truy cập đường dẫn, escape mọi giá trị hiển thị, SQL tham số hóa, ffmpeg ổn với 12 loại đầu vào.

## Vòng 4 — Tấn công chính các bản sửa

Tôi giao một tác tử độc lập thứ hai kiểm tra lại các bản sửa, nhưng nó bị ngắt giữa chừng vì giới hạn phiên của dịch vụ và **không trả báo cáo**, nên vòng này do chính tôi thực hiện, không được tính là rà soát độc lập. Nội dung:

| Kiểm tra | Kết quả |
|---|---|
| Nâng cấp từ cơ sở dữ liệu thật của bản 1.1 (bản sao lưu do `backup.sh` tạo) | 55 video nguyên vẹn, thêm 5 cột và bảng `tasks`, mở lại nhiều lần không lỗi |
| Vượt cổng mật khẩu: 14 đường dẫn (`//`, `/./`, `/%2e/`, `/login/../`, `/api/dashboard`...), `Host` sai chữ hoa/dấu chấm/khoảng trắng/thiếu, tiêu đề `X-Forwarded-For`/`Forwarded`, cookie giả, POST không CSRF, API không token | Không có đường nào cho vào (test tự động) |
| Lỗi tôi tự tìm ra khi đọc lại bản sửa: video bị chuyển "Cần xem" sau 3 lần đăng lỗi không còn đường quay lại đăng, và bộ đếm lỗi không xóa khi duyệt lại | Sửa: nút "↩ Đưa về sẵn sàng đăng", bộ đếm về 0 (có test) |
| Lỗi tìm ra khi chạy test trong ổ đĩa chỉ đọc: ghi nhật ký của agent ném lỗi, phá cam kết "trình đăng không bao giờ ném lỗi" | Sửa: ghi nhật ký không bao giờ làm hỏng tác vụ (có test) |
| Toàn bộ test | 153 test đạt trên máy, 97 test đạt trong image có ffmpeg, 58 kiểm tra trình duyệt thật đạt |

Khuyến nghị: chạy thêm một vòng rà soát độc lập khi dịch vụ sẵn sàng.

## Thử nghiệm bằng dịch vụ thật (không phải giả lập)

| Kiểm tra | Kết quả |
|---|---|
| Gemini: phân tích 4 video thật | Phát hiện Gemini bịa phụ đề sau cuối video dài (11 dòng ngoài 138 giây) khiến video bị từ chối: đã sửa bằng bộ chuẩn hóa mốc thời gian; 3/4 lần chạy sau qua; còn lại là Gemini quá tải (503/504), hệ thống xếp lại hàng đợi đúng thiết kế |
| Chất lượng mô tả | Trước: câu lửng ("...và cái kết") và hashtag tên nền tảng ("tiktokgiaitri"). Sau khi sửa prompt và bộ lọc: "Nghỉ làm cả tháng mà con trai vẫn tính toán để bố trả lương." #haihuoc #tieuphim #congso |
| Nút Thu thập trên bảng điều khiển đang chạy | Chạy thật qua agent: "Douyin: đọc 48, đạt ngưỡng 2, mới 2 / Kuaishou: đọc 20 ..." |
| Nút Xem thử | Chạy thật: Chrome mở TikTok Studio, tải video thử, điền mô tả và 5 hashtag (TikTok nhận diện, bộ đếm 97/4000), dừng trước nút Đăng, ảnh chụp mở được từ bảng điều khiển; không có bài nào bị đăng |
| Nút Bỏ video | Chạy thật, video chuyển sang "rejected" |
| Nút **🚀 Đăng ngay** trên kênh thật | Được chủ kênh đồng ý cho đúng một bài thử riêng tư: bấm nút trên giao diện, hộp xác nhận nêu đúng "CHỈ MÌNH TÔI", Chrome đăng và **xác nhận trên hồ sơ** (`.../video/7691237769196080404`), video biến mất khỏi danh sách, đếm "Hôm nay 1/2". Sau đó khôi phục chế độ Công khai và xóa bản ghi thử khỏi hệ thống; bài trên TikTok để chủ kênh tự xóa |

## Giới hạn còn lại (nói thẳng)

- macOS: cài đặt sạch đã kiểm chứng trên Linux; launchd và `host-gateway` chưa chạy trên Mac thật.
- TikTok thỉnh thoảng đòi xác minh (CAPTCHA); hệ thống dừng và báo, không giải thay bạn. Tần suất ở 2 bài/ngày chưa đo dài hạn.
- Gemini đôi lúc quá tải hoặc chậm (đã thấy 503/504 nhiều lần trong ngày thử); hệ thống thử lại, đổi model và xếp lại hàng đợi, nhưng thời gian xử lý có thể dài hơn bình thường.
- Cờ xoay video được xử lý theo dữ liệu ffprobe và có test đơn vị; chưa thử với video quay từ điện thoại thật.
- Chất lượng mô tả đo trên 4 video (chủ yếu tiếng Trung, hài); chưa đo trên video nhạc hay thuyết minh.
