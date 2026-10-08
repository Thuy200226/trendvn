# Bản đồ thao tác, vị trí cuộn và thông báo phản hồi (Scroll & Feedback Map)

Tài liệu này chuẩn hóa và ánh xạ (map) chi tiết mọi thao tác người dùng, vị trí cuộn trang mong muốn, và thông tin thông báo phản hồi trên toàn bộ giao diện TrendVN.

---

## 1. Nguyên tắc hoạt động cốt lõi

1. **Không giật trang lên đỉnh đầu (No blind scroll to top):**
   - Khi người dùng gửi form, xác nhận thao tác hoặc hệ thống cập nhật live, không ép cuộn về `(0, 0)` trừ khi người dùng chủ động bấm vào thanh menu điều hướng tab trên cùng (`.topnav`) hoặc thanh menu dưới (`.bottomnav`).
2. **Ưu tiên cuộn đến thông báo hoặc vị trí vừa thao tác:**
   - Hệ thống lưu trữ `trendvn.scroll.y` và `trendvn.scroll.target` (ID của hàng/thẻ/form vừa bấm) vào `sessionStorage`.
   - Sau khi trang chuyển hướng 303 hoặc render lại:
     - Nếu có banner thông báo kết quả (`.flash`, `.banner.good`, `.banner.warn`), tự động cuộn mượt (`scrollIntoView({behavior: 'smooth', block: 'nearest'})`) tới thông báo.
     - Nếu có target ID vừa thao tác (ví dụ hàng bài đăng vừa bấm xóa), cuộn đúng đến phần tử đó.
     - Nếu không có ID cụ thể, khôi phục đúng tọa độ `scrollY` trước khi submit.
3. **Phản hồi tức thì tại chỗ (Local Inline Feedback):**
   - Các thao tác trong chat (chọn video, bỏ ứng viên, sao chép link, gửi tin nhắn) hiển thị trạng thái `Đang thực hiện…` / `Đã thực hiện` ngay tại bong bóng tin nhắn (`data-action-feedback`), không làm dịch chuyển khung chat.

---

## 2. Bảng ánh xạ theo từng Tab và Thao tác

