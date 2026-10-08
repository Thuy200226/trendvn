# Kế hoạch Hàng đợi, tìm kiếm và quản lý bài đăng

Ngày cập nhật: 2026-10-07. Trạng thái: đã triển khai bản 1.9; nghiệm thu nền tảng còn bị chặn. Biên bản: [QUEUE-SEARCH-TESTS.md](QUEUE-SEARCH-TESTS.md).

## 1. Mục tiêu và đường đi của người dùng

Một tab **Hàng đợi** chứa ba khu vực: **Tìm video → Ứng viên → Chờ xử lý**. Video xử lý xong sang **Đăng bài**, đăng thành công sang **Đã đăng**. Thanh điều hướng còn sáu mục: Tổng quan, Hàng đợi, Đăng bài, Cần xem, Đã đăng, Thêm. Đường dẫn `#search` cũ vẫn mở được khu vực tìm kiếm trong Hàng đợi.

Người dùng chọn tài khoản đích, nguồn và thể loại; có thể nhập chữ, dán đường dẫn, dán ảnh hoặc kéo tệp vào. Bật **Tìm bán hàng** thì hiện ngành hàng. Xem kết quả, bỏ ứng viên không phù hợp hoặc chọn tải về. Video tải thành công vào Chờ xử lý; có thể xử lý từng video hoặc xử lý theo lô. Video đã đăng có hành động xóa đúng bài TikTok và cập nhật lại trạng thái trong ứng dụng.

## 2. Giao diện và component chung

- Gom component icon, nút, nút chỉ có icon, trường nhập, ô số, textarea, select, checkbox/công tắc, nhãn trường, tab, badge trạng thái, bảng, hộp xác nhận và phản hồi lỗi/thành công. Các tab dùng chung component và các biến màu/kích thước/khoảng cách; không sao chép một kiểu điều khiển cho từng màn hình.
- Select giữ khả năng thao tác bằng bàn phím, thêm mũi tên thống nhất, khoảng trống cho chữ và trạng thái disabled/error/focus. Nút làm mới dùng SVG đồng bộ với bộ icon, có nhãn cho trình đọc màn hình và trạng thái đang tải.
- Sáu mục điều hướng chia đều chiều ngang; chọn mục bằng màu và dấu chỉ thị, không làm chiều cao/chiều rộng thay đổi. Focus bàn phím rõ, không bị cắt hay làm bố cục nhảy.
- Hiệu ứng ngắn và thống nhất; tôn trọng tùy chọn giảm chuyển động. Vùng nhấn ít nhất 44 px, nội dung dài không đẩy trang tràn ngang.
- Giữ nội dung đang nhập, tệp đã chọn, lựa chọn ứng viên và vị trí cuộn khi cập nhật kết quả nền. Không tự kéo người đang đọc lịch sử xuống cuối.

**Nghiệm thu:** kiểm tra bảy kích thước màn hình, điều hướng bằng chuột/bàn phím, focus, select dài, dữ liệu rỗng/nhiều dòng và chế độ giảm chuyển động.

## 3. Tìm kiếm qua tài khoản đã đăng nhập

- Một hồ sơ trình duyệt riêng cho mỗi tài khoản và mỗi nguồn TikTok, Douyin, Kuaishou, Instagram. Hiển thị nguồn nào đã đăng nhập, hết phiên, đang kiểm tra hoặc cần xác minh.
- Phân biệt tài khoản TikTok nhận video với danh tính tài khoản nguồn. Biên bản thử ghi danh tính thực đọc được; có cookie nhưng chưa đọc được tên chỉ là có dấu hiệu phiên, không phải đã xác minh đúng người. Thử cả đổi tài khoản giữa tìm và tải.
- Tìm bằng phiên tương ứng với lựa chọn hiện tại; không âm thầm dùng hồ sơ tài khoản khác. Chọn thể loại mặc định theo cấu hình tài khoản; người dùng đổi được trước khi tìm.
- **Yêu cầu bổ sung của chủ:** thể loại, từ khóa và thông tin sản phẩm phải tạo thành truy vấn được nhập vào chức năng tìm video của chính nền tảng, sau đó thực hiện tìm kiếm. Không chỉ dùng chúng để lọc danh sách đã thu thập. Lưu/hiển thị truy vấn thực tế của từng nguồn để kiểm tra.
- Nguồn chưa đăng nhập hướng dẫn mở đăng nhập, không báo lỗi nội dung video. CAPTCHA hoặc giới hạn truy cập được báo đúng nguồn và dừng tại đó; giữ các kết quả của nguồn khác nếu có.
- Đầu vào chữ/ảnh/tệp/đường dẫn được chuẩn hóa thành thông tin sản phẩm và truy vấn phù hợp từng nguồn. Giữ nguyên thương hiệu/mã model, bổ sung từ khóa tiếng Trung cho nguồn Trung Quốc; không dịch mất `MCHOSE ACE68`.
- Nếu nguồn không hỗ trợ tìm bằng ảnh, ảnh được dùng để nhận diện thuộc tính và tạo từ khóa. Hiển thị từ khóa để người dùng kiểm tra/sửa; không suy đoán mã model chỉ từ hình dáng. Tên người dùng nhập được ưu tiên; nhận diện mâu thuẫn phải thể hiện rõ.
- Phân biệt kết quả khớp model, tương tự và khác model. Không đưa video khác model vào luồng tự động như kết quả khớp chính xác.

