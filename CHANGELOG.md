# Lịch sử thay đổi

## 1.4 — đang làm (xem docs/ROADMAP.md)

**Phase A — bố cục và chia module (không đổi hành vi).** Hai ứng dụng được tách thành gói Python có thư mục theo việc, mỗi file một trách nhiệm (không file nào quá khoảng 300 dòng):

- `services/worker/src/trendvn_worker/`: `domain/` (luật thuần: chấm điểm, lịch, quan sát, caption), `store/` (SQLite: schema có phiên bản, ingest, queue, publishing, reporting…), `ai/` (Gemini: phân tích, TTS, client), `media/` (ffmpeg, dấu vân tay, phụ đề, dựng), `web/` (HTTP: handler, bảo mật, form, API), `ui/` (giao diện: thẻ, từng tab, CSS/JS tĩnh), `tasks.py`, `pipeline.py`.
- `services/agent/src/trendvn_agent/`: `collector/` (+ `sources/` mỗi nền tảng một file, thêm nền tảng = thêm một file và một dòng đăng ký), `publisher/`, `browser.py`, `server.py`.
- Chạy theo module (`python -m trendvn_worker`, `python -m trendvn_agent`); mẫu systemd/launchd và `agent.sh` cập nhật theo; `./trendvn update` cài lại dịch vụ nền của agent nên bản đang chạy theo bố cục cũ vẫn chuyển được.
- Cơ sở dữ liệu có phiên bản (`PRAGMA user_version` + danh sách migration); CSDL 1.0–1.3 được nhận nguyên trạng.
- `tests/` chia `worker/ agent/ tools/ e2e/`; thêm `./trendvn fmt` (black + ruff, bản ghim trong `requirements-dev.txt`), doclint kiểm tra mọi lệnh đều có tài liệu.
- Sửa lỗi tìm thấy khi tách: `sys` chưa import trong đường tải Instagram của collector; bước kiểm tra e2e bố cục từng chập chờn vì đo khi trang chưa về đầu.

## 1.3 — 2026-09-30

Bản đóng gói lại để bàn giao và triển khai trên nhiều máy Mac/Linux. **Không đổi hành vi của hệ thống** (luồng tự động, quy tắc, giao diện giữ nguyên bản 1.2); đổi cách bố trí thư mục và bổ sung công cụ vận hành.

