# Tìm sản phẩm: một khung chat cho văn bản, ảnh, tài liệu và link

Tab **Tìm** (thanh điều hướng, giữa Tổng quan và Hàng đợi) là một khung chat duy nhất. Bạn gửi bất cứ thứ gì bạn có về sản phẩm; mỗi câu trả lời của hệ thống hiện ngay trong khung, kèm nút cho bước tiếp theo. Không còn biểu mẫu riêng cho video, sản phẩm hay link.

## Dùng thế nào

1. Chọn **tài khoản** ở dưới khung (mọi việc trong tin nhắn đó gắn với tài khoản này).
2. Gửi một trong các thứ sau (Ctrl/⌘+Enter để gửi; kéo thả hoặc dán ảnh vào khung):
   - **Tên/model/biến thể**, ví dụ `bàn phím mchose ace68`;
   - **Ảnh** (PNG/JPEG/WebP), **PDF, DOCX, TXT** (tối đa 3 tệp, 4 MiB mỗi tệp, tổng 8 MiB);
   - **Link**: video TikTok/Douyin, trang web bất kỳ (đọc như tài liệu), hoặc **link chia sẻ sản phẩm TikTok Shop** (xem dưới).
3. Hệ thống trả lời **sản phẩm nhận diện được** (hãng, model, biến thể, từ khóa sẽ dùng cho TikTok và Douyin). Bấm **Tìm video trên TikTok** hoặc **… Douyin**; hoặc **Sửa tên/model** để chỉnh rồi gửi lại.
4. Danh sách video ứng viên hiện ngay trong khung. Xem từng video (liên kết mở nguồn), **tích ô xác nhận** rồi bấm **Chọn và tải để xử lý**: video vào hàng đợi như mọi video khác, gắn đúng tài khoản đã chọn, luôn cần bạn duyệt trước khi đăng.
5. Muốn link hoa hồng của sản phẩm: **dán link chia sẻ vào chính khung chat** (xem dưới).

Gặp xác minh/CAPTCHA của TikTok hay Douyin: thẻ lỗi có nút **Mở cửa sổ để tự xác minh rồi tìm lại**. Bạn tự giải trong cửa sổ đó (tối đa 4 phút); hệ thống không bao giờ giải hay né. Sau khi có kết quả, hệ thống kiểm lại tên đăng nhập thật của phiên.

## Link hoa hồng: hệ thống làm được gì và không làm được gì

Link hoa hồng của sản phẩm trong Showcase của bạn chỉ có trong **ứng dụng TikTok trên điện thoại** (Showcase → chọn sản phẩm → Chia sẻ → Sao chép link). TikTok không đưa link này ra trang web hay API cho tài khoản nhà sáng tạo chưa có ứng dụng Shop Partner được duyệt, và hệ thống này **không đăng nhập Shop/Affiliate của bạn**. Vì vậy cách làm là: bạn sao chép link trong ứng dụng, dán vào khung chat, hệ thống kiểm tra và lưu.

Khi dán, hệ thống làm theo thứ tự:

1. Chỉ chấp nhận link HTTPS của `tiktok.com`. Đi theo các chuyển hướng (chỉ gọi host `tiktok.com`; bước chuyển sang nơi khác được ghi lại nhưng không được gọi).
2. Đọc **mã sản phẩm** từ địa chỉ cuối (và tên sản phẩm từ trang, nếu đọc được).
3. So với sản phẩm đang bàn trong khung (tin nhận diện gần nhất). Nếu chưa có sản phẩm nào, chính link là sản phẩm của khung.
4. Tìm các tham số gắn link với một **người chia sẻ** (ví dụ `share_creator_id`), và so với các link bạn đã xác nhận trước đó trên cùng tài khoản.

| Kết luận | Nghĩa | Việc của bạn |
|---|---|---|
| **Đúng sản phẩm** | Mã sản phẩm trùng mã đang bàn | Link đã lưu ngay nếu có cùng dấu hiệu nhà sáng tạo với các link bạn đã xác nhận; ngược lại bấm xác nhận |
| **Đã đọc sản phẩm** | Chưa có sản phẩm khác để đối chiếu; sản phẩm của khung lấy từ chính link | Xác nhận nếu đúng |
| **Có vẻ đúng** | Không có mã để so; tên trang khớp hãng/model (chỉ là ứng viên) | Tự mở link xem rồi mới xác nhận |
| **Chưa rõ** | Không đọc được tên hay mã để so | Tự mở link xem |
| **Sản phẩm khác** | Mã hoặc model/biến thể khác | Không dùng; không thể xác nhận |
| **Không hợp lệ** | Không đọc được mã sản phẩm | Dán lại link chia sẻ đầy đủ |