**Nghiệm thu:** bốn nguồn × có phiên/chưa đăng nhập/hết phiên/cần xác minh; chữ, link, ảnh, tệp, hỗn hợp, đầu vào rỗng/sai/quá giới hạn. Trường hợp mẫu: “bàn phím mchose ace68” cùng ảnh, kiểm tra truy vấn và model của kết quả.

## 4. Tìm video bán hàng

- Công tắc bật/tắt; khi bật mới hiện ngành hàng. Ngành hàng ban đầu gồm điện tử/phụ kiện, làm đẹp, thời trang, gia dụng, mẹ và bé, thực phẩm, thể thao và đồ thú cưng.
- Có thể tìm theo ngành hàng mà không cần nêu một sản phẩm cụ thể; khi có tên/model thì kết hợp cả hai. Chuyển chế độ không làm mất thông tin đã nhập.
- Kết quả ghi rõ căn cứ sắp xếp. Chỉ gọi **bán chạy** khi nguồn cung cấp số bán/bảng xếp hạng có thể xác minh; nếu chỉ có lượt xem/thích thì ghi **video có tương tác cao**, không quy đổi thành doanh số.
- Quyền nhà sáng tạo, hoa hồng và quyền gắn sản phẩm là các thông tin riêng: chỉ hiển thị số hoa hồng hoặc khả năng gắn sản phẩm khi đọc được từ tài khoản/nguồn thực. Tài khoản nhà sáng tạo không đồng nghĩa có App key hay quyền API.
- Kiểm tra hồi quy link hoa hồng đã lưu và liên kết sản phẩm với video qua các bước chọn/xử lý/đăng. Bản hiện tại đã gỡ đăng kèm giỏ hàng từ phiên bản 1.7; không coi yêu cầu giao diện lần này là bằng chứng tính năng đó đang hoạt động.

**Nghiệm thu:** bật/tắt, từng ngành hàng, không có từ khóa, có model, không có số bán, kết quả rỗng và nguồn trả lỗi một phần. Không tạo số doanh thu/hoa hồng giả.

## 5. Ứng viên và Chờ xử lý

- Mỗi ứng viên có **Bỏ ứng viên** và **Đưa vào chờ xử lý**. Hành động thứ hai tải đúng video; chỉ đổi sang Chờ xử lý sau khi tệp tải hợp lệ. Tải hỏng cho phép thử lại và giữ lý do.
- Mỗi video chờ có **Xử lý video này** và **Bỏ chờ**. Xử lý riêng phải nhận đúng mã video, không lấy video đầu hàng đợi thay thế. Hành động theo lô vẫn hoạt động.
- Chống nhận cùng video hai lần khi bấm nhanh hoặc tác vụ nền chạy cùng lúc. Video đang được xử lý không bị bỏ ngang bởi thao tác bỏ chờ.
- Bỏ khỏi hàng đợi là thay đổi trạng thái có lý do, giữ thông tin để tránh thu thập lại ngay; không xóa bài TikTok.
- Bỏ ứng viên/bỏ chờ tác động bản ghi video chung trong hệ thống; những lần thu thập lại cùng nguồn/mã không tự đưa nó về ứng viên. Muốn lấy lại cần thao tác khôi phục có chủ ý; không âm thầm thay quyết định đã bỏ.

