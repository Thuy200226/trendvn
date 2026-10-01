# Lộ trình 1.4: các phase và nhật ký rà soát

Tài liệu làm việc: ghi lại yêu cầu, thiết kế từng phase và kết quả 3 vòng rà soát của mỗi phase (để không mất khi làm nhiều phiên).
Quy ước mỗi phase: (1) làm, (2) **rà soát vòng 1 — tĩnh** (đọc lại mã, lint, tài liệu khớp mã), (3) **vòng 2 — động** (chạy thật, đo thật),
(4) **vòng 3 — độc lập** (tác tử chỉ đọc mã, hoặc đối chiếu số liệu đo), (5) sửa mọi phát hiện rồi mới sang phase kế.

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Chạy hoàn toàn từ thư mục mới, dữ liệu mới, thôi dùng thư mục cũ | xong |
| A | Bố cục thư mục và chia module (worker, agent) cho dễ đọc, dễ mở rộng | xong |
| B | Chất lượng phân tích (giữ nguyên / Vietsub / thuyết minh) và chất lượng video | xong |
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
Bộ kiểm thử bố cục e2e chập chờn một lần khi máy bận (đo khi trang chưa cuộn về đầu): nay đo sau khi trang đứng yên và báo rõ nếu không về đầu; chạy lại 6 lần, kể cả khi máy bị làm bận hết CPU: xanh.

**Rà soát 2 — động.** `./trendvn update` trên hệ thống thật: dịch vụ nền của agent được viết lại sang `-m trendvn_agent`; `doctor` xanh; thu thập thật qua agent mới (Douyin đọc 49, đạt ngưỡng 4, tải 2); `./trendvn test all` (cuối Phase A: 189 test trên máy và trong image Docker, dựng video thật bằng ffmpeg, 76 kiểm tra Chrome thật ở 7 cỡ màn hình).

**Rà soát 3 — độc lập.** Hai tác tử chỉ đọc mã đối chiếu mã cũ (`9dbd527`) với mã mới. Agent: không có lỗi hay thay đổi hành vi ngoài ý muốn (so sánh AST từng hàm, hằng số, thứ tự thao tác trình duyệt, thời gian chờ, đường dẫn dữ liệu); 6 ghi chú nhỏ đã xử lý: `agent.sh` nay nhận cả tiến trình `server.py` kiểu cũ khi dừng, `SECURITY.md` còn tên cũ (`publisher.py`, `_looks_blocked`) và doclint nay bắt loại lỗi này, test ghi nhầm vào `data/agent/agent.log` thật nay ghi vào thư mục tạm.

## Phase B — Chất lượng phân tích và video

Mốc đo (video thật tải từ Douyin lúc bắt đầu phase, chạy trong image worker với khóa Gemini thật):

| | Video 1: tiểu phẩm 1080×1920, 78,6 giây, có phụ đề cứng tiếng Trung | Video 2: nhạc live 1920×1080, 152,9 giây |
|---|---|---|
| Gemini quyết định | `mixed`, 12 dòng thoại → **Vietsub** (đúng) | `music` → **giữ nguyên** (đúng) |
| Dựng trước phase | 30,8 giây, 24,8 MB; phụ đề Việt đè lên chữ Trung, hiện lộn xộn; dòng nhanh nhất 21 ký tự/giây | 68,5 giây, 59,8 MB |
| Dựng sau phase | 24,9 giây, 19,7 MB; chữ Trung bị che sau dải mờ, phụ đề Việt nằm đúng trên dải đó; dòng nhanh nhất 17 ký tự/giây | (đo mã hóa riêng ở dưới) |

Đã làm (chi tiết kỹ thuật: `docs/PROMPTS.md` mục 3): bảng quyết định giữ nguyên / Vietsub / thuyết minh thành một hàm có lý do hiện trên thẻ video; che phụ đề cứng của video gốc; kéo dài thời gian hiện của dòng phụ đề quá nhanh; mã hóa `veryfast/crf 24` (SSIM 0,992 so với tham chiếu crf 12, nhỏ hơn và nhanh hơn khoảng 40%); đo âm lượng trong lần giải mã kiểm tra; chốt chặn giọng đọc nhanh bất thường.

Bài học đo được (và đã đổi hướng theo đó):
- Cắt/đồng bộ phụ đề bằng độ lớn âm thanh (silencedetect) **không dùng được** với video thật: tiểu phẩm Douyin luôn có nhạc nền nên âm thanh liên tục lớn; Gemini cho mốc thời gian gần như tròn giây (sai số khoảng ±1 giây). Đã bỏ ý định này.
- Bắt Gemini TTS đọc nhanh cho vừa cửa sổ lời làm nó **bỏ sót cả câu** (khớp 79% số từ khi nghe lại bằng Gemini), tốc độ mặc định khớp 100%. Giữ prompt mặc định, tăng tốc bằng `atempo`, thêm chốt chặn.
- Không đổi `loudnorm`: đo thực tế đưa nhạc -10 LUFS về -14,1 và lời thoại -14,6 về -14,5.

**Rà soát 1 — tĩnh.** Đọc lại toàn bộ thay đổi; ruff/black/shellcheck/doclint sạch; hằng số trong tài liệu khớp mã.
**Rà soát 2 — động.** Chạy trên video thật như bảng trên; `./trendvn test all`: 212 test trên máy và trong image Docker, 76 kiểm tra Chrome thật. Chưa kiểm chứng được: Gemini thật báo đúng vị trí phụ đề cứng (API video quá tải HTTP 503 cả buổi; schema mới đã được API chấp nhận và dải mờ đã dựng đúng với vị trí đặt tay), nên thử lại khi API rảnh.
**Rà soát 3 — độc lập.** Một tác tử thử phá bằng 486 tổ hợp (11 hình học nguồn × 18 giá trị dải × 3 đường dựng) trong image worker. Ba lỗi thật, đã sửa và có test: (1) đường âm thanh im lặng tuyệt đối (rỗng) làm `loudnorm` ra NaN và bộ mã hóa AAC từ chối: **lỗi có từ bản 1.3**, nay video "im lặng" không chỉnh âm lượng (cũng tránh khuếch đại tiếng xì lên -14 LUFS) và lỗi NaN được thử lại một lần không chỉnh; (2) dải ở mép dưới cùng của hình rất nhỏ ra dải 4 điểm ảnh bị ffmpeg từ chối; (3) số nguyên quá lớn trong `hard_subtitles` ném `OverflowError`. Sau sửa: 486/486 chạy được. Kiểm tra `decode_check` với tệp hỏng/cắt cụt (ném `ValueError` ngay, không treo), âm thanh rất ngắn, 10 phút âm thanh: ổn.