- **Bố cục thư mục chuẩn:** `services/worker` (image Docker), `services/agent` (Chrome trên máy), `n8n/` (bộ sinh workflow + công cụ quản lý), `scripts/`, `macos/`, `tests/`, `docs/`; mọi dữ liệu và bí mật của máy nằm trong `data/` và `.env` (không nằm trong bản đóng gói).
- **Một lệnh cho mọi việc:** `./trendvn` (và `Makefile` làm lối tắt): `install`, `up`, `down`, `restart`, `update`, `status`, `doctor`, `logs`, `build`, `backup`, `restore`, `package`, `test`, `agent ...`, `tiktok ...`, `n8n ...`.
- **Công cụ build n8n:** `n8n/build.py` sinh 6 workflow từ mã (id node cố định nên sinh lại cho kết quả giống hệt; `--check` phát hiện file JSON lệch mã); `n8n/manage.py` nạp, bật/tắt lịch, xuất workflow từ n8n; nạp lại không làm tắt lịch đang bật.
- **Docker:** image worker có nhãn phiên bản, `HEALTHCHECK`, chạy root filesystem chỉ đọc, bỏ mọi capability, `no-new-privileges`; log container tự xoay vòng (5 × 10 MB); n8n có healthcheck; `up --wait` chờ tới khi khỏe.
- **Log:** `./trendvn logs [worker|n8n|agent|all] [-f] [-n]` gom log của cả ba thành phần.
- **Đóng gói:** `./trendvn package` (Python thuần, giống nhau trên Linux/macOS) kiểm tra rồi mới đóng gói; khôi phục sao lưu giữ đúng khóa mạng/uid của máy mới.
- **`./trendvn migrate <thư-mục-1.2>`**: chuyển hệ thống đang chạy từ thư mục 1.2 sang thư mục mới bằng một lệnh (sao lưu, dừng bản cũ, chép dữ liệu và phiên TikTok, cài, đối chiếu), giữ nguyên trạng thái lịch và công tắc, có đường lui.
- Bản sao lưu tạo bởi 1.2 vẫn khôi phục được. `restore` gộp `.env` an toàn (giá trị của máy hiện tại luôn thắng), kiểm tra bản sao lưu trước khi xóa gì, `backup` dừng n8n vài giây để chép dữ liệu nhất quán.
- **Bảo vệ hệ thống khác trên cùng máy:** mọi lệnh thay đổi từ chối chạy nếu project Docker đang chạy từ thư mục khác (`TRENDVN_ALLOW_TAKEOVER=1` để bỏ qua); `install` từ chối tạo khóa n8n mới khi còn volume n8n cũ; dịch vụ nền chỉ điều khiển agent của đúng thư mục này.
- **Cài đặt chắc hơn:** kiểm tra `docker compose` ≥ 2.20, Google Chrome đúng chỗ Playwright tìm, từ chối đường dẫn có dấu cách/ký tự đặc biệt và (macOS) các thư mục Documents/Desktop/Downloads; `doctor` mở thử Chrome qua Playwright; dịch vụ nền được sinh bằng Python (`scripts/render_service.py`) nên không vỡ khi có Wayland hay ký tự lạ; cài lại trên Linux khởi động lại agent.
- **Python cho agent phải từ 3.10** (playwright và yt-dlp yêu cầu; macOS chỉ kèm 3.9): `install` tự chọn bản mới nhất trên máy hoặc hướng dẫn `brew install python@3.12`; lỗi này đã có từ bản 1.2 và chỉ lộ ra khi cài trên Mac mới.
- **Một bộ đọc `.env` chung** (`scripts/envfile.py`, theo quy tắc của Compose: chú thích cuối dòng, nháy, dòng rỗng) cho mọi công cụ; sao chép `.env.example` thành `.env` vẫn sinh được khóa bí mật thật.
- Sửa lỗi: mật khẩu/header có dấu tiếng Việt làm `hmac.compare_digest` ném lỗi (không đăng nhập được, 500); log yêu cầu sai định dạng; nạp credential n8n không còn qua file root-0600 (hỏng trên Mac).
- **Log:** worker ghi log có ích (khởi động, từng lệnh gọi API, lỗi kèm traceback; không ghi token, cookie hay chuỗi truy vấn); `./trendvn logs agent` gom agent.log, launchd.log, agent.out hoặc journal của systemd, nên thấy cả lỗi khi khởi động.
- **Kiểm tra tự động:** `./trendvn test lint` kiểm tra workflow khớp mã sinh, cú pháp Python/shell, bash 3.2 của macOS, shellcheck (nếu có), mẫu dịch vụ nền, và `scripts/doclint.py` bảo đảm tài liệu khớp mã (lệnh, liên kết, đường dẫn).

Đường dẫn cũ → mới: `worker/` → `services/worker/src/trendvn_worker/`, `agent/` → `services/agent/src/trendvn_agent/`, `runtime/` → `data/worker/`, `agent_data/` → `data/agent/`, `backups/` → `data/backups/`, `workflows/` → `n8n/workflows/`, `install.sh`/`backup.sh`/... → `./trendvn install`/`backup`/...

## 1.2 — 2026-09-30

Bản này thêm các nút thao tác tay cho bảng điều khiển (luồng tự động theo lịch giữ nguyên hoàn toàn) và trải qua ba vòng rà soát (giao diện, hiệu suất, lỗi), trong đó một vòng do một bên độc lập thực hiện.