**Nghiệm thu:** hai video A/B, bấm xử lý B thì chỉ B được nhận; tải lỗi, bấm lặp, hai tác vụ tranh cùng video, bỏ ứng viên, bỏ chờ và thao tác trên video đang xử lý.

## 6. Lịch sử tìm kiếm và chống trùng

- Mỗi lượt tìm có nút xóa riêng; xóa cả câu hỏi và câu trả lời thuộc lượt đó. Giữ chức năng xóa toàn bộ lịch sử đã hoàn tất.
- Xóa lịch sử không làm mất video đã chọn/tải hoặc liên kết đang được tác vụ sử dụng. Lượt đang chạy có trạng thái rõ ràng; không tạo bản ghi mồ côi.
- Mỗi lần gửi có mã yêu cầu để máy chủ nhận diện gửi lại; bấm đúp hoặc gửi lại cùng yêu cầu không tạo hai lượt. Một yêu cầu mới có nội dung giống yêu cầu cũ vẫn được phép.
- Mỗi tin nhắn có mã ổn định. Chỉ một lần cập nhật nền chạy tại một thời điểm; phản hồi cũ không được ghi đè phản hồi mới. Giữ vị trí cuộn và trạng thái chọn khi dựng lại kết quả.

**Nghiệm thu:** bấm đúp, mạng chậm, phản hồi đảo thứ tự, tải lại trang, hai lượt nội dung giống nhau nhưng mã khác nhau; xóa một lượt không xóa lượt bên cạnh hoặc phá video chờ tải.

## 7. Xóa bài đã đăng trên TikTok

- Từ Đã đăng, hiển thị bài, đường dẫn và tài khoản trong hộp xác nhận. Kiểm tra bài vẫn thuộc bản ghi và tài khoản đó trước khi thực hiện.
- Mở đúng hồ sơ Chrome, kiểm tra danh tính tài khoản đang đăng nhập và đúng mã bài. Không thao tác khi sai tài khoản, hết phiên hoặc cần xác minh.
- Ghi nhận trạng thái đang xóa trước thao tác; khóa để hai yêu cầu không cùng xóa một bài. Không tự lặp lại thao tác khi kết quả từ TikTok chưa rõ.
- Chỉ chuyển ứng dụng sang Đã xóa sau bằng chứng TikTok xác nhận xóa. Lỗi trước thao tác cho phép thử lại; kết quả không chắc chắn hiển thị Cần kiểm tra, giữ đường dẫn và lý do.
- Giữ lịch sử nguồn, tài khoản và thao tác để đối chiếu; không xóa bản ghi khiến hệ thống thu thập/đăng lại cùng video.
- Giữ nguyên dấu mốc/số lần đã đăng và hạn mức sau khi xóa. Trang không truy cập được hoặc bài biến mất không đủ chứng minh xóa thành công: phân biệt riêng tư, bị gỡ và lỗi mạng.

**Nghiệm thu:** đúng/sai tài khoản, bài không khớp, hết phiên, bấm lặp, lỗi trước xác nhận, mất kết nối sau xác nhận và TikTok xác nhận thành công.

## 8. Kịch bản kiểm thử và triển khai

1. Ghi nền trước thay đổi: đã chạy 901 test trên máy; một lỗi sẵn có về quyền đọc tệp của tar trên macOS, 18 test bỏ qua do thiếu ffmpeg. Các lỗi mới phải được tách khỏi nền này.
2. Mỗi thay đổi trạng thái, chống trùng, quyền tài khoản và xóa có test hồi quy trên CSDL/thư mục riêng; không dùng hàng đợi thật làm fixture. Nếu đổi schema, chạy migration trong giao dịch và thử trên bản sao CSDL thật.
3. Rà mã/lint/tài liệu, chạy test trong môi trường có ffmpeg, kiểm tra luồng bằng Chrome thật ở bảy kích thước. Test tự động trên dữ liệu riêng giúp chặn lỗi trước khi thử thật, nhưng không thay thế nghiệm thu trên hệ thống/nền tảng thật theo yêu cầu của chủ.
4. Thử tìm thật theo các nguồn đăng nhập được. Ghi số kết quả, truy vấn, trạng thái nguồn và thời gian; bị CAPTCHA/giới hạn thì ghi chưa kiểm chứng, không biến thành kết quả đạt.
   Thực hiện thật các thao tác: nhập từ khóa/thể loại/sản phẩm vào tìm video, dán/kéo tệp, bật ngành hàng, bỏ/chọn ứng viên, tải, xử lý từng video, bỏ chờ, xóa một lượt lịch sử, kiểm tra không trùng khi gửi nhanh. Mỗi trường hợp phải có kết quả quan sát; nguồn không có phiên phải được chủ đăng nhập trước khi nghiệm thu tìm thành công.