| Tab / Vị trí | Thao tác người dùng | Cơ chế kích hoạt | Anchor / Target Scroll | Thông báo hiển thị | Trạng thái hệ thống sau thao tác |
|---|---|---|---|---|---|
| **Tổng quan (`#home`)** | Bật/tắt công tắc Xử lý video | Form POST `/settings` | `#control` hoặc giữ nguyên `scrollY` | Flash banner: "Đã lưu cài đặt" | Trạng thái nút đổi ngay (Đang bật / Đang tắt), badge cập nhật |
| **Tổng quan (`#home`)** | Bật/tắt công tắc Tự đăng | Form POST `/settings` có popup xác nhận | `#control` | Flash banner: "Đã lưu cài đặt" | Chuyển chế độ giữa "Đang tự động hoàn toàn" và "Chế độ thủ công" |
| **Tổng quan (`#home`)** | Bấm "Thu thập và xử lý ngay" | Form POST `/task` (`kind=update`) | `#control` -> `.taskpanel` | Flash banner: "Đã bắt đầu. Tiến độ hiện ngay trên trang..." | Task panel hiện tiến trình 2 bước: Thu thập video -> Xử lý video |
| **Hàng đợi (`#queue`)** | Gửi tin nhắn tìm kiếm (chữ/ảnh) | Form POST `/chat/send` (AJAX) | `#chat-thread` (cuộn xuống cuối chat) | Phản hồi inline trong thread: bong bóng người dùng + bot đang nhận diện | Bot phân tích sản phẩm (Gemini sinh `query_zh` và Latin query) |
| **Hàng đợi (`#queue`)** | Tick xác nhận video và bấm "Chọn và tải" | Button `data-chat-act="pick"` | Giữ nguyên vị trí bubble video đang xem | Feedback inline: `Đang gửi…` -> `Đã thực hiện` -> Thẻ chuyển thành `Chờ tải video đã chọn` | Video được đưa vào `queued`, hàng đợi Chờ xử lý tăng số lượng |
| **Hàng đợi (`#queue`)** | Bấm "Bỏ ứng viên" | Button `data-chat-act="dismiss"` | Giữ nguyên vị trí trong chat thread | Feedback inline: thẻ ứng viên đóng lại, ghi nhận rejected | Video bị loại trừ vĩnh viễn, không tải lại |
| **Hàng đợi (`#queue`)** | Bấm "Xử lý 1 video này" | Form POST `/task` (`kind=process_one`) | `#queue-live` -> `.taskpanel` | Flash banner: "Đã bắt đầu..." + Task panel hiện từng giai đoạn | Video chuyển sang `processing` -> `awaiting_approval` hoặc `ready` |
| **Hàng đợi (`#queue`)** | Bấm "Bỏ chờ" (xóa khỏi hàng đợi) | Form POST `/decide` (`action=discard`) | `#queue-live` | Flash banner: "Đã ghi nhận quyết định của bạn" | Video chuyển sang `discarded`, biến mất khỏi bảng chờ xử lý |
| **Đăng bài (`#publish`)** | Sửa mô tả / hashtag và bấm "Lưu mô tả" | Form POST `/caption` | Thẻ `.ready` của đúng video | Flash banner: "Đã lưu mô tả và hashtag" | Cập nhật số ký tự, hashtag count và lưu vào database |
| **Đăng bài (`#publish`)** | Bấm "Duyệt cho lịch tự đăng" | Form POST `/decide` (`action=approve`) | Thẻ `.ready` kế tiếp hoặc danh sách Đăng bài | Flash banner: "Đã ghi nhận quyết định của bạn" | Trạng thái chuyển từ `awaiting_approval` sang `ready` |
| **Đăng bài (`#publish`)** | Bấm "Đăng ngay" (đăng lên TikTok) | Form POST `/task` (`kind=publish`) có popup xác nhận | Thẻ `.ready` -> Task panel tiến trình đăng | Flash: "Đã bắt đầu..." -> Task panel hiển thị kết quả xác nhận | Agent mở trình duyệt đăng bài -> nếu có link thì lưu vào Đã đăng |
| **Đã đăng (`#posted`)** | Bấm "Đọc lượt xem ngay" | Form POST `/task` (`kind=stats`) | `#posted` -> `.taskpanel` | Flash banner: "Đã bắt đầu..." + Task panel | Agent đọc số view, tim từ hồ sơ TikTok và cập nhật bảng |
| **Đã đăng (`#posted`)** | Bấm "Xóa bài TikTok" | Form POST `/post-delete` có popup xác nhận | Dòng `tr` của bài đăng trong bảng | Flash: "Đã bắt đầu..." -> Task panel hiển thị tiến trình xóa | Agent thử mở trang video, fallback TikTok Studio, bấm Xóa và đợi xác nhận |
| **Đã đăng (`#posted`)** | Bấm "Đã kiểm tra: bài đã xóa" | Form POST `/post-delete-checked` (`outcome=deleted`) | Dòng `tr` của đúng bài đăng đó | Flash banner: "Đã cập nhật trạng thái bài đăng" | Trạng thái đổi thành "Đã xóa trên TikTok · Chủ đã kiểm tra: bài đã xóa" |
| **Đã đăng (`#posted`)** | Bấm "Thử xóa lại" | Form POST `/post-delete` | Dòng `tr` của bài đăng đó | Flash: "Đã bắt đầu..." | Agent mở lại Studio để thực hiện xóa |
| **Cần xem (`#attention`)** | Giải quyết video cần duyệt (Duyệt / Bỏ) | Form POST `/decide` | `#attention` | Flash banner: "Đã ghi nhận quyết định của bạn" | Badge tab Cần xem giảm, video chuyển trạng thái tương ứng |
| **Thêm (`#more`)** | Lưu khóa Gemini API | Form POST `/setup` | `#settings` (khung khóa Gemini) | Flash banner: "Đã lưu khóa Gemini" | Kiểm tra kết nối, gỡ cảnh báo khóa bị từ chối nếu có |
| **Thêm (`#more`)** | Lưu cài đặt hệ thống | Form POST `/settings` | `#settings` | Flash banner: "Đã lưu cài đặt" | Cập nhật cấu hình tức thì |
| **Thêm (`#more`)** | Thêm / Lưu tài khoản TikTok | Form POST `/account-add`, `/account-save` | `#accounts` | Flash banner: "Đã lưu tài khoản" | Cập nhật danh sách tài khoản và phân quyền |

---

## 3. Các điểm lưu ý cho từng thiết bị

- **Màn hình điện thoại (<370px, 375px - 414px):**
  - Thanh điều hướng `.bottomnav` cố định dưới đáy màn hình, luôn có `safe-area-inset-bottom`.
  - Bảng dữ liệu tự động chuyển sang layout dạng thẻ (`card view`), mỗi dòng là một khối độc lập.
  - Ô "Thao tác" được hiển thị tràn 100% chiều rộng card, các nút bấm có chiều cao tối thiểu 44px để dễ chạm.
- **Màn hình máy tính bảng (768px - 860px, 959px):**
  - Không bẻ vụn chữ trên các cột chỉ số (Lượt xem, Tim, Ngày đăng).
  - Khung xem trước video `.ready` tự co về 1 cột nếu chiều rộng màn hình hẹp, tránh ép cột văn bản mô tả.
- **Màn hình lớn (>=960px, 1200px - 1440px):**
  - Thanh điều hướng trên cùng `.topnav` hiển thị đầy đủ 6 tab trên một hàng duy nhất.
  - Khung chat phân tách rõ ràng 2 cột: Cột chat chính (bên trái) và Cột kênh tìm kiếm + link hoa hồng (bên phải).
