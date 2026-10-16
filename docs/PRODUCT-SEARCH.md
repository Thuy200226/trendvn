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

Tìm thông thường trong cửa sổ Chrome có màn hình sẽ chờ bạn khi gặp xác minh/CAPTCHA. Nếu lượt trước đã báo lỗi, thẻ lỗi có nút **Mở cửa sổ để tự xác minh rồi tìm lại**. Bạn tự giải trong cửa sổ đó (không tự đóng vì hết giờ; đóng cửa sổ nếu muốn dừng); hệ thống không bao giờ giải hay né. Sau khi có kết quả, hệ thống kiểm lại tên đăng nhập thật của phiên.

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

## Đăng nhập các kênh tìm kiếm

Khách chưa đăng nhập **không tìm video theo từ khóa được** (đã đo ngày 2026-10-06 trên chính máy này):
- **TikTok:** API tìm kiếm trả phản hồi rỗng cho khách (trang hiện "Đã xảy ra lỗi… máy chủ").
- **Douyin:** Chrome ẩn (headless) bị chuyển tới trang trắng tên "验证码中间页" (xác minh mã) ngay cả ở trang chủ; Chrome có cửa sổ vào được trang chủ nhưng trang **tìm kiếm** vẫn đòi xác minh với khách.

Vì vậy cột bên cạnh khung chat có mục **Kênh tìm kiếm**: mỗi tài khoản đang bật có một dòng TikTok và một dòng Douyin, mỗi dòng có tình trạng (Sẵn sàng / Chưa đăng nhập / Đòi xác minh / Chưa kiểm, kèm thời điểm biết được) và hai nút:
- **Đăng nhập** mở một cửa sổ Chrome thật **trên máy chạy TrendVN** (không phải trình duyệt bạn đang xem bảng điều khiển). Bạn tự đăng nhập trong đó (quét mã QR hoặc số điện thoại), không giới hạn thời gian; cửa sổ chỉ tự đóng khi đã đăng nhập và không còn xác minh, rồi hệ thống đọc lại hồ sơ để chắc phiên còn sau khi cửa sổ đóng. Hệ thống không nhập mật khẩu hộ, không sao chép hay công khai cookie. Douyin chỉ tính thành công khi trang trả thông tin tài khoản sở hữu; cookie còn tồn tại không đủ bằng chứng. Sau khi Chrome lưu hồ sơ, hệ thống mở lại trang để kiểm phiên còn dùng được. TikTok dùng chính hồ sơ đăng bài của tài khoản (một lần đăng nhập dùng cho cả đăng bài và tìm kiếm) và chỉ tính khi cửa sổ đăng nhập đúng `@tài_khoản`; Douyin có hồ sơ riêng `search-cn-<mã tài khoản>`.
- **Kiểm tra** Douyin mở trang trong chính hồ sơ và vùng CN, chờ bằng chứng tài khoản sở hữu. Trang khách → Chưa đăng nhập; CAPTCHA → Chờ xác minh; trang chưa đọc được → Chưa xác nhận phiên, giữ hồ sơ. Các nguồn còn lại đọc cookie trước; lần tìm TikTok kiểm lại đúng `@tài_khoản`. Cookie chỉ là dấu hiệu hồ sơ có thể dùng được, không bảo đảm nền tảng chưa thu hồi phiên.
Thẻ lỗi của một lần tìm cũng có sẵn nút đăng nhập đúng kênh. Máy không có màn hình thì không mở được cửa sổ: hệ thống báo (với TikTok kèm cách dùng `./trendvn tiktok login` trên máy có màn hình; Douyin cần chạy TrendVN trên máy có màn hình).

Khi máy có màn hình, tìm kiếm TikTok và Douyin chạy bằng **cửa sổ Chrome thật** (như đăng bài) vì Douyin từ chối Chrome ẩn; cửa sổ hiện trong lúc tìm (thường vài chục giây, có thể tới vài phút khi mạng chậm) rồi tự đóng. Hệ thống kiểm màn hình còn thật sự tồn tại (biến `DISPLAY` của dịch vụ được đặt lúc cài và có thể đã cũ); không có thì tìm kiếm chạy ẩn, TikTok vẫn có thể chạy còn Douyin sẽ bị chặn. Đặt `TRENDVN_PUBLISH_HEADED=0` để ép chạy ẩn. Trong lúc cửa sổ đăng nhập mở, agent bận (các việc dùng trình duyệt khác, kể cả lịch tự động, phải đợi hoặc báo bận).

