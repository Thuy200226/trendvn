# Lộ trình 1.4: các phase và nhật ký rà soát

Tài liệu làm việc: ghi lại yêu cầu, thiết kế từng phase và kết quả 3 vòng rà soát của mỗi phase (để không mất khi làm nhiều phiên).
Quy ước mỗi phase: (1) làm, (2) **rà soát vòng 1 — tĩnh** (đọc lại mã, lint, tài liệu khớp mã), (3) **vòng 2 — động** (chạy thật, đo thật),
(4) **vòng 3 — độc lập** (tác tử chỉ đọc mã, hoặc đối chiếu số liệu đo), (5) sửa mọi phát hiện rồi mới sang phase kế.

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Chạy hoàn toàn từ thư mục mới, dữ liệu mới, thôi dùng thư mục cũ | xong |
| A | Bố cục thư mục và chia module (worker, agent) cho dễ đọc, dễ mở rộng | đang rà soát |
| B | Chất lượng phân tích (giữ nguyên / Vietsub / thuyết minh) và chất lượng video | |
| C | Tìm kiếm và tổng hợp theo chủ đề, đăng nhiều tài khoản theo nhiều chủ đề | |
| D | Hiệu suất và tốc độ | |

## Phase 0 — Chuyển hẳn sang thư mục mới (xong)

- Dừng agent và container của thư mục cũ (theo yêu cầu rõ ràng của chủ), chạy lại bằng `./trendvn install` từ thư mục mới với **cơ sở dữ liệu mới**.
- Giữ lại hai thứ khó tạo lại: khóa Gemini và phiên đăng nhập TikTok (đã kiểm tra `logged_in: true`); mọi dữ liệu video, hàng đợi, n8n cũ không mang sang.
- Việc xóa thư mục cũ và volume n8n cũ do chủ tự làm (xem hướng dẫn cuối báo cáo); thư mục mới không phụ thuộc vào chúng.
- Kiểm tra: `doctor` xanh (trừ ổ đĩa đầy và việc của người dùng), thu thập thật từ hệ thống mới (Douyin đọc 49, Kuaishou 97), phiên TikTok còn đăng nhập.
- Ổ đĩa máy chỉ còn khoảng 2 GB (99% đầy): rủi ro thật cho việc dựng video; xem phần cuối báo cáo.

## Phase A — Bố cục và chia module

Làm: hai ứng dụng thành gói Python (`trendvn_worker`, `trendvn_agent`) chia theo việc; file nào cũng một trách nhiệm; hàm dài nhất còn 67 dòng; test chia theo dịch vụ; công cụ định dạng ghim phiên bản; triển khai lại hệ thống đang chạy bằng `./trendvn update` (đã cài lại dịch vụ nền của agent theo bố cục mới).

**Rà soát 1 — tĩnh.** ruff, black (bản ghim), shellcheck, doclint đều sạch; đọc lại hàm dài nhất và tách `process_one` (98 dòng) thành các bước `_source/_look_alike/_voice_or_subtitles/_checked_output/_write_manifest`, `_publish_one` (88 dòng) thành 5 bước. Phát hiện **lỗi do chính việc tách gây ra**: biến cục bộ `shot` che mất hàm `shot()` trong trình đăng (mọi lỗi trước khi bấm Đăng sẽ thành `UnboundLocalError`; mã cũ đặt tên khác nên không bị). Đã sửa bằng cách tách hàm và thêm 11 test chạy trình đăng với trình duyệt giả (mọi nhánh: thiếu ô chọn file, hết hạn đăng nhập, xác minh trước/sau khi bấm, trùng mô tả, bài riêng tư…) và 12 test cho `process_one` với ffmpeg/Gemini giả (trước đó không có test nào gọi thẳng nó).
Bộ kiểm thử bố cục e2e chập chờn một lần khi máy bận (đo khi trang chưa cuộn về đầu): nay đo sau khi trang đứng yên và báo rõ nếu không về đầu; chạy lại 5 lần, kể cả khi máy bị làm bận hết CPU: xanh.

**Rà soát 2 — động.** `./trendvn update` trên hệ thống thật: dịch vụ nền của agent được viết lại sang `-m trendvn_agent`; `doctor` xanh; thu thập thật qua agent mới (Douyin đọc 49, đạt ngưỡng 4, tải 2); `./trendvn test all`: 189 test trên máy và trong image Docker, dựng video thật bằng ffmpeg, 76 kiểm tra Chrome thật ở 7 cỡ màn hình.

**Rà soát 3 — độc lập.** Hai tác tử chỉ đọc mã đối chiếu mã cũ (`9dbd527`) với mã mới. Agent: không có lỗi hay thay đổi hành vi ngoài ý muốn (so sánh AST từng hàm, hằng số, thứ tự thao tác trình duyệt, thời gian chờ, đường dẫn dữ liệu); 6 ghi chú nhỏ đã xử lý: `agent.sh` nay nhận cả tiến trình `server.py` kiểu cũ khi dừng, `SECURITY.md` còn tên cũ (`publisher.py`, `_looks_blocked`) và doclint nay bắt loại lỗi này, test ghi nhầm vào `data/agent/agent.log` thật nay ghi vào thư mục tạm.
