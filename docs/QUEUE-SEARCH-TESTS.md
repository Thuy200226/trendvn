# Biên bản thử Hàng đợi và tìm kiếm — 2026-10-07

Phân biệt thử trên Chrome thật với tìm/đăng thành công trên nền tảng thật. Phiên bản đang chạy: 1.9. Kế hoạch: [QUEUE-SEARCH-PLAN.md](QUEUE-SEARCH-PLAN.md).

## Kiểm tra cô lập và bố cục

- Nền trước thay đổi: 901 test host, một lỗi sẵn có về tar/quyền đọc trên macOS, 18 bỏ qua do host thiếu ffmpeg.
- 923/923 test trong Docker, không bỏ qua; dựng, giải mã, phụ đề, âm thanh gốc và dấu vân tay bằng ffmpeg thật đều đạt. Bao gồm năm test xóa bài riêng: chờ hydration, chặn đổi bài, phân biệt thất bại trước click/chưa rõ sau click và xác nhận thành công.
- 120/120 bước trên Chrome thật, bảy viewport 320–1440 px: sáu mục điều hướng, không tràn ngang, ô chạm tối thiểu 44 px, điều khiển chung, hủy/xác nhận, thao tác từng video, lịch sử, tệp/dán/kéo, giữ bản nháp khi phản hồi về muộn. Agent và dữ liệu của bộ này là fixture riêng, không chứng minh tìm kiếm nền tảng thành công.
- Lint, định dạng và doclint đạt. Rà soát độc lập chỉ-đọc đã sửa các lỗi tham chiếu lượt tìm, tranh chấp tài khoản, nguồn Instagram không thuộc truy vấn, bảo toàn bản nháp và kiểm lại đúng mã bài trước xóa.
- Migration bản sao CSDL thật: 8 → 10, `integrity_check=ok`, giữ nguyên 172 jobs, 2 tin chat, 1 tài khoản, 0 link hoa hồng. Bản sao được dọn sau thử.

## Thử hệ thống và tài khoản thật

| Ca thử | Quan sát | Kết luận |
|---|---|---|
| TikTok: chữ MCHOSE ACE68, thể loại kiến thức, bán hàng điện tử | Truy vấn chứa model + thể loại + ngành hàng + ý định review; TikTok đòi xác minh | Truy vấn thật đạt; lấy video chưa đạt |
| Douyin: cùng sản phẩm | Truy vấn `迈从 ACE68 磁轴键盘 科普 电子产品 数码配件 好物 推荐`; nền tảng đòi xác minh | Từ khóa Trung giữ đúng model; lấy video bị chặn |
| TikTok sau chủ báo đã xác minh | Tìm lại `mchose ace68`, không nhận được video từ phản hồi nguồn | Chưa thể nghiệm thu tìm thành công |
| Ảnh bàn phím chủ đính kèm + tên ACE68 | Gemini thật nhận ảnh là KZZI K68; giao diện cảnh báo mâu thuẫn, giữ MCHOSE ACE68 để tìm | Cảnh báo mâu thuẫn đạt; chưa chứng minh ảnh đúng ACE68 |
| Nguồn tự động | Tình trạng các nguồn chưa sẵn sàng nên báo cần kiểm tra/đăng nhập | Không âm thầm tìm bằng hồ sơ khác |
| Instagram chưa đăng nhập | Báo cần đăng nhập, không có kết quả giả | Nhánh thiếu phiên đạt; tìm thành công chưa thử được |
| Kuaishou đăng nhập | Cửa sổ mở cho chủ, hết thời gian chưa ghi nhận phiên | Cần chủ hoàn tất đăng nhập để nghiệm thu |
| Xóa riêng lịch sử lỗi Instagram/Douyin | Xóa được riêng lượt đã chọn; lượt sản phẩm khác còn nguyên | Thử thật đạt |
| Đính kèm ảnh qua trình chọn tệp | Hiện tên/tệp 230 KiB, gửi được vào nhận diện thật | Thử thật đạt |
| Xem thử video tự tạo | Tải lên và điền caption trong TikTok Studio, dừng trước Đăng | Thử thật đạt |
| Đăng đúng một bài tự tạo | TikTok và hồ sơ xác nhận bài 7693824713411317013 trên @bubituean | Thử thật đạt |
| Xóa bài thử qua ứng dụng | Chưa thấy menu quản lý riêng của bài; dừng trước click xóa | Chưa nghiệm thu thành công; không báo đã xóa |

Bài thử duy nhất: https://www.tiktok.com/@bubituean/video/7693824713411317013 — “Video kiểm thử TrendVN”. Không dùng bài cũ của chủ để thử xóa. Không bật Tự đăng hoặc lịch mới.

Các thao tác chọn/tải video sản phẩm thật rồi xử lý chưa thử thành công vì nguồn không trả ứng viên. Logic có regression cô lập, nhưng cần lượt tìm thật thành công để nghiệm thu chuỗi này. Bốn nguồn không được coi là đã hoạt động đầy đủ chỉ vì có parser và nút đăng nhập.

