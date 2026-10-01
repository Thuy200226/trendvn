# Lộ trình 1.4: các phase và nhật ký rà soát

Tài liệu làm việc: ghi lại yêu cầu, thiết kế từng phase và kết quả 3 vòng rà soát của mỗi phase (để không mất khi làm nhiều phiên).
Quy ước mỗi phase: (1) làm, (2) **rà soát vòng 1 — tĩnh** (đọc lại mã, lint, tài liệu khớp mã), (3) **vòng 2 — động** (chạy thật, đo thật),
(4) **vòng 3 — độc lập** (tác tử chỉ đọc mã, hoặc đối chiếu số liệu đo), (5) sửa mọi phát hiện rồi mới sang phase kế.

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Chạy hoàn toàn từ thư mục mới, dữ liệu mới, thôi dùng thư mục cũ | xong |
| A | Bố cục thư mục và chia module (worker, agent) cho dễ đọc, dễ mở rộng | xong |
| B | Chất lượng phân tích (giữ nguyên / Vietsub / thuyết minh) và chất lượng video | xong |
| C | Tìm kiếm và tổng hợp theo chủ đề, đăng nhiều tài khoản theo nhiều chủ đề | xong |
| D | Hiệu suất và tốc độ | đang rà soát |

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

## Phase C — Tìm kiếm theo chủ đề và nhiều tài khoản

Khảo sát thật trước khi thiết kế (Chrome thật, khách chưa đăng nhập): **tìm kiếm của Douyin và Kuaishou không dùng được** (Douyin ra trang CAPTCHA, Kuaishou trả `{"result":2}`; hệ thống không bao giờ giải CAPTCHA). Cái dùng được: trang `jingxuan` của Douyin có 13 tab chủ đề, mỗi tab cho khoảng 40 video riêng; Kuaishou chỉ có một luồng "推荐" cho khách; TikTok (cần IP Mỹ) có chip danh mục.

Số đo làm nền cho thiết kế (520 video Douyin thật trong 13 tab): chỉ 12% video trong một tab đạt mốc 150 nghìn tim của luồng chung, trung vị tuổi video là 39 ngày (giới hạn 7 ngày chỉ cho qua 10%), 40% video dài hơn 180 giây. Vì vậy luồng chủ đề dùng 15% ngưỡng tim/lượt xem và cho phép cũ gấp 4 lần; ngưỡng cứng của luồng chung sẽ làm mọi chủ đề nhỏ chết đói. Gợi ý chủ đề bằng từ khóa (không tốn lượt Gemini): 67% tiêu đề có từ khóa, trúng 67%, trên nửa dữ liệu giữ lại để kiểm; danh mục của nguồn tự nó cũng nhiễu (tab "Âm nhạc" lẫn video nấu ăn, nông thôn), nên gợi ý chỉ dùng để **chọn tải**, Gemini mới quyết định chủ đề cuối.

Đã làm: thực đơn 14 chủ đề; bảng `accounts` (CSDL tự chuyển, đã thử trên bản sao CSDL thật của 1.2: 58 video giữ nguyên); đăng theo từng tài khoản (giờ vàng, giới hạn, giãn cách, hồ sơ Chrome riêng); thu thập Douyin theo tab trong một lần mở trang; chọn tải chia lượt giữa chủ đề; giao diện và API tài khoản; `tiktok login --account`.

