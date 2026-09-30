# Vận hành hằng ngày và xử lý sự cố

## 1. Một ngày điển hình khi đã chạy tự động

| Giờ | Việc xảy ra (không cần bạn) |
|---|---|
| Mỗi 3 giờ | Workflow 01: quét 4 nguồn, chỉ tải video mới nổi (tối đa 3/lần, tổng hàng chờ ≤ 4), xử lý bằng Gemini và ffmpeg |
| Mỗi 30 phút | Workflow 02: hỏi worker có được đăng không. Chỉ khi đang trong giờ vàng (mặc định 11–14h và 19–23h), chưa đủ 2 bài hôm nay, cách bài trước ≥ 3 giờ |
| 23:30 | Workflow 03: đọc lượt xem bài đã đăng, cập nhật trọng số nguồn, gửi tóm tắt ngày |

Bạn chỉ cần mở bảng điều khiển (**http://localhost:5681**) khi nhận thông báo, hoặc thỉnh thoảng để xem hiệu quả.

## 1b. Các nút thao tác tay

Bảng điều khiển có sáu tab: **Tổng quan**, **Hàng đợi** (video đang chờ xử lý), **Đăng bài** (video đã xử lý xong), **Cần xem** (việc cần bạn quyết định), **Đã đăng**, **Thêm** (nguồn, cài đặt, thông báo, nhật ký). Các nút chỉ là bổ sung: lịch n8n vẫn thu thập, xử lý và đăng như cũ.

- **Tổng quan → ▶ Bắt đầu:** thu thập video mới rồi xử lý. Có thể rời trang, tác vụ chạy nền; trang tự làm mới khi xong. Nếu "Xử lý video" đang tắt, nút chỉ thu thập và nói rõ điều đó.
- **Đăng bài:** mỗi video đã xử lý là một thẻ có xem trước, ô mô tả và hashtag (số ký tự, số hashtag, kiểm tra chất lượng cập nhật khi gõ), các nút Đăng ngay, Xem thử, Lưu mô tả, Duyệt cho lịch tự đăng (chỉ khi bật "Duyệt tay"), Bỏ video. Bấm Đăng ngay có hộp xác nhận nêu rõ tài khoản, chế độ hiển thị và cảnh báo nếu đã đủ bài hôm nay hoặc đang ngoài giờ vàng.
- **Khi có việc đang chạy** (của nút hoặc của lịch): các nút cùng loại bị khóa và có dòng giải thích, để không thể bấm chồng. Việc xử lý (Gemini) và việc dùng trình duyệt là hai khóa riêng nên có thể chạy song song.
- **Video lỗi khi đăng:** lỗi lần 1–2 thì nghỉ 1 giờ rồi lịch thử lại; lỗi 3 lần thì chuyển sang "Cần xem" kèm thông báo. Ở đó bấm **↩ Đưa về sẵn sàng đăng** (video đã dựng xong, không tốn thêm lượt Gemini) hoặc **Duyệt lại** (dựng lại từ đầu). Nút Đăng ngay của bạn không bị giới hạn nghỉ 1 giờ.

## 2. Đọc bảng điều khiển

Từ trên xuống:

1. **Thanh trạng thái:** xanh = đang tự động hoàn toàn; cam = còn việc cần xem hoặc thiếu thiết lập.
2. **Thẻ Tình trạng:** ba dòng Thu thập video · Đăng TikTok · Giờ vàng (đang mở hay mở lúc mấy giờ). Mỗi dòng nằm gọn trong thẻ, không cuộn ngang.
3. **Thiết lập n/6:** danh sách việc để đạt tự động hoàn toàn, mỗi mục chưa xong có gợi ý ngay bên dưới.
4. **Luồng xử lý:** Ứng viên → Chờ xử lý → Sẵn sàng → Đã đăng. Chạm vào từng bước để mở đúng tab (Hàng đợi, Đăng bài, Đã đăng).
5. **Cần xem:** gom ba loại việc, xem bên dưới.
6. **Tab Hàng đợi** và **Đăng bài** có hướng dẫn riêng khi trống (xem mục dưới); **Đã đăng và hiệu quả, Nguồn thu thập, Cài đặt, Thông báo, Nhật ký** nằm ở các tab còn lại.

### Ba nơi một video có thể nằm

| Tab | Chứa gì | Vì sao có thể trống |
|---|---|---|
| **Hàng đợi** | Video đã tải, đang chờ Gemini làm Vietsub hoặc lồng tiếng (xếp đúng thứ tự sẽ được xử lý), cùng danh sách ứng viên chưa tải | Chưa có video mới: bấm **Thu thập video mới** |
| **Đăng bài** | Video đã dựng xong, mỗi video có nút **Đăng ngay** | Nếu trống, trang tự nói lý do: công tắc **Xử lý video** đang TẮT (kèm nút bật), hoặc còn N video đang chờ (kèm nút **Xử lý ngay**), hoặc chưa có gì (kèm nút **Cập nhật**) |
| **Cần xem** | Việc cần bạn quyết định: xác minh TikTok, bài chưa xác nhận, video bị hệ thống giữ lại | Trống là tốt. Video "chờ xử lý" **không** nằm ở đây mà nằm ở Hàng đợi |

### Việc "Cần xem"

| Thẻ | Nghĩa | Bạn làm gì |
|---|---|---|
| 🚨 **Chưa xác nhận đã đăng** | Hệ thống đã bấm Đăng nhưng chưa thấy bài trên hồ sơ TikTok. Đăng tự dừng để không trùng | Mở TikTok kiểm tra. **Bài đã lên** → bấm "Bài đã lên TikTok". **Chưa có** → bấm "Chưa có, cho phép đăng lại" |
| 🎬 **Chờ bạn duyệt** | Chỉ xuất hiện khi bật "Duyệt tay trước khi đăng". Đã dựng xong | Xem video, bấm "Duyệt và cho đăng" hoặc "Bỏ" |
| ⚠️ **Cần duyệt** | Hệ thống giữ lại và ghi lý do (lệch chủ đề, nhạy cảm, Gemini không chắc, có thể trùng video đã xử lý...) | Xem video gốc. Ổn → "Duyệt lại, bỏ qua kiểm tra" (chạy lại và bỏ qua các kiểm tra phán đoán, vẫn giữ kiểm tra cấu trúc). Không → "Bỏ" |

## 3. Cài đặt (đều đổi được ngay trên bảng điều khiển)

| Cài đặt | Mặc định | Ý nghĩa |
|---|---|---|
| Xử lý video bằng Gemini | Tắt | Bật thì video được gửi tới Google Gemini để phân tích. Cần khóa |
| Tự đăng lên TikTok | Tắt | Công tắc cuối cùng. Chỉ bạn bật |
| Duyệt tay trước khi đăng | Tắt | Bật thì video dựng xong dừng ở "Chờ bạn duyệt" |
| Lồng tiếng Việt | Tắt | Chỉ áp dụng cho video thuyết minh. Nghe thử giọng đọc trước khi bật |
| Số bài tối đa mỗi ngày | 2 | 1–10 |
| Giãn cách tối thiểu | 3 giờ | Giữa hai bài |
| Giờ vàng | 11-14, 19-23 | Giờ Việt Nam; để trống là đăng bất kỳ lúc nào |
| Video mới trong (ngày) | 7 | Bỏ video cũ hơn |
| Độ dài tối đa | 180 giây | |
| Tải tối đa mỗi lần quét / Hàng chờ tối đa | 3 / 4 | Kiểm soát chi phí Gemini |
| Ngưỡng thịnh hành | Douyin ≥ 150.000 tim; Kuaishou, TikTok ≥ 1.000.000 lượt xem | Video dưới ngưỡng không vào hàng đợi |
| Độ chắc chắn tối thiểu của Gemini | 0.90 | Dưới mức này video vào "Cần duyệt" |
| Hạn mức gọi Gemini / 24 giờ | 12 | Mỗi video tốn 1 lần phân tích (+1 nếu lồng tiếng). Tăng nếu gói Gemini của bạn cho phép |

Mọi giá trị đều được kiểm tra khoảng hợp lệ ở worker (`validate_settings`), nhập sai sẽ báo lỗi chứ không lưu.

### Khi đăng bài, cửa sổ Chrome hiện lên

Trình đăng mặc định mở **cửa sổ Chrome thật** (khi máy có màn hình), khoảng 1–2 phút mỗi bài: tải video, điền mô tả, bấm Đăng, xác nhận. Đừng đóng nó giữa chừng. Trên máy chủ không có màn hình, nó chạy ẩn (TikTok sẽ đòi xác minh nhiều hơn). Ép một trong hai cách bằng `TRENDVN_PUBLISH_HEADED=1` hoặc `0` trong `.env`. Trên Linux dùng dịch vụ systemd, `./trendvn install` đã ghi `DISPLAY` hiện tại vào dịch vụ; nếu cửa sổ không hiện, kiểm tra `systemctl --user cat trendvn-agent`.

### Chạy thử an toàn trước khi đăng công khai

Đặt **Chế độ hiển thị bài đăng = Chỉ mình tôi** trong Cài đặt → Lịch đăng, bật Tự đăng, để hệ thống đăng vài bài thật mà chỉ bạn thấy. Xem chất lượng phụ đề, mô tả và kiểu dựng trong TikTok Studio; ổn thì đổi lại "Mọi người". Bài riêng tư vẫn được xác nhận bằng hồ sơ hoặc trang nội dung của Studio.

### Dùng trên điện thoại

Mở địa chỉ bảng điều khiển (qua VPN hoặc đường hầm SSH, xem [DEPLOY.md](DEPLOY.md)). Giao diện tự chuyển sang dạng điện thoại: thanh điều hướng ở đáy màn hình (Tổng quan, Hàng đợi, Đăng bài, Cần xem, Đã đăng, Thêm), bảng thành thẻ, nút lớn. Ở màn hình **Tổng quan** có hai công tắc nhanh: **Xử lý video** và **Tự đăng TikTok** (chạm để bật/tắt ngay, dùng làm nút dừng khẩn cấp). Duyệt video: mở tab **Cần xem**, xem trước video rồi bấm nút ở đáy thẻ.

## 4. Xử lý sự cố theo triệu chứng

Bắt đầu bằng: `./trendvn doctor` (mỗi dòng lỗi kèm cách sửa), rồi `./trendvn status`. Xem log: `./trendvn logs -f` (worker + n8n), `./trendvn logs agent -f` (Chrome trên máy; file `data/agent/agent.log`).

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có video mới nào vào hàng đợi | (1) Lần quét đầu chỉ ghi mốc. (2) Ngưỡng quá cao. (3) Hàng chờ đã đủ | Chờ lần quét thứ 2; hạ ngưỡng ở Cài đặt; xem mục Nguồn thu thập |
| TikTok, Instagram báo "Cần IP US" | IP thoát không phải Mỹ | Đặt `TRENDVN_US_PROXY` trong `.env`, rồi `./trendvn agent restart` |
| "Trình đăng: Cần chú ý" | Chưa đăng nhập hoặc phiên hết hạn | `./trendvn tiktok login` |
| Video kẹt ở "Cần duyệt" hàng loạt với lý do Gemini | Sai khóa, hết hạn mức, model đổi | Kiểm tra khóa và hạn mức ở Google AI Studio; xem `docs/PROMPTS.md` |
| Một nguồn báo "xác minh hoặc đăng nhập" | Trang hiện CAPTCHA hoặc bắt đăng nhập | Hệ thống **không vượt CAPTCHA**. Thường tự hết sau vài giờ; giảm tần suất quét hoặc dùng IP khác |
| Kuaishou đôi khi báo lỗi | Trang ngắt kết nối | Đã tự thử lại 3 lần; lỗi thoáng qua bình thường |
| Bảng điều khiển báo "TikTok đang yêu cầu xác minh" | TikTok hiện hình CAPTCHA cho phiên tự động (xuất hiện ngẫu nhiên, nhất là khi mở trang tải lên nhiều lần liên tiếp) | Hệ thống **không giải hay vượt** và đã tạm dừng đăng. Chạy `./trendvn tiktok trust` (Mac: nhấp đúp `macos/Xac-minh-TikTok.command`), tự giải hình trong cửa sổ hiện ra; xong hệ thống tự đăng tiếp. Tránh chạy `dry-run` liên tục |
| Đăng báo "Không tìm thấy ô chọn file" | TikTok đổi giao diện TikTok Studio, hoặc trang tải quá chậm | Xem ảnh trong `data/agent/shots/`; sửa bộ chọn phần tử ở `services/agent/publisher.py::_publish_one` |
| Bấm nút mà báo "Agent đang bận" | Lịch tự động hoặc một nút khác đang dùng trình duyệt | Bình thường, đợi vài phút rồi bấm lại |
| `./trendvn doctor` báo "Container gọi được agent" lỗi dù agent chạy | Tường lửa của máy chặn cầu nối Docker (Linux/ufw) | `sudo ufw allow from <dải TRENDVN_SUBNET trong .env> to any port <TRENDVN_AGENT_PORT>` |
| Bấm nút mà báo "Không gọi được agent" | Dịch vụ agent không chạy | `./trendvn doctor`, rồi `./trendvn agent restart` và `./trendvn agent logs` |
| Mở bảng điều khiển từ máy khác bị chuyển tới trang đăng nhập | Bạn đã mở ra ngoài máy | Nhập mật khẩu `TRENDVN_UI_PASSWORD` trong `.env` (xem [DEPLOY.md](DEPLOY.md)) |
| Video kẹt "Chờ xử lý" và nhật ký ghi "Gemini đang quá tải" | Google báo model quá tải tạm thời (503) | Bình thường: hệ thống đã thử lại, đổi model và xếp video lại hàng đợi; tự chạy ở lần sau |
| Lỗi "Gemini HTTP 404 ... no longer available" | Google ngừng model bạn đang chọn | Tự chuyển model kế tiếp; nếu vẫn lỗi, đổi tên model ở Cài đặt → Gemini (xem `GET /v1beta/models` của Google) |
| Bấm Đăng nhưng bài không lên | TikTok đang kiểm duyệt hoặc lỗi mạng | Hệ thống tự đánh dấu "chưa xác nhận" và dừng; xác nhận bằng tay (mục 2) |
| Workflow n8n chạy nhưng "Agent busy" | Agent đang làm việc khác | Bình thường; lần sau tự chạy. Một việc trình duyệt tại một thời điểm |
| `agent` không nghe được | Mạng Docker chưa lên | Agent tự thử lại mỗi 15 giây; `./trendvn up` |
| Ổ đĩa đầy | Video gốc và dựng tích tụ | Xóa video cũ: xem mục 5 |

## 5. Dọn dẹp và bảo trì

- Video đã đăng thành công không cần giữ lại. Xóa an toàn thư mục `data/worker/jobs/<id>/` và `data/worker/inbox/*` của video có trạng thái `published`, `rejected`, `duplicate`, `failed` (bản ghi trong SQLite vẫn giữ để chống trùng).
- Không xóa `data/worker/trendvn.sqlite3`: mất nó là mất toàn bộ lịch sử chống trùng, hệ thống sẽ đăng lại video đã từng đăng.
- Sao lưu định kỳ: `./trendvn backup --keep 8` (đưa vào cron nếu muốn; cron có PATH rất ngắn nên khai báo để tìm thấy `docker`: `0 3 * * 0 PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; cd /đường/dẫn/trendvn && ./trendvn backup --keep 8`).
- Lịch sử thực thi n8n tự xóa sau 7 ngày (`EXECUTIONS_DATA_MAX_AGE`).

## 6. Khôi phục các tình huống

- **Mất điện giữa lúc xử lý:** `housekeeping` (trong workflow 01) chuyển video bị treo > 30 phút sang "Cần duyệt", bạn duyệt lại là chạy tiếp.
- **Mất điện giữa lúc đăng:** trạng thái `publishing` quá 45 phút tự thành "Chưa xác nhận"; agent đối chiếu hồ sơ ở lần chạy 01 kế tiếp, không xác nhận được thì bạn xác nhận tay.
- **Đổi mật khẩu TikTok hoặc bị đăng xuất:** đăng nhập lại bằng `./trendvn tiktok login`. Đăng tự dừng ("Trình đăng: Cần chú ý") cho tới khi có phiên.
- **Gemini sai lệch:** dùng "Duyệt tay trước khi đăng" trong vài ngày đầu để xem chất lượng phụ đề và mô tả trước khi để hoàn toàn tự động.
- **Muốn dừng ngay mọi thứ:** đặt "Tự đăng: Tắt" trên bảng điều khiển (có hiệu lực ngay ở lần hỏi tiếp theo). Muốn dừng cả thu thập: tắt Publish của workflow 01 trong n8n.

## 7. Kiểm thử

```bash
./trendvn test              # nhanh: lint + hơn 150 test trên máy
./trendvn test container    # toàn bộ test trong image Docker (có ffmpeg, gồm dựng video thật)
./trendvn test e2e          # Chrome thật: bố cục 7 kích thước × 6 tab và mọi luồng bấm nút
./trendvn test all
```