Điều kiện để tin: **chính xác = cùng mã sản phẩm**. Tên giống nhau không bao giờ cho kết luận "đúng". Hệ thống **không thể chứng minh** link thuộc tài khoản nào: lần đầu tiên (hoặc khi dấu hiệu nhà sáng tạo khác các link đã xác nhận) bạn phải bấm "Đây đúng là link hoa hồng của tôi", và chỉ nên bấm khi chính bạn sao chép nó từ Showcase. Link thường (không có dấu hiệu nhà sáng tạo) được báo là **không tính hoa hồng**. Link đã lưu hiện kèm nút **Chép link**.

## Nhận diện sản phẩm

- Lời bạn gõ thắng ảnh: nếu ảnh được Gemini đọc ra hãng/model khác tên bạn nhập, hệ thống giữ tên bạn, báo xung đột và hiện cái ảnh đọc được. Lời không chứa hãng hay model (ví dụ "tìm cái này") không ghi đè điều Gemini đọc từ ảnh/trang.
- Gemini quá tải hoặc trả lời hỏng: tên bạn nhập vẫn tìm được; ảnh/tài liệu **không có tên đi kèm** thì cần nhận diện thành công, nếu không báo lỗi bằng lời.
- Từ khóa Douyin giữ nguyên hãng/model/biến thể khi dịch; dòng sản phẩm có từ riêng ở chợ Trung Quốc nằm ở bảng `LINE_HINTS` trong `services/worker/src/trendvn_worker/domain/search_queries.py` (thêm một dòng là thêm một dòng sản phẩm), bí danh hãng ở `BRAND_ALIASES`.
- Ảnh không được đưa vào ô tìm ảnh của TikTok: Gemini mô tả, rồi tìm bằng chữ.

## Tìm video và kiểm khớp

Tìm chạy trong hồ sơ Chrome của đúng tài khoản (headless, hoặc cửa sổ của bạn khi tự xác minh). Mỗi ứng viên được so với sản phẩm: **khác hãng, model hoặc biến thể thì bị loại khỏi lựa chọn**; khớp từ khóa chỉ là ứng viên và luôn cần bạn xem video. Tối đa 20 ứng viên mỗi lần, chỉ tải video bạn chọn. Chọn "TikTok + Douyin": một nguồn lỗi (kể cả hết thời gian chờ) không làm mất kết quả của nguồn kia.

## Không làm / chưa kiểm chứng

- Không tự đăng, không tự thêm sản phẩm vào Showcase, không đăng video gắn giỏ hàng. Những việc đó cần ứng dụng Shop Partner được duyệt; mã tích hợp API Shop đã gỡ khỏi bản này (còn nguyên ở commit `3d48f41` nếu sau này bạn có ứng dụng được duyệt).
- Không có cách nào chứng minh "đúng 100% mọi sản phẩm" từ ảnh hoặc mô tả thiếu thông tin. Cái chắc chắn duy nhất là **mã sản phẩm trùng**; mọi thứ khác là ứng viên cho bạn xem.
- Đã kiểm bằng test và Chrome thật với agent giả; **chưa** kiểm với link chia sẻ thật từ ứng dụng TikTok (dạng tham số có thể khác dự đoán) và với nguồn TikTok/Douyin thật bị chặn xác minh. Xem `docs/ROADMAP.md`, Phase K.

## Dữ liệu và riêng tư

Nhật ký chat (SQLite `chat`, giữ 300 tin gần nhất) chỉ chứa lời nhắn đã cắt còn 1.000 ký tự, tên tệp và kết quả; **nội dung ảnh/tài liệu chỉ nằm trong bộ nhớ** tới khi nhận diện xong. Link bạn xác nhận nằm ở bảng `commission_links` (một dòng cho mỗi cặp tài khoản + sản phẩm). Chi tiết bảo mật: `docs/SECURITY.md`.