**Rà soát 1 — tĩnh.** Đọc lại toàn bộ thay đổi, ruff/black/shellcheck/doclint sạch; phát hiện và sửa khi viết test: gợi ý chủ đề của luồng chung bị tab ghi đè đúng thứ tự (tab biết rõ hơn từ khóa), `target` không còn là cài đặt lưu mà là tên của tài khoản mặc định (giữ API cũ chạy).
**Rà soát 2 — động.** Trên hệ thống thật: CSDL v1.3 → v2 tự chuyển; thu thập thật Douyin 250–270 video/lần (trước 49) qua 6 luồng; ứng viên theo chủ đề vào đúng nhóm (hài 10, thú cưng 10, đời sống 8, nhạc 7, gia đình 4); 82 kiểm tra Chrome thật gồm luồng thêm tài khoản, chạm chọn chủ đề, lưu, xóa; Gemini thật phân loại video nhạc live đúng `music`, không nhận chữ lời bài hát là phụ đề cứng.
**Rà soát 3 — độc lập.** Một tác tử thử phá: 2300 chuỗi ngẫu nhiên (khoảng 175 nghìn thao tác) so với mô hình độc lập, 0 vi phạm; 6000 dữ liệu vào ác ý, chỉ ra `ValueError`; di trú CSDL 8 tiến trình cùng lúc, không lỗi. Hai lỗi thật và nhiều rủi ro, **đã sửa hết và có test**: (1) tài khoản chưa đăng nhập luôn được chọn trước, đốt 3 video tốt nhất vào "Cần xem" và bỏ đói tài khoản khác (nay: tài khoản biết là chưa đăng nhập bị bỏ qua, không tính là lỗi của video, tài khoản vừa lỗi xếp sau các tài khoản khác); (2) hộp xác nhận ở thẻ video nêu sai tài khoản khi không tài khoản nào nhận chủ đề đó. Rủi ro: đọc danh sách tài khoản ngoài khóa (xóa tài khoản đúng lúc vẫn nhận bài), video dựng xong nhưng không tài khoản nào nhận chặn thu thập mới, hồ sơ Chrome đăng nhập nhầm tài khoản (nay kiểm tra tên đăng nhập thật trong trang TikTok trước khi đăng, đã thử trên hồ sơ thật), tab nhận nhầm phản hồi muộn của tab trước (nay gán theo mã tab trong yêu cầu), mất cả luồng đã đọc khi một tab lỗi, từ khóa Latin ngắn khớp giữa chữ (`cat` trong `location`), sao lưu/khôi phục chỉ lo hồ sơ `publisher`, chip TikTok không xoay vòng, bài đăng cũ không có tài khoản bị tính cho tài khoản mặc định hiện tại.

## Phase D — Hiệu suất và tốc độ

Đo từng công đoạn trên video thật trước khi sửa (video ngang 153 giây): Gemini khoảng 65% thời gian một video (30–100 giây và hay gặp lỗi 503 kéo dài), dựng 40 giây, bản xem trước 6,5 giây, kiểm tra 4 giây, dấu vân tay 1,2 giây; thu thập 107–205 giây; trang bảng điều khiển 8–12 ms (không cần tối ưu).

| Việc | Trước | Sau |
|---|---|---|
| Xử lý nhiều video | lần lượt từng video | 2 video cùng lúc (`TRENDVN_PROCESS_PARALLEL`), thông lượng gần gấp đôi vì phần lớn là chờ Gemini |
| Video nhạc dọc không lời (giữ nguyên) | dựng lại 24 giây, tệp 24,8 MB | sao nguyên hình 3,3 giây, 13,8 MB, từng điểm ảnh giống bản gốc |
| Thu thập Douyin (6 luồng chủ đề) | chờ cố định ~95 giây | chờ thích nghi ~60 giây (mỗi tab 5–11 giây) |
| Bản xem trước gửi Gemini | 2 khung/giây | 1 khung/giây (Gemini chỉ lấy 1 khung/giây); thời gian mã hóa không đổi vì bị giải mã chi phối |

Thử và **không đổi** vì không nhanh hơn: bộ lọc khung 9:16 (giải mã 1080p và co ảnh chiếm hơn nửa; `fast_bilinear`, ghép lớp, số luồng đều không thắng), `-filter_complex_threads`. `thinkingConfig`/độ phân giải thấp của Gemini không thể đo trong buổi này vì API liên tục quá tải (503), nên không bật; nếu bật mà API từ chối thì sẽ làm hỏng mọi lần phân tích.
