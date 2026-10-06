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

Gặp xác minh/CAPTCHA của TikTok hay Douyin: thẻ lỗi có nút **Mở cửa sổ để tự xác minh rồi tìm lại**. Bạn tự giải trong cửa sổ đó (tối đa 4 phút mỗi trang); hệ thống không bao giờ giải hay né. Sau khi có kết quả, hệ thống kiểm lại tên đăng nhập thật của phiên.

## Link hoa hồng: hệ thống làm được gì và không làm được gì

Link hoa hồng của sản phẩm trong Showcase của bạn chỉ có trong **ứng dụng TikTok trên điện thoại** (Showcase → chọn sản phẩm → Chia sẻ → Sao chép link). TikTok không đưa link này ra trang web hay API cho tài khoản nhà sáng tạo chưa có ứng dụng Shop Partner được duyệt, và hệ thống này **không đăng nhập Shop/Affiliate của bạn**. Vì vậy cách làm là: bạn sao chép link trong ứng dụng, dán vào khung chat, hệ thống kiểm tra và lưu.

Khi dán, hệ thống làm theo thứ tự:

1. Chỉ chấp nhận link HTTPS của `tiktok.com` (địa chỉ chữ, không phải số IP, chỉ ký tự ASCII). Đi theo các chuyển hướng và đọc tiêu đề trang chỉ với host `tiktok.com`; một bước chuyển sang nơi khác được ghi lại nhưng không bao giờ được gọi. Link rút gọn dẫn tới một **video** thì không bị coi là sản phẩm: hệ thống thêm video đó bên dưới để bạn tìm/tải.
2. Đọc **mã sản phẩm** (và tên sản phẩm từ trang, nếu đọc được). Hai mã sản phẩm khác nhau trên đường đi (hoặc trong một địa chỉ) thì không biết là sản phẩm nào: kết luận **Không hợp lệ**; trang trả HTTP 404/410 cũng vậy (link hết hạn).
3. So với sản phẩm đang bàn trong khung (tin nhận diện gần nhất). Nếu chưa có sản phẩm nào, chính link là sản phẩm của khung.
4. Tìm các tham số gắn link với một **người chia sẻ** (ví dụ `share_creator_id`), và so với các link bạn đã xác nhận trước đó trên cùng tài khoản.

| Kết luận | Nghĩa | Việc của bạn |
|---|---|---|
| **Đúng sản phẩm** | Mã sản phẩm trùng mã đang bàn | Link được lưu ngay nếu **mọi** dấu hiệu chỉ người chia sẻ trong nó (`share_creator_id`, `sec_user_id`, `u_code`, …) trùng giá trị với một link bạn đã xác nhận (thẻ chiến dịch như `ug_btm` không tính); ngược lại bấm xác nhận |
| **Đã đọc sản phẩm** | Chưa có sản phẩm khác để đối chiếu; sản phẩm của khung lấy từ chính link | Xác nhận nếu đúng |
| **Có vẻ đúng** | Không có mã để so; tên trang khớp hãng/model (chỉ là ứng viên) | Tự mở link xem rồi mới xác nhận |
| **Chưa rõ** | Không đọc được tên hay mã để so | Tự mở link xem |
| **Sản phẩm khác** | Mã hoặc model/biến thể khác | Không dùng; không thể xác nhận |
| **Không hợp lệ** | Không đọc được mã sản phẩm | Dán lại link chia sẻ đầy đủ |

Điều kiện để tin: **chính xác = cùng mã sản phẩm**. Tên giống nhau không bao giờ cho kết luận "đúng". Hệ thống **không thể chứng minh** link thuộc tài khoản nào: lần đầu tiên (hoặc khi dấu hiệu nhà sáng tạo khác các link đã xác nhận) bạn phải bấm "Đây đúng là link hoa hồng của tôi", và chỉ nên bấm khi chính bạn sao chép nó từ Showcase. Một link **đầy đủ không có dấu hiệu nhà sáng tạo** được báo là **không tính hoa hồng**; một **link rút gọn** (`vt.tiktok.com/…`) không thấy dấu hiệu thì hệ thống nói thẳng là không kiểm được (mã người chia sẻ có thể nằm ở phía TikTok) và để bạn tự xác nhận. Link đã lưu hiện kèm nút **Chép link**.

## Nhận diện sản phẩm

- Lời bạn gõ thắng ảnh: ảnh được đọc **riêng** (Gemini không thấy lời bạn khi có tệp, để không chép theo lời và che mâu thuẫn). Nếu ảnh được đọc ra hãng/model khác tên bạn nhập, hệ thống giữ tên bạn, báo xung đột và hiện cái ảnh đọc được. Biến thể do Gemini đọc từ ảnh chỉ là mô tả, không bao giờ loại video. Lời không chứa hãng hay model (ví dụ "tìm cái này") không ghi đè điều Gemini đọc từ ảnh/trang.
- Gemini quá tải hoặc trả lời hỏng: tên bạn nhập vẫn tìm được; ảnh/tài liệu **không có tên đi kèm** thì cần nhận diện thành công, nếu không báo lỗi bằng lời.
- Từ khóa Douyin giữ nguyên hãng/model/biến thể khi dịch; dòng sản phẩm có từ riêng ở chợ Trung Quốc nằm ở bảng `LINE_HINTS` trong `services/worker/src/trendvn_worker/domain/search_queries.py` (thêm một dòng là thêm một dòng sản phẩm), bí danh hãng ở `BRAND_ALIASES`.
- Ảnh không được đưa vào ô tìm ảnh của TikTok: Gemini mô tả, rồi tìm bằng chữ.