**Kiểm chứng ngày 2026-10-09:** cookie cũ từng khiến hồ sơ khách bị báo sẵn sàng. Sau khi chủ đăng nhập, mở lại đúng hồ sơ nhận được phản hồi tài khoản sở hữu và không còn nút 登录. Bộ đọc mới lấy 16 video thật cho “迈从 ACE68 磁轴键盘”; kết quả vẫn cần lọc biến thể và chủ xem trước khi chọn. Không dùng việc có video công khai làm bằng chứng đăng nhập.

**Link video:** chỉ đọc đúng ID trong link, không lấy video khác thay thế. Luồng tìm chat yêu cầu phiên nguồn; thu thập chủ đề Douyin (`jingxuan`) là luồng riêng.

Kênh khác (Kuaishou, Instagram) có bộ đọc tìm kiếm trong `search_extra.py`; cần phiên phù hợp và điều kiện mạng của nền tảng. Chưa nghiệm thu tìm thật hai nguồn này trong phase S. Thêm một kênh cần: một mục trong `services/agent/src/trendvn_agent/channels.py` (tên, trang web, cookie phiên, ngôn ngữ), một mô-đun đọc trang như `search_douyin.py` và một dòng trong `_ask` của `search.py`, rồi tên kênh trong `services/worker/src/trendvn_worker/domain/channels.py` (worker và giao diện lấy danh sách kênh từ đó).

## Link đã lưu và lịch sử

Cột bên cạnh cũng liệt kê **Link hoa hồng đã lưu** (mỗi tài khoản, mới nhất trước; nút **Chép link** và **Xóa link này**) để bạn lấy lại link bất cứ lúc nào, kể cả sau khi xóa lịch sử. **Xóa lịch sử tìm kiếm** (hỏi lại trước khi làm) ẩn toàn bộ lượt trong khung chat, kể cả đang chạy; kết quả đến muộn cùng lượt cũng ẩn. Không xóa video đã chọn hay đã tải, link đã lưu và phiên đăng nhập. Xóa lượt riêng ẩn cả câu nhập và mọi thẻ con; cửa sổ đang chờ vẫn hoạt động ngoài lịch sử. Một video đã chọn nhưng chưa tải xong giữ lại tin nhắn nó cần cho tới khi tải xong. Hệ thống cũng tự xóa tin đã xong cũ hơn 30 ngày khi dọn dẹp định kỳ. Lịch sử tìm kiếm **trên tài khoản TikTok/Douyin** (mục "tìm kiếm gần đây" của chính nền tảng) không bị xóa bởi nút này.

## Tìm video và kiểm khớp

Quy tắc loại ứng viên (chỉ "khác sản phẩm" mới bị loại; còn lại là ứng viên cho bạn xem): **khác model** (mã có chữ số trong lời bạn, trừ thông số như 256GB, 5G), **khác biến thể** bạn nêu hoặc tiêu đề có thêm từ biến thể bạn không nêu (Pro, Max, Ultra, Plus/`+`, Lite, Air…), **tiêu đề nêu hãng khác** trong danh sách hãng đã biết (`KNOWN_BRANDS`). Tiêu đề chỉ không nhắc hãng thì vẫn là ứng viên (điểm thấp hơn). Sản phẩm lấy từ link (tên trang quảng cáo) chỉ dùng hãng và các luật biến thể, không bắt video lặp lại số trong tiêu đề.

TikTok chạy trong hồ sơ Chrome đã đăng nhập của đúng tài khoản (hệ thống kiểm tên đăng nhập thật trước khi đọc kết quả; trong cửa sổ "chờ tôi xác minh" thì kiểm sau khi có kết quả). Douyin chạy trong hồ sơ riêng `search-cn-<mã tài khoản>` (đăng nhập bằng nút Đăng nhập Douyin; xác nhận tài khoản sở hữu từ trang, không ép tên nguồn giống tên tài khoản TikTok nhận video); gặp xác minh thì bạn tự xử lý trong cửa sổ. Mỗi ứng viên được so với sản phẩm: **khác hãng, model hoặc biến thể thì bị loại khỏi lựa chọn**; khớp từ khóa chỉ là ứng viên và luôn cần bạn xem video. Tối đa 20 ứng viên mỗi lần, chỉ tải video bạn chọn. Chọn "TikTok + Douyin": một nguồn lỗi (kể cả hết thời gian chờ) không làm mất kết quả của nguồn kia. Mỗi nguồn trả tối đa 20 ứng viên; sau khi xếp hạng chỉ giữ 20 tốt nhất.