**Chỉnh giao diện theo phản hồi khi dùng thật (cùng bản 1.2)**
- Tách **Hàng đợi** thành tab riêng (thanh dưới có 6 mục, có số video đang chờ): thứ tự sẽ xử lý, nút **Xử lý N video chờ**, nút bật xử lý khi đang tắt, danh sách ứng viên chưa tải.
- Đổi tên tab **Cần xử lý** thành **Cần xem** để không lẫn với video "chờ xử lý".
- Tab **Đăng bài** khi trống giải thích lý do (xử lý đang tắt / còn N video đang chờ / chưa có gì) và có đúng nút để làm tiếp; chưa có khóa Gemini thì chỉ đường tới Cài đặt.
- Thanh trạng thái không còn là hàng cuộn ngang bị cắt chữ mà là thẻ ba dòng; các bước của Luồng xử lý bấm được; nhãn thanh dưới không xuống dòng/dính nhau ở 320–414 px (kiểm tra bằng Chrome thật); kết quả của việc đã xong quá 15 phút không còn hiện ở tab khác; mỗi nút chạy nền đưa bạn về đúng tab có nút.

**Nút thao tác trên bảng điều khiển**
- **▶ Bắt đầu:** thu thập video mới rồi xử lý, sẵn sàng đăng. Kèm nút **Thu thập video mới**, **Xử lý video chờ** và **Đọc lượt xem**. Tiến độ hiện trực tiếp, chạy nền, dùng chung khóa với lịch n8n nên không va chạm.
- **Tab Đăng bài:** danh sách video đã xử lý, mỗi video có xem trước, ô sửa mô tả và hashtag (đếm ký tự, kiểm tra chất lượng), nút **Đăng ngay**, **Xem thử không đăng** (có ảnh chụp), **Lưu mô tả**, **Duyệt cho lịch tự đăng**, **Bỏ video**. Bấm Đăng ngay là sự đồng ý cho đúng video đó: bỏ qua công tắc, giờ vàng, giới hạn ngày; các chốt bảo vệ tài khoản (một bài đang đăng, bài chưa xác nhận, TikTok đòi xác minh) vẫn giữ.

**Sửa lỗi nghiêm trọng tìm thấy khi rà soát**
- Mọi nút gửi form của bảng điều khiển bị từ chối từ bản 1.0 (tiêu đề `Referrer-Policy: no-referrer` khiến Chrome gửi `Origin: null`).
- Video Douyin dài bị từ chối vì Gemini bịa thêm phụ đề sau phút cuối: nay chuẩn hóa mốc thời gian (sắp xếp, cắt, bỏ phần thừa) và chỉ từ chối khi quá nửa số dòng không đáng tin.
- Lỗi trước khi bấm Đăng (Chrome không mở được...) từng bị tính nhầm là "đã bấm Đăng chưa xác nhận" và chặn mọi lần đăng; mọi lỗi sau khi bấm luôn là "chưa rõ" (không bao giờ đăng lại).
- Đăng thủ công thất bại không còn vô tình duyệt video cho lịch tự đăng; video lỗi 3 lần được chuyển sang Cần xem, lỗi 1–2 lần nghỉ 1 giờ để khỏi chặn hàng đợi.
- Ô để trống trong Cài đặt từng bị bỏ qua (xóa giờ vàng không có tác dụng, xóa một ngưỡng lại tắt luôn ngưỡng đó); số quá lớn gây lỗi 500.
- Ngưỡng treo bài đăng nâng từ 15 lên 45 phút (đăng chậm không bị coi là hỏng giữa chừng).

**Bảo mật**
- Mở bảng điều khiển ra ngoài máy giờ **bắt buộc mật khẩu** (`TRENDVN_UI_PASSWORD`, chặn đoán sai sau 5 lần); trên chính máy này vẫn không cần. Bật công tắc Tự đăng hoặc Xử lý bằng một chạm có hỏi xác nhận.

**Chất lượng video, mô tả, hashtag**
- Video ngang và vuông được đưa vào khung dọc 1080×1920 trên nền mờ (nhanh hơn 4 lần); video xoay được nhận đúng; video quá lớn thu về tối đa 1080×1920; âm lượng chuẩn −14 LUFS; bỏ siêu dữ liệu nguồn; giới hạn 30 fps; đo chất lượng đầu ra và tạo ảnh xem trước.
- Phụ đề tránh vùng chữ của TikTok (dải mờ dưới hoặc trên hình, hoặc cao hơn với video dọc).
- Prompt yêu cầu mô tả là một câu tự nhiên 40–90 ký tự, hashtag 3–4 cái không dấu; mã lọc bỏ hashtag mang tên nền tảng hoặc từ sáo rỗng, chuẩn hóa Unicode, cắt mô tả ở ranh giới từ; mô tả ngắn hoặc thiếu thì video vào Cần xem.

