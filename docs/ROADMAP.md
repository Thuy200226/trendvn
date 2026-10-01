# Lộ trình 1.4: các phase và nhật ký rà soát

Tài liệu làm việc: ghi lại yêu cầu, thiết kế từng phase và kết quả 3 vòng rà soát của mỗi phase (để không mất khi làm nhiều phiên).
Quy ước mỗi phase: (1) làm, (2) **rà soát vòng 1 — tĩnh** (đọc lại mã, lint, tài liệu khớp mã), (3) **vòng 2 — động** (chạy thật, đo thật),
(4) **vòng 3 — độc lập** (tác tử chỉ đọc mã, hoặc đối chiếu số liệu đo), (5) sửa mọi phát hiện rồi mới sang phase kế.

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Chạy hoàn toàn từ thư mục mới, dữ liệu mới, thôi dùng thư mục cũ | xong |
| A | Bố cục thư mục và chia module (worker, agent) cho dễ đọc, dễ mở rộng | |
| B | Chất lượng phân tích (giữ nguyên / Vietsub / thuyết minh) và chất lượng video | |
| C | Tìm kiếm và tổng hợp theo chủ đề, đăng nhiều tài khoản theo nhiều chủ đề | |
| D | Hiệu suất và tốc độ | |

## Phase 0 — Chuyển hẳn sang thư mục mới (xong)

- Dừng agent và container của thư mục cũ (theo yêu cầu rõ ràng của chủ), chạy lại bằng `./trendvn install` từ thư mục mới với **cơ sở dữ liệu mới**.
- Giữ lại hai thứ khó tạo lại: khóa Gemini và phiên đăng nhập TikTok (đã kiểm tra `logged_in: true`); mọi dữ liệu video, hàng đợi, n8n cũ không mang sang.
- Việc xóa thư mục cũ và volume n8n cũ do chủ tự làm (xem hướng dẫn cuối báo cáo); thư mục mới không phụ thuộc vào chúng.
- Kiểm tra: `doctor` xanh (trừ ổ đĩa đầy và việc của người dùng), thu thập thật từ hệ thống mới (Douyin đọc 49, Kuaishou 97), phiên TikTok còn đăng nhập.
- Ổ đĩa máy chỉ còn khoảng 2 GB (99% đầy): rủi ro thật cho việc dựng video; xem phần cuối báo cáo.