## Không làm / chưa kiểm chứng

- Không tự đăng, không tự thêm sản phẩm vào Showcase, không đăng video gắn giỏ hàng. Những việc đó cần ứng dụng Shop Partner được duyệt; mã tích hợp API Shop đã gỡ khỏi bản này (còn nguyên ở commit `3d48f41` nếu sau này bạn có ứng dụng được duyệt).
- Không có cách nào chứng minh "đúng 100% mọi sản phẩm" từ ảnh hoặc mô tả thiếu thông tin. Cái chắc chắn duy nhất là **mã sản phẩm trùng**; mọi thứ khác là ứng viên cho bạn xem.
- Đã kiểm bằng test và Chrome thật với agent giả; **chưa** kiểm với link chia sẻ thật từ ứng dụng TikTok (dạng tham số có thể khác dự đoán) và với nguồn TikTok/Douyin thật bị chặn xác minh. Xem `docs/ROADMAP.md`, Phase K.

## Dữ liệu và riêng tư

Nhật ký chat (SQLite `chat`, giữ 300 tin gần nhất) chỉ chứa lời nhắn đã cắt còn 1.000 ký tự, tên tệp và kết quả; **nội dung ảnh/tài liệu chỉ nằm trong bộ nhớ** tới khi nhận diện xong. Link bạn xác nhận nằm ở bảng `commission_links` (một dòng cho mỗi cặp tài khoản + sản phẩm). Chi tiết bảo mật: `docs/SECURITY.md`.


## Hàng đợi thống nhất (1.9)

Kế hoạch và kịch bản nghiệm thu: [QUEUE-SEARCH-PLAN.md](QUEUE-SEARCH-PLAN.md). Bộ chọn nguồn có bốn kênh và lựa chọn các kênh đã đăng nhập. Mỗi kênh dùng hồ sơ riêng theo tài khoản nhận video; đăng nhập nguồn Trung Quốc/Instagram không đồng nghĩa với đăng nhập tài khoản TikTok đích. TikTok đích được đối chiếu tên thật trước tìm/đăng/xóa.

Thể loại mặc định lấy từ chủ đề tài khoản. Có thể đổi hoặc chọn không giới hạn. Thể loại, từ khóa và sản phẩm đi vào truy vấn nền tảng, không chỉ lọc kết quả. Chế độ bán hàng cần chọn ngành hàng; ưu tiên khớp model trước, sau đó lượt xem/tim thực đọc được. Chưa có số bán nên chưa xác nhận bảng sản phẩm bán chạy nhất. Ảnh/tài liệu dùng Gemini nhận diện từ khóa; các nguồn web được tìm bằng văn bản/URL, không giả lập tìm ảnh gốc của nền tảng.

Ứng viên trong chat có thể bỏ hoặc chọn vào chờ xử lý sau khi chủ xác nhận đã xem đúng sản phẩm. Hàng đợi cho tải từng ứng viên, xử lý riêng video chờ hoặc bỏ chờ. Đã nhận xử lý/tải thì không cho xóa xen giữa. Xóa riêng lịch sử không làm mất video đã chọn hay link hoa hồng đã lưu. Gửi lại cùng yêu cầu mạng không sinh lượt trùng; cùng từ khóa được chủ gửi thành lượt mới vẫn hợp lệ.

Link hoa hồng vẫn do chủ lấy trong Showcase và dán để kiểm tra/lưu. Tài khoản nhà sáng tạo đơn thuần chưa cung cấp quyền TikTok Shop API; phiên bản này không tự lấy tỷ lệ hoa hồng, bảng doanh số hoặc đăng kèm sản phẩm.

Ở Đã đăng, xóa bài yêu cầu xác nhận đúng URL/tài khoản. Hệ thống giữ bản ghi ứng dụng và đánh dấu đã xóa trên TikTok, không xóa lịch sử thống kê hoặc hoàn lại hạn mức. Nếu thao tác bị ngắt sau khi bắt đầu xóa thì hiển thị chưa rõ để chủ kiểm tra, không tự gửi lại.

Nghiệm thu 2026-10-07: sau chủ tự xác minh Douyin, truy vấn `迈从 ACE68 磁轴键盘` nhận 16 video thật. Video 7627431070878744296 được chủ đối chiếu, tải thật vào hàng chờ (22.961.755 byte); xử lý gặp Gemini 504 nên chưa có bản dựng. Kết quả ACE75/V2 được nhận là khác sản phẩm dù có nhắc ACE68. Bỏ ứng viên giữ dấu nguồn/ID để không lấy lại; xóa lịch sử không xóa dấu này. TikTok/Kuaishou/Instagram vẫn chưa nghiệm thu tìm thành công; chưa có dữ liệu để xác nhận bán chạy nhất/hoa hồng tự động từ tài khoản nhà sáng tạo.