**Hiệu suất (đo với 30.000 video, 150.000 sự kiện)**
- Chỉ mục mới: dữ liệu bảng điều khiển 63 → 20 ms, cả trang 22 ms, 16 KB sau nén gzip; trang không còn tải lại toàn bộ khi chỉ cần xem tiến độ; ảnh xem trước thay vì tải cả video.

**Sau rà soát vòng 4:** nút "Đưa về sẵn sàng đăng" cho video bị chuyển Cần xem sau 3 lần lỗi; ghi nhật ký không bao giờ làm hỏng tác vụ; tóm tắt thu thập không cắt giữa từ.

**Kiểm thử:** từ 82 lên 150+ test, thêm bộ kiểm thử trình duyệt thật (`tests/e2e/ui_e2e.py`: bố cục ở 7 kích thước × 6 tab và toàn bộ luồng bấm nút) và bộ kiểm thử máy chủ HTTP.

## 1.1 — 2026-09-30

Bản này sửa các lỗi chỉ lộ ra khi chạy với dịch vụ thật (Gemini, TikTok) và đóng gói để cài trên máy khác, gồm cả macOS.

**Sửa lỗi phát hiện khi thử thật**
- Gemini: model mặc định `gemini-2.5-flash` đã bị Google ngừng cấp cho người dùng mới (HTTP 404). Mặc định giờ là `gemini-3.8-flash`, cài đặt cũ tự được nâng cấp, gặp 404 tự chuyển model kế tiếp và nhớ model dùng được.
- Gemini quá tải (429/5xx) hoặc hết thời gian chờ: thử lại và đổi model; nếu vẫn lỗi thì xếp video lại hàng đợi, không đánh dấu hỏng. Yêu cầu bị từ chối không tính vào hạn mức ngày. Thông báo lỗi hiện lý do thật của Google.
- Giọng đọc: model mới trả file WAV, model cũ trả PCM thô; nay đọc được cả hai và mọi định dạng khác qua ffmpeg.
- TikTok Studio cần 20–30 giây mới dựng xong trang tải lên (trước đó chỉ chờ 7 giây); khung con bị hủy khi trang đang dựng không còn làm văng lỗi.
- TikTok đôi khi hiện CAPTCHA: trình đăng nhận biết, **không giải hay vượt**, tạm dừng đăng, báo trên bảng điều khiển và điện thoại; lệnh `publisher.py trust` (hoặc nhấp đúp `Xac-minh-TikTok.command`) để bạn giải một lần thì đăng tự tiếp tục.

**Đã kiểm chứng bằng dịch vụ thật trong bản này**
- Gemini: phân tích một video Kuaishou thật (phân loại, chép và dịch 7 đoạn thoại, mô tả, hashtag, dựng Vietsub) và giọng đọc 15,6 giây.
- TikTok Studio: đăng nhập, dry-run, rồi **đăng thật một video thử riêng tư** và xác nhận bài trên hồ sơ (chủ kênh đồng ý rõ ràng, bài thử còn lại để chủ kênh tự xóa).
- Cài đặt sạch, n8n gọi agent, sao lưu và khôi phục trên một bản cài thứ hai tách biệt.

**Trung thực với trang web**
- Gỡ các thiết lập giấu việc tự động hóa (cờ `AutomationControlled`, sửa User-Agent bỏ chữ "Headless"). Bốn nguồn vẫn đọc được.
- Trình đăng mặc định dùng **cửa sổ Chrome thật** khi máy có màn hình (TikTok hiện hình xác minh cho Chrome ẩn dày hơn hẳn); `TRENDVN_PUBLISH_HEADED=0/1` để đổi. Hình xác minh vẫn chỉ do bạn giải.
- Chế độ hiển thị bài đăng chỉnh được (Mọi người, Bạn bè, Chỉ mình tôi) để chạy thử an toàn.