## Tìm video cần đăng nhập (đã đo ngày 2026-10-06)

Khách chưa đăng nhập **không tìm kiếm video được** ở cả hai nguồn:
- **TikTok:** API tìm kiếm trả phản hồi rỗng cho khách (trang hiện "Đã xảy ra lỗi… máy chủ"). Cần hồ sơ đã đăng nhập của tài khoản: `./trendvn tiktok login` (thêm `--account <mã>` cho tài khoản khác). Chưa đăng nhập thì hệ thống báo đúng lệnh này.
- **Douyin:** khách bị chuyển tới trang trắng tên "验证码中间页" (xác minh mã). Bấm **Mở cửa sổ để tự xác minh rồi tìm lại**, tự xác minh/đăng nhập một lần trong cửa sổ đó (hồ sơ riêng `search-cn-<mã tài khoản>` nhớ phiên); không có cách tìm theo từ khóa mà không qua bước này. Hệ thống không giải và không né xác minh.
- **Không cần đăng nhập:** dán thẳng link video (TikTok hoặc Douyin) vào chat thì chỉ đọc đúng video đó; và các luồng thu thập theo chủ đề (tab chủ đề `jingxuan` của Douyin) không dùng tìm kiếm.

## Tìm video và kiểm khớp

Quy tắc loại ứng viên (chỉ "khác sản phẩm" mới bị loại; còn lại là ứng viên cho bạn xem): **khác model** (mã có chữ số trong lời bạn, trừ thông số như 256GB, 5G), **khác biến thể** bạn nêu hoặc tiêu đề có thêm từ biến thể bạn không nêu (Pro, Max, Ultra, Plus/`+`, Lite, Air…), **tiêu đề nêu hãng khác** trong danh sách hãng đã biết (`KNOWN_BRANDS`). Tiêu đề chỉ không nhắc hãng thì vẫn là ứng viên (điểm thấp hơn). Sản phẩm lấy từ link (tên trang quảng cáo) chỉ dùng hãng và các luật biến thể, không bắt video lặp lại số trong tiêu đề.

TikTok chạy trong hồ sơ Chrome đã đăng nhập của đúng tài khoản (hệ thống kiểm tên đăng nhập thật; headless, hoặc cửa sổ của bạn khi tự xác minh, kiểm lại sau khi có kết quả). Douyin chạy trong hồ sơ riêng `search-cn-<mã tài khoản>` không đăng nhập: gặp xác minh thì bạn tự xử lý trong cửa sổ mở từ thẻ lỗi. Mỗi ứng viên được so với sản phẩm: **khác hãng, model hoặc biến thể thì bị loại khỏi lựa chọn**; khớp từ khóa chỉ là ứng viên và luôn cần bạn xem video. Tối đa 20 ứng viên mỗi lần, chỉ tải video bạn chọn. Chọn "TikTok + Douyin": một nguồn lỗi (kể cả hết thời gian chờ) không làm mất kết quả của nguồn kia. Mỗi nguồn trả tối đa 20 ứng viên; sau khi xếp hạng chỉ giữ 20 tốt nhất.

## Không làm / chưa kiểm chứng

- Không tự đăng, không tự thêm sản phẩm vào Showcase, không đăng video gắn giỏ hàng. Những việc đó cần ứng dụng Shop Partner được duyệt; mã tích hợp API Shop đã gỡ khỏi bản này (còn nguyên ở commit `3d48f41` nếu sau này bạn có ứng dụng được duyệt).
- Không có cách nào chứng minh "đúng 100% mọi sản phẩm" từ ảnh hoặc mô tả thiếu thông tin. Cái chắc chắn duy nhất là **mã sản phẩm trùng**; mọi thứ khác là ứng viên cho bạn xem.
- Đã kiểm bằng test và Chrome thật với agent giả; **chưa** kiểm với link chia sẻ thật từ ứng dụng TikTok (dạng tham số có thể khác dự đoán) và với nguồn TikTok/Douyin thật bị chặn xác minh. Xem `docs/ROADMAP.md`, Phase K.

## Dữ liệu và riêng tư

Nhật ký chat (SQLite `chat`, giữ 300 tin gần nhất) chỉ chứa lời nhắn đã cắt còn 1.000 ký tự, tên tệp và kết quả; **nội dung ảnh/tài liệu chỉ nằm trong bộ nhớ** tới khi nhận diện xong. Link bạn xác nhận nằm ở bảng `commission_links` (một dòng cho mỗi cặp tài khoản + sản phẩm). Chi tiết bảo mật: `docs/SECURITY.md`.