Không có dữ liệu doanh số/hoa hồng đã xác minh trong lần thử này. Chế độ bán hàng xếp theo độ khớp và tương tác thực đọc được, không chứng minh “bán chạy nhất”. Tài khoản nhà sáng tạo không tự cung cấp quyền API/giỏ hàng; không khẳng định đăng kèm sản phẩm hoạt động.

## Sự cố kiểm thử và khôi phục

Khi tạo bản ghi của clip thử, mở SQLite từ macOS trong lúc worker Docker đang giữ WAL gây lỗi I/O do hai kernel không dùng chung khóa. Đã khởi động lại riêng worker, kiểm `integrity_check=ok`, giữ 172 jobs cũ và một job thử riêng. Không mở CSDL đang chạy từ host nữa; mọi kiểm tra live thực hiện trong container hoặc qua ứng dụng. Một lượt tìm bị gián đoạn được ghi lỗi rõ ràng, không nhân kết quả.

Hệ thống đã cập nhật qua cửa lệnh của dự án; doctor báo mọi mục bắt buộc ổn. Nguồn Mỹ vẫn thiếu proxy Mỹ; Tự đăng tắt. Không cam kết chính xác 100% mọi sản phẩm hoặc mọi tài khoản khi chưa có bằng chứng nền tảng.

## Bổ sung nghiệm thu Phase N

Sau chủ xác minh Douyin, lượt 21 nhận 16 video thật cho `迈从 ACE68 磁轴键盘`. Bốn ứng viên đầu có hai ca cần chặn thêm: ACE75 nhắc ACE68 và ACE68V2 sát chữ Trung. Luật được sửa và kiểm lại cả thẻ đã lưu, không chỉ lượt tìm mới. Biến thể GT/Air2/V2 còn lại đã bị loại từ trước; không coi tỷ lệ từ khóa là xác suất đúng sản phẩm.

Chủ xác nhận video `7627431070878744296` (review ACE68 sau một năm): tải thật vào queued/main thành công. Bấm xử lý riêng chỉ nhận video này; Gemini quá tải, kết quả “1 chờ Gemini hết quá tải”, video trở về chờ. Chưa có bằng chứng dựng thành công, không tự đăng video nguồn này.

Xóa lịch sử thật: gốc 6 và con 7/10 biến mất cùng nhau, giữ lượt Douyin đang chạy, không tái xuất sau reload. Ô tích bán hàng có phần vẽ tối đa 24 px/vùng chạm ≥44 px. Tải hoàn tất có fragment hàng chờ riêng để giữ draft. Bỏ ứng viên lưu rejected để lần tìm sau không nhận lại; regression gồm cả hai thứ tự race chọn/bỏ.

942/942 test Docker đạt, không bỏ qua; 123/123 kiểm tra Chrome đạt, gồm giữ phản hồi GET trước thao tác rồi tải đến queued mà không reload. Rà độc lập tìm lỗi dấu gạch nối model, tombstone bỏ ứng viên và coalescing GET cũ; đã sửa và có regression. Xóa bài thử vẫn chưa thành công: Studio chưa lọc còn duy nhất bài khi dùng toàn caption; dừng trước Xóa, giữ bài và lịch sử. Trạng thái này phải cập nhật khi có bằng chứng thật mới.

19:15: tải ACE68 thật xác nhận tệp nguồn 22.961.755 byte; bỏ ACE75 thật, thẻ biến mất và job rejected không tệp. Đọc bộ lọc trên hai ID/URL thật: loại 2, còn 0 mới. Xóa bài thử đã bấm confirm trong Studio; không bắt toast nên giữ unknown. TikTok công khai báo không khả dụng, chủ tự kiểm tra xác nhận đã xóa. Bổ sung UI chủ chốt kết quả để cập nhật mà không gọi agent/xóa lại. Docker cuối: 946/946, 0 bỏ qua, ffmpeg đạt. Chrome cuối: 131/131 đã đạt, gồm cả ca notice chỉ chứa chữ ẩn. Giữ rõ nguyên nhân test từng thất bại và đã sửa ở ROADMAP.

Sau update/doctor: thao tác “Đã kiểm tra: bài đã xóa” trên đúng dòng bài thử, xác nhận URL 7693824713411317013. UI thật ghi deleted, lý do “Chủ đã kiểm tra: bài đã xóa trên TikTok”; không còn nút xóa. Không gửi thêm tác vụ agent. Kết quả xóa thật được chốt bằng kiểm tra của chủ; observer toast mới chỉ được kiểm trên Chrome/dữ liệu thử, không đăng thêm clip để thử lại.

Kết quả cuối: lint/doclint/diff-check đạt; 946/946 Docker (0 bỏ qua), ffmpeg thật đạt; Chrome 131/131 ở bảy viewport trên dữ liệu riêng. Đã rà tĩnh/động/độc lập. Bốn nền tảng chưa cùng đạt: Douyin có kết quả/tệp thật; tìm TikTok chưa thành công, Kuaishou/Instagram thiếu phiên, nguồn Mỹ thiếu IP Mỹ. Tài khoản nhà sáng tạo chưa có Shop API nên chưa xác nhận tự động hoa hồng hoặc gắn giỏ. Không báo các phần này là đạt.