**Giao diện điện thoại**
- Thanh điều hướng dưới màn hình, mỗi màn hình một trang; bảng thành thẻ; công tắc nhanh (xử lý, tự đăng) ngay màn hình chính; nhóm cài đặt gập; nút lưu nổi; ô nhập cỡ chữ 16px chống phóng to trên iPhone; hỗ trợ vùng an toàn (tai thỏ); liên kết n8n theo địa chỉ bạn đang dùng.

**Đóng gói cho máy khác**
- `install.sh` chạy trên Linux và macOS (Chrome trong /Applications, launchd, `caffeinate`, `host-gateway` của Docker Desktop).
- Quyền người dùng khớp máy (`TRENDVN_UID/GID`), cổng, dải mạng, tên dự án đều đổi được trong `.env`; nạp workflow, sao lưu và khôi phục không còn phụ thuộc tên container cố định.
- `yt-dlp` cài trong môi trường riêng (không cần cài hệ thống); `package.sh` đóng gói bản sạch không kèm bí mật; `CAI-DAT-MAC.md` hướng dẫn 5 bước; hai lối tắt nhấp đúp `Dang-nhap-TikTok.command`, `Xac-minh-TikTok.command`.
- Đã kiểm chứng cài đặt sạch, n8n gọi agent, sao lưu và khôi phục trên một bản cài thứ hai tách biệt.

## 1.0 — 2026-09-30

**Thu thập**
- Bốn nguồn chạy thật: Douyin, Kuaishou (mọi IP), TikTok và Instagram (chỉ khi IP thoát là Mỹ; từ chối gắn nhãn nhầm).
- Chọn video theo độ "mới nổi": điểm = mức tương tác ÷ (tuổi theo giờ)^0.6, lọc video quá cũ, ưu tiên nguồn từng hiệu quả.
- Thử lại khi trang ngắt kết nối; proxy Mỹ áp dụng cả cho Instagram qua yt-dlp.

**Xử lý**
- Prompt tách riêng (`worker/prompts.py`), có schema ép JSON, kiểm tra chủ đề, nhạy cảm, hashtag, phiên bản prompt trong manifest.
- Phụ đề Việt tự chia câu dài, có nền mờ che chữ gốc; lồng tiếng Việt cho video thuyết minh (tiếng gốc giảm còn 18%).
- Hết hạn mức Gemini thì xếp lại hàng đợi thay vì đánh dấu hỏng; hạn mức chỉnh được.

**Đăng**
- Trình đăng TikTok qua Chrome hồ sơ riêng, tự đăng nhập bằng thao tác của bạn; `dry-run` không bấm Đăng; xác nhận bài trên hồ sơ; không bao giờ tự đăng lại bài chưa rõ kết quả.
- Giờ vàng, giới hạn ngày, giãn cách, chọn bài điểm cao nhất; duyệt tay tùy chọn.
- Đọc lượt xem sau đăng và tự điều chỉnh trọng số nguồn (cần ≥ 8 bài).

**Vận hành**
- Bảng điều khiển viết lại: việc cần làm, duyệt có xem trước video, hiệu quả, nguồn, cài đặt đầy đủ, thông báo, nhật ký, sáng/tối, dùng được trên điện thoại.
- Thông báo Telegram, Discord/Slack, ntfy, có chống spam theo loại.
- Sáu workflow n8n: 01 thu thập và xử lý (3 giờ), 02 đăng (30 phút), 03 chốt ngày (23:30), 00, 10, 20.

**Đóng gói**
- `install.sh` một lệnh, `uninstall.sh`, `backup.sh`, `restore.sh`, `scripts/doctor.py`, `.env.example`, tham số hóa hoàn toàn `compose.yaml`, tự chọn dải mạng Docker trống.
- Tài liệu: README, ARCHITECTURE, DEPLOY, OPERATIONS, PROMPTS, SECURITY, API.
- 69 test.

## 0.1 — 2026-09-29

Nền tảng: hàng đợi SQLite, chống trùng, xử lý Vietsub, ba workflow n8n cơ bản.