5. **Chủ đã cho phép đăng và xóa bài thật trong lần kiểm thử này, ngày 2026-10-07.** Dùng tối đa một video thử riêng có nội dung/tiêu đề “Video kiểm thử TrendVN”, trên tài khoản đã xác minh `@bubituean`, ghi URL/mã bài mới đăng, xác nhận bài tồn tại rồi xóa chính bài đó bằng chức năng mới. Kiểm tra TikTok và ứng dụng cùng cập nhật; báo URL nếu bài thử chưa xóa được. Không chọn bài cũ của chủ làm mẫu xóa.
6. Chỉ thực hiện bài thử khi tài khoản được xác minh, có quyền đăng và không bị CAPTCHA; nếu cần chủ đăng nhập/xác minh thì giữ trạng thái và báo chính xác bước còn thiếu.
7. Rà soát độc lập bằng tác tử chỉ-đọc sau khi mã ổn định; sửa phát hiện và chạy lại những kiểm tra liên quan. Cập nhật CHANGELOG, tài liệu và ROADMAP.
8. Áp dụng qua `./trendvn update`, kiểm tra cả worker, agent, n8n bằng `./trendvn doctor`; xác nhận phiên bản mới hoạt động tại cổng 5681. Giữ cơ chế sao lưu/phục hồi hiện có.

Biên bản mỗi ca thử thật ghi: thời gian, nguồn/tài khoản, đầu vào, truy vấn đã gửi, kết quả mong đợi, kết quả quan sát, URL/ảnh bằng chứng, thời lượng và lý do bị chặn nếu có. Trạng thái phân biệt **đã triển khai / qua test cô lập / qua thử thật / bị chặn hoặc chưa kiểm chứng**.

## 9. Bảng đối chiếu yêu cầu và tình trạng

| Yêu cầu | Kết quả cần có | Tình trạng |
|---|---|---|
| Gom tìm kiếm vào hàng đợi | Sáu tab, link cũ hoạt động | Đạt Chrome bảy viewport |
| Component và CSS chung | Điều khiển thống nhất, focus/select/reload đẹp và dùng được | Đạt Chrome và lint |
| Tìm theo tài khoản bốn nguồn | Phiên riêng, thể loại, lỗi phiên rõ ràng | Đã triển khai; tìm thật bị xác minh/thiếu phiên |
| Tìm bán hàng | Công tắc, ngành hàng, căn cứ xếp hạng thật | Qua fixture; không có dữ liệu doanh số để chứng minh bán chạy |
| Bỏ/chọn ứng viên | Tải đúng video rồi mới chờ xử lý | Qua regression; chưa có ứng viên thật để nghiệm thu |
| Xử lý/bỏ từng video chờ | Nhận đúng mã, chống tranh chấp | Qua regression và Chrome dữ liệu riêng |
| Xóa một lượt, chống lịch sử trùng | Liên kết lượt và mã yêu cầu ổn định | Qua regression; xóa lượt trên hệ thống thật đạt |
| Xóa bài TikTok và cập nhật ứng dụng | Đúng bài/tài khoản, xác nhận kết quả | Đăng thật đạt; bước xóa đang đối chiếu giao diện TikTok |
| Test nhanh trên Chrome thật | Kịch bản có kết quả và giới hạn được ghi lại | 120/120 bước Chrome; xem biên bản thử nền tảng |

Không coi “qua fixture” là “đã chạy thành công trên TikTok”; không cam kết tìm đúng 100% mọi sản phẩm khi nguồn chặn truy cập hoặc không cung cấp dữ liệu xác minh.