### Dùng lại phiên theo tài khoản (2026-10-09)

Mỗi tài khoản nhận video có hồ sơ riêng cho bốn nguồn; TikTok dùng chung hồ sơ đăng bài của chính tài khoản đó. Đăng nhập/kiểm tra được ghi bền vào CSDL theo `(account, channel)`. Chọn nguồn tự động sẽ kiểm các hồ sơ đã có rồi dùng phiên phù hợp, không bắt đăng nhập chỉ vì báo cáo cũ hoặc thiếu. Chuyển tài khoản nhận thay cả phần trạng thái kênh và link đã lưu; không chia sẻ phiên giữa tài khoản.

Khởi động lại dự án giữ hồ sơ Chrome và trạng thái. CAPTCHA là yêu cầu tự xác minh, không đồng nghĩa mất đăng nhập. Khi nền tảng thu hồi/hết hạn phiên thì vẫn cần đăng nhập lại. Cookie/mật khẩu không được trả qua API, ghi log hoặc chép sang tài khoản khác.
Một nguồn chỉ hiện một kết quả cho sản phẩm và tài khoản nhận đang chọn. **Thử lại** hoặc **Mở cửa sổ chờ xác minh** cập nhật chính thẻ đó; bấm lặp khi đang chạy/đã xong không gọi tìm lần nữa. Muốn tìm mới, gửi yêu cầu mới hoặc chọn nguồn khác. Các thông báo kiểm tra/đăng nhập nằm tại **Kênh tìm kiếm**, không lẫn với lịch sử sản phẩm. Lỗi trùng cũ được gộp khi hiển thị, dữ liệu và video đã chọn vẫn giữ nguyên.

### Quy tắc gắn giỏ hàng affiliate vào video (2026-10-11)

1. **Quy tắc chặn đăng bắt buộc:** Bất kỳ video nào thuộc luồng bán hàng (có `product_binding`) khi đăng bài qua TikTok Studio **bắt buộc phải gắn được giỏ hàng**. Nếu `_try_attach_product_anchor` không tìm thấy sản phẩm trong Showcase của kênh, hệ thống lập tức dừng lại, trả về lỗi `anchor_missing` kèm thông báo *"Chưa gắn được giỏ hàng... Dừng đăng để bảo vệ hoa hồng!"*. Tuyệt đối không tự ý bấm đăng video chay.
2. **Đảm bảo 100% gắn được sản phẩm:** Hệ thống ưu tiên đọc danh mục sản phẩm từ Showcase thực tế của tài khoản (lưu trong `commission_links` kèm mã Showcase ID số). Khi tìm kiếm sản phẩm trong TikTok Studio, việc dùng trực tiếp Showcase ID số đảm bảo 100% kết quả trả về chính xác sản phẩm đó trong Showcase, chọn radio và hoàn tất gắn giỏ hàng.

## Kiểm giỏ hàng với nội dung (2026-10-13)
Tìm tay, chọn video và hàng loạt dùng một bộ resolver. Cần mã Shop số của đúng tài khoản, hãng/model/biến thể cụ thể và một sản phẩm catalog duy nhất; tên chung, số lượt thích hoặc trùng một từ không được tự gắn. Các mã cũ như Windbreaker/Backpack chưa hợp lệ, không tự đăng. Shortlink đã lưu vẫn cần đọc ID và tên Showcase thật, không được coi là đã resolve chỉ từ dữ liệu lưu.
Thành phẩm có giỏ được kiểm qua hình ảnh nhãn/bao bì gốc. Kết quả unknown/different giữ Cần xem, không chịu ảnh hưởng bởi việc tắt duyệt chung. Bằng chứng pin hash, binding, mã Shop và tài khoản; thay đổi phải kiểm lại. Bấm Thêm trong Studio chỉ thành công khi đọc lại được đúng ID. Nếu Studio không cung cấp ID để kiểm, lượt dừng trước Đăng.
Kiểm AI có thể thiếu dữ liệu hoặc nhận sai; không phải bảo đảm tuyệt đối về hàng hóa. Ca đăng thật cần đối chiếu video và SKU cụ thể, rồi kiểm giỏ trên bài mới. Chưa có ca được chủ chỉ định cho phase này.
