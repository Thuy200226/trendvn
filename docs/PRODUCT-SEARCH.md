# Tìm video và sản phẩm theo tài khoản

Đầu vào tùy chọn: văn bản, ảnh PNG/JPEG/WebP, PDF, DOCX, TXT hoặc đường dẫn HTTPS. Có thể dán hoặc kéo tệp vào ô tìm kiếm. Không nhập yêu cầu thì luồng thu thập theo chủ đề cũ vẫn chạy.

Luồng: chọn tài khoản → nhập yêu cầu → nhận diện thông tin sản phẩm → tìm ứng viên → chủ chọn video và sản phẩm → tải video → hàng đợi xử lý hiện tại → duyệt → diễn tập → đăng khi chủ bấm Đăng.

## Quyết định thiết kế

- Tìm kiếm chủ động độc lập với ngưỡng thịnh hành và mốc lần quét đầu; người tìm sản phẩm cần video đúng hàng, không nhất thiết nhiều lượt xem.
- Yêu cầu và kết quả thuộc tài khoản đã chọn. Video tìm kiếm không được lịch lấy sang tài khoản khác.
- Tên/hình ảnh giống nhau chỉ là ứng viên. Mã sản phẩm, thương hiệu, model, dung tích, màu và biến thể phải được kiểm tra; điểm khớp từ khóa không phải xác suất đúng.
- Không tải tất cả kết quả: giữ tối đa 20 ứng viên, chỉ tải sau khi chủ chọn. Mỗi lần nhận diện dùng một vòng gọi Gemini (có thể thử model dự phòng khi lỗi), dùng hạn mức chung.
- Mỗi tệp tối đa 4 MiB, tối đa 3 tệp, tổng tối đa 8 MiB. DOCX giải nén có giới hạn; PDF/ảnh được gửi cho Gemini để đọc, không thực thi nội dung. URL phải HTTPS công khai, kiểm DNS và từng chuyển hướng.
- Danh sách hoa hồng phải lấy trong phiên nhà sáng tạo đúng tài khoản, không dùng danh sách bán hàng công khai làm chứng cứ. Chưa xác minh hoặc gặp CAPTCHA/hết phiên thì dừng và báo rõ.
- Không bao giờ đăng video được chọn với yêu cầu giỏ hàng nếu không gắn và xác minh đúng mã sản phẩm. Giao diện TikTok không hỗ trợ thì giữ video và báo chủ, không âm thầm đăng video thiếu giỏ.

## Giới hạn kiểm chứng

Không có cách chứng minh đúng 100% với mọi sản phẩm từ ảnh hoặc mô tả thiếu thông tin. Giữ bước lựa chọn và xác nhận của chủ; ghi riêng những gì tìm thấy, chưa xác minh hoặc bị nền tảng chặn. Đăng thật và thêm vào showcase là thao tác ngoài hệ thống, cần chủ chọn sản phẩm và bấm nút tương ứng.

Tài liệu nền tảng: [Affiliate integration](https://partner.tiktokshop.com/docv2/page/affiliate-integration), [Product Marketplace](https://seller-vn.tiktok.com/university/essay?knowledge_id=6837827107342081&lang=en), [Link products](https://seller-vn.tiktok.com/university/essay?knowledge_id=496374274639617&lang=en).

## Kết nối và đăng kèm giỏ hàng

Mở Thêm → Tìm sản phẩm → Kết nối TikTok Shop. Bước 1 mở cửa sổ đăng nhập đúng tài khoản. Nếu chỉ có tài khoản nhà sáng tạo, xem hoa hồng/trang trưng bày trong ứng dụng TikTok; tự đồng bộ cần ứng dụng TikTok Shop được duyệt. Khi có ứng dụng: nhập App key/secret tại máy, đặt Redirect URL như trang hiển thị, rồi tự đăng nhập/đồng ý cấp quyền. Không gửi bí mật qua chat. Có lựa chọn nâng cao dùng token có sẵn. Token người bán không thay được token nhà sáng tạo. Ứng dụng phải có quyền đọc thông tin/tiếp thị liên kết/showcase và quyền `creator.video.write` để đăng. Luồng cấp quyền chính thức lưu access/refresh token bảo vệ quyền đọc, kiểm creator/scopes/username; làm mới trước khi hết hạn và kiểm open_id không đổi. Token nhập tay không có refresh token thì vẫn cần nhập lại khi hết hạn.

Đọc tối đa2.000 sản phẩm showcase và20 ứng viên marketplace cho mỗi tìm kiếm. Marketplace có thông tin hoa hồng nhưng chưa chứng minh đủ điều kiện gắn; thêm sản phẩm trong TikTok rồi đồng bộ lại để xác minh showcase. Khi ghép video, xác nhận đúng sản phẩm và biến thể. Khi đăng, kiểm lại username, quyền tiếp thị liên kết, showcase, tồn kho, hoa hồng và MD5. Hiện API tải trực tiếp hỗ trợ video tối đa10 MiB; video lớn hơn hoặc chế độ không công khai được giữ lại và báo lý do, chưa triển khai luồng tải tệp lớn. Chạy thử có tải tệp lên TikTok Shop nhưng không gửi lệnh đăng.

API tham chiếu: [Creator Profile](https://partner.tiktokshop.com/docv2/page/get-creator-profile-202508), [Showcase](https://partner.tiktokshop.com/docv2/page/get-showcase-products-202405), [Search open collaboration](https://partner.tiktokshop.com/docv2/page/creator-search-open-collaboration-product-202405), [Upload](https://partner.tiktokshop.com/docv2/page/upload-shoppable-video-file-202505), [Post shoppable video](https://partner.tiktokshop.com/docv2/page/post-shoppable-video-202603), [Posting status](https://partner.tiktokshop.com/docv2/page/get-shoppable-video-status-202509).


## Tên, hình ảnh và nguồn tiếng Trung

Tên/model/biến thể nhập ngắn được ưu tiên, ảnh bổ sung thông tin; nếu AI nhận ảnh khác thì báo xung đột và giữ tên. Nếu Gemini chưa đọc được ảnh, tên đủ thông tin vẫn tìm được; ảnh không có tên thì cần nhận diện thành công. Ảnh không được gửi vào ô tìm kiếm ảnh TikTok: Gemini trích mô tả/từ khóa, sau đó dùng tìm kiếm văn bản. Không khẳng định nền tảng không có mọi dạng tìm kiếm ảnh ở mọi khu vực.

Chọn TikTok, Douyin hoặc cả hai. Mỗi nguồn hiện từ khóa đã dùng. Với bàn phím MCHOSE ACE68: TikTok dùng tên/model, Douyin dùng `迈从 ACE68 磁轴键盘`; alias thương hiệu đối chiếu theo [hướng dẫn MCHOSE](https://file.maicong.cn/uploads/25/02/MCHOSE%2020250211.pdf). Không đổi ACE68 thành Air/Turbo/GT/V2 khi dịch hoặc xếp kết quả. Tìm lại tạo phiên mới để video đã chọn không bị mất liên kết với kết quả cũ. CAPTCHA cần chủ tự xử lý trong cửa sổ mở từ trang, không giải tự động.

Cấp quyền nhà sáng tạo theo [TikTok Creator Authorization](https://partner.tiktokshop.com/docv2/page/678e3a362dccb8030ea6f98c); [showcase](https://partner.tiktokshop.com/docv2/page/get-showcase-products-202405) chấp nhận quyền `creator.showcase.read` hoặc `creator.video.write`. Quyền đăng không suy ra từ quyền đọc.
