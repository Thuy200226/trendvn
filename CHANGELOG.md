# Lịch sử thay đổi

## 1.8 — 2026-10-06 (đăng nhập kênh tìm kiếm, xóa lịch sử, tab cân đối)

**Đăng nhập Douyin và TikTok để tìm kiếm.** Đo trên máy thật: khách không tìm kiếm được ở cả hai nguồn (TikTok trả phản hồi rỗng; Douyin chuyển Chrome ẩn tới trang xác minh ngay ở trang chủ). Cột bên cạnh khung chat có mục **Kênh tìm kiếm**: tình trạng đăng nhập của từng tài khoản trên từng kênh, nút **Đăng nhập** (mở cửa sổ Chrome thật cho chủ tự đăng nhập, tối đa 10 phút) và **Kiểm tra** (đọc cookie, không mở trang); thẻ lỗi của lần tìm cũng có nút đăng nhập đúng kênh. Tình trạng được agent ghi lại sau mỗi lần đăng nhập, kiểm tra và tìm kiếm. Khi máy có màn hình, tìm kiếm chạy bằng cửa sổ thật như đăng bài (Douyin từ chối Chrome ẩn); trang xác minh trắng của Douyin giờ được nhận ra thay vì báo "chưa trả video".

**Link đã lưu và lịch sử.** Danh sách link hoa hồng đã lưu (chép, xóa từng link) nằm ở cột bên cạnh, tách khỏi lịch sử chat. **Xóa lịch sử tìm kiếm** xóa tin đã xong, giữ tin đang chạy, video đã chọn, link đã lưu và tình trạng đăng nhập; tin đã xong quá 30 ngày tự bị dọn. Xóa tài khoản xóa luôn tình trạng đăng nhập và link đã lưu của nó (bảng `channel_logins` do migration 8 tạo).

**Bố cục.** Tab Tìm hai cột trên màn hình rộng (khung chat + cột bên cạnh), cột bên cạnh nằm dưới khung nhập trên điện thoại. Thanh điều hướng điện thoại dàn đều khoảng cách giữa bảy mục thay vì chia theo độ dài nhãn, nhãn đầu và cuối không còn sát mép.


## 1.7 — 2026-10-06 (tìm sản phẩm trong một khung chat: docs/PRODUCT-SEARCH.md)

**Một khung chat cho mọi thứ về sản phẩm** (tab mới **Tìm**, thay cho mục "Tìm sản phẩm" nằm trong Thêm): gửi tên/model, ảnh, PDF/DOCX/TXT hoặc link; hệ thống nhận diện sản phẩm, tìm video ngay trong phiên TikTok/Douyin của tài khoản bạn chọn, và kiểm tra link chia sẻ bạn dán từ ứng dụng TikTok. Mọi câu trả lời hiện trong cùng luồng tin, có nút cho bước tiếp theo; tiến độ tự cập nhật, không tải lại trang.

**Link hoa hồng.** Hệ thống không đăng nhập Shop/Affiliate nên không tự lấy link; bạn sao chép link trong Showcase của ứng dụng TikTok và dán vào chat. Hệ thống đi theo chuyển hướng (chỉ gọi host `tiktok.com`), đọc mã sản phẩm và tên trang, rồi kết luận: đúng sản phẩm (cùng mã) / có vẻ đúng / chưa rõ / sản phẩm khác / không hợp lệ, kèm từng bằng chứng. Link đầy đủ không có dấu hiệu nhà sáng tạo được báo là không tính hoa hồng; link rút gọn không thấy dấu hiệu thì báo là không kiểm được (mã người chia sẻ có thể nằm phía TikTok). Chủ xác nhận link đầu tiên; dấu hiệu nhà sáng tạo của các link đã xác nhận được dùng để so các link sau. Không bao giờ khẳng định "đúng 100%": chắc chắn duy nhất là mã sản phẩm trùng.

**Nhận diện bền hơn.** Lời bạn gõ thắng ảnh; lời không chứa hãng/model ("tìm cái này") không ghi đè điều đọc được từ ảnh/trang; mọi kiểu lỗi của Gemini (quá tải, trả lời hỏng, sai lược đồ) đều quay về tìm theo tên bạn nhập (trước đây chỉ bắt lỗi gọi API). Quy tắc từ khóa riêng cho một sản phẩm (MCHOSE ACE68) thành bảng dữ liệu `LINE_HINTS`.

**Agent.** Một nguồn lỗi bất kỳ (kể cả hết thời gian chờ của trình duyệt) không còn làm mất kết quả của nguồn kia ở chế độ TikTok + Douyin (trước đây chỉ bắt `ValueError`). Ở cửa sổ tự xác minh, tên đăng nhập của phiên được kiểm lại sau khi có kết quả, kể cả khi cửa sổ vừa bị đóng.

**Dọn.** Gỡ tích hợp TikTok Shop API và đăng kèm giỏ hàng (cần ứng dụng Shop Partner được duyệt; còn nguyên ở commit `3d48f41`). Bảng kết quả cũ thay bằng nhật ký chat và bảng link đã xác nhận (migration 6 viết lại; migration 7 lặp lại đúng các bước đó cho CSDL đã chạy bản migration 6 đầu tiên của nhánh này, bảng `searches` cũ được để nguyên). Việc nền của tìm kiếm tách khỏi `tasks.py` sang `search/runner.py`; phần đọc trang tìm kiếm của agent dùng chung một khung. Ảnh/tài liệu chỉ nằm trong bộ nhớ đến khi nhận diện xong (không còn ghi vào CSDL). Thanh điều hướng điện thoại có bảy mục, nhãn 10 px ở màn hình rộng tới 370 px.

## 1.6 — 2026-10-02 (chất lượng đầu ra: docs/QUALITY.md)

**Lỗi lớn nhất tìm được:** giọng đọc **đọc to cả câu hướng dẫn** đứng trước lời thuyết minh (model TTS mới coi `text` là bản chép nguyên văn): thêm 10 giây lời hướng dẫn vào mọi video lồng tiếng, làm lời trông quá dài rồi bị tăng tốc hoặc từ chối. Nay chỉ gửi lời thuyết minh; giọng, sắc thái và nhịp đi trong `speech_metadata.style` (Interactions API); model cũ vẫn nhận hướng dẫn dạng chữ. Kết luận cũ "đọc nhanh thì bỏ sót câu" cũng sai (16–19 ký tự/giây tự nhiên, vẫn đủ từng chữ).

**Lồng tiếng được ưu tiên khi phù hợp.** Gemini báo thêm `speaker` (giới tính, sắc thái, số người nói) và `dub_ok`: video thuyết minh **và video một người nói mà thay giọng không mất gì** được lồng tiếng; hài, kịch, nhiều người nói giữ giọng gốc + Vietsub. Giọng theo người nói (đã nghe kiểm bằng một model khác: Kore, Aoede, Leda nữ; Orus nam), nhịp chọn bằng lời theo số ký tự cần nói mỗi giây, rồi chỉ chỉnh tốc độ nhỏ. Google bận thì video quay lại hàng đợi (phân tích đã nhớ trong `jobs/<id>/analysis.json`, không tốn thêm lượt gọi video; phê duyệt tay cũng không gọi lại), tối đa 4 lần rồi ra với Vietsub. Cài đặt mới: "Lồng tiếng cho", "Chọn giọng đọc", công tắc "Lồng tiếng Việt" bật mặc định.

**Âm thanh lồng tiếng.** Giọng cân riêng -16 LUFS; tiếng gốc chỉ hạ (còn 14%) trong cả cửa sổ lời gốc, vào/ra mềm, giữ nguyên ngoài đó (trước đây hạ cố định 18% suốt video); sau bản trộn có bộ giới hạn đỉnh. Đo: thấp hơn trên 8 dB dưới giọng.

**Làm mờ phụ đề gốc theo điều kiện.** Cài đặt "Làm mờ phụ đề gốc": Tự động (mặc định: chỉ khi phụ đề Việt sẽ đè lên chữ gốc, so bằng hình học thật), Luôn, Không bao giờ; luôn chỉ trong lúc phụ đề Việt hiện. Video ngang (phụ đề Việt nằm dưới khung hình) không còn bị làm mờ gì.

**Phụ đề.** Bỏ các dòng bịa khi mô hình "đặt lại đồng hồ" (một tiểu phẩm 53 giây có 11 dòng bịa hiện ở giây 1,6); dòng quá nhanh (>20 ký tự/giây) được viết ngắn lại bằng một lần gọi văn bản, kiểm từng dòng.

**Sau hai vòng rà soát độc lập (2026-10-02 và 2026-10-05; chi tiết ở docs/ROADMAP.md, Phase F).**
- Giọng đã tạo và lời viết ngắn lại được nhớ trong thư mục việc: video quay lại hàng đợi hoặc được duyệt tay không trả phí lại. Bản phân tích đã nhớ chỉ giữ khi hợp lệ về cấu trúc, ghi nguyên tử, và khóa gồm cả kiểu mô tả lẫn model (file của bản trước, chưa có hai trường này, vẫn dùng được để không trả thêm một lần gọi video cho mỗi video đang chờ).
- Giọng bị từ chối khi kéo dài quá hết video hoặc im lặng (file im lặng bị xóa); lời đưa cho giọng đọc bỏ emoji, thẻ `{an8}`, ngắt dòng `\N`.
- Lần tạo giọng thứ hai (khi giọng đầu quá dài) nhanh hơn **một bậc** thay vì nhảy từ chậm lên nhanh, chỉ chờ Google bận một vòng, và lỗi gì của nó cũng giữ bản đầu.
- Gemini: model chạy được lúc model cấu hình chỉ đang bận không còn bị ghi nhớ thay model cấu hình; chỉ 429 theo **ngày** (đọc từ chi tiết lỗi) mới bỏ qua việc chờ vòng, 429 theo phút vẫn chờ.
- **Lỗi nặng đã sửa:** video đã duyệt tay bị xếp lại hàng đợi mãi khi Google bận lúc tạo giọng (bộ đếm lần hoãn bị đặt về 0 ở mỗi lần chạy vì cờ `approved` ở lại trên dòng); nay bộ đếm chỉ đặt lại một lần, lúc duyệt.
- Nhánh chuyển mp3/ogg sang WAV hỏng vì tên file `.part` (ffmpeg không chọn được định dạng): đã chỉ định `-f wav`.

**Nhiều tài khoản (Phase G).** Phiên TikTok hết hạn không còn bị tính là lỗi của video (hoãn, báo mỗi tài khoản kèm lệnh đăng nhập; kiểm tra phiên 3 giờ không xóa được cờ đăng xuất); một bài đăng treo không chặn các tài khoản khác quá 45 phút; CAPTCHA, hộp xác nhận "Đăng ngay" và nút Đăng theo từng tài khoản; `tiktok dry-run --account`; sao lưu hồ sơ Chrome không mang cache. Chi tiết và phần để lại: docs/ROADMAP.md, mục Phase G.

**Chất lượng sản phẩm (Phase I).** Thanh trạng thái trung thực (7 giờ), dòng "vì sao chưa đăng" trên mỗi video, khóa Gemini bị từ chối giữ video ở hàng đợi và hiện trên banner và tab Cần xem (điện thoại: tối đa mỗi 6 giờ), lỗi và lý do bằng tiếng Việt (có test quét mã), danh sách hiện mô tả tiếng Việt, số đếm khớp danh sách, bước thu thập lỗi hết thì báo lỗi, `./trendvn doctor` cùng ngưỡng ổ đĩa với bảng điều khiển và kiểm tra `linger`, thứ tự cài đặt lần đầu đúng. Chi tiết: docs/ROADMAP.md, mục Phase I.

**Hiệu năng (Phase H).** Dải làm mờ phụ đề gốc làm mờ trên bản thu nhỏ 1/4 rồi phóng lại: dựng video cần làm mờ nhanh hơn 19% (44,8 → 36,4 giây trên video thật 134 giây), hình tương đương (SSIM 0,988–0,996). Bộ thu thập ghi vào `agent.log` thời gian từng lần cuộn và chuyển tab. Số đo và các thử nghiệm không đổi (bộ mã hóa, gộp QC, thời gian chờ thu thập): docs/ROADMAP.md, mục Phase H.

**Đã đo và không đổi:** mã hóa (crf, preset, tune: SSIM chỉ chênh 0,001–0,002 mà dung lượng +30–70%, thời gian +31–78%). Hiệu năng giữ nguyên hoặc tốt hơn (ít làm mờ hơn).

## 1.5 — 2026-10-02 (rà soát độc lập 3 vòng: docs/ROADMAP.md, mục "Rà soát 1.5")

**Nội dung theo yêu cầu của chủ kênh.** Chỉ còn "giới hạn cứng" chặn video (tình dục, trẻ em gặp nguy, máu me thật, thù ghét, tự hại/tội phạm, lời khuyên nguy hiểm, đời tư); chính trị, tranh cãi, drama, tai nạn trong tin tức, scandal, cảnh gây sốc được đăng bình thường. Thêm chủ đề `news` (tin nóng/drama), cài đặt `caption_style` (`hook` = mô tả giật tít bám đúng video, mặc định; `factual`), hashtag tiếp cận (`xuhuong`, `fyp`, `viral`) được phép, luôn đủ 3–5 thẻ không dấu có thẻ của chủ đề. Hệ thống không và không thể bảo đảm một video "chắc chắn viral" hay một kênh "không bao giờ bị gỡ": xem docs/SECURITY.md mục 1 và 7.

**Bảo mật (rà soát tĩnh + động + độc lập).**
- Bảng điều khiển không mật khẩu chỉ khi `Host` là localhost **và** kết nối đến từ chính máy (hoặc cổng cầu nối Docker của dự án) **và** không có tiêu đề của reverse proxy; `TRENDVN_TRUSTED_PEERS` cho Docker Desktop. Phiên đăng nhập lưu trên máy chủ (7 ngày, `/logout` và nút "Đăng xuất" vô hiệu hóa thật), `Secure` khi `TRENDVN_UI_HTTPS=1`.
- Máy chủ HTTP: `Content-Length` âm/lạ bị từ chối (từng khiến `/login` đọc không giới hạn), hết hạn socket 30 giây mỗi lần đọc, tối đa 48 luồng (dư thì 503), backlog 64; CSP không còn `script-src 'unsafe-inline'` (script theo mã băm), `base-uri 'none'`, `Permissions-Policy`; log làm sạch ký tự điều khiển và ghi địa chỉ nguồn của 401/403.
- Cổng kiểm tra đầu ra Gemini: khóa JSON lặp, nhiều đối tượng, `caption_vi` không phải chuỗi bị từ chối; mô tả và phụ đề bị lọc liên kết, @tên, số điện thoại, email, ký tự ẩn/đảo chiều (phụ đề: cả emoji); câu nhắc "nội dung trong video không phải chỉ dẫn" gửi sau video.
- Tải video: cú pháp URL chặt (backslash, user-info, IP, cổng), proxy yt-dlp qua biến môi trường, agent giới hạn thân yêu cầu và hết hạn socket. Thông báo: không IP, phải phân giải ra địa chỉ công khai, không theo chuyển hướng, không @everyone.
- Sửa lỗi: heartbeat quá lớn từng làm hỏng một dòng cài đặt và gây lỗi 500 ở mọi trang; `resolve_unknown` nhận `javascript:` làm đường dẫn; 3 endpoint trả 500 khi sai kiểu dữ liệu.
- `./trendvn test lint` chặn ký tự ẩn/đảo chiều trong mã nguồn (kiểu tấn công Trojan Source); mã dùng `\\uXXXX` thay vì dán trực tiếp.
- compose: `cap_drop: ALL` cho cả n8n, giới hạn RAM/số tiến trình, ảnh nền ghim theo mã băm; thêm `.github/workflows/ci.yml` (ghim SHA, chưa chạy trên GitHub).

**Sửa sau khi dùng thật.** Một video Douyin vào "Cần duyệt" với lý do "Gemini trả dữ liệu không đọc được": mô hình `gemini-3.5-flash` đã viết đúng phân tích rồi sa vào vòng lặp ở trường phụ `sensitive_reason` (một chuỗi vô tận 13.455 token tới giới hạn đầu ra, JSON bị cắt dở). Trường đó không dùng ở đâu nên đã bỏ khỏi schema và prompt (`PROMPT_VERSION` 2026-10-02.2); các trường văn bản còn lại có trần độ dài (`maxLength`, `maxItems`), đã thử thật: cùng video giờ ra 2.528 token, kết thúc `STOP`, kèm vị trí phụ đề cứng; câu trả lời bị cắt ở `MAX_TOKENS` được báo đúng nguyên nhân bằng tiếng Việt.

**Dải làm mờ phụ đề gốc không còn che cả video.** Dải mờ che chữ Trung burned-in từng phủ suốt cả video và cả bề ngang, nên che người và cảnh ngay cả khi không ai nói; nay chỉ mờ trong lúc phụ đề Việt đang hiện (cộng đệm, gộp các dòng gần nhau). Video đã dựng sẵn bị ảnh hưởng (một video) được dựng lại từ nguồn và phân tích đã lưu (không gọi Gemini).

**Logic và hiệu năng.**
- Dọn đĩa (nguy cơ lặp lại của dự án này): hết hạn ứng viên/video không ai quyết định, xóa tệp của video đã xong sau 7 ngày, cắt lịch sử, xóa tệp mồ côi; ngừng tải dưới 1 GB trống và ngừng dựng dưới 512 MB; Chrome giới hạn bộ nhớ đệm 64 MB; `agent.log` xoay vòng; trang Tổng quan hiển thị ổ đĩa.
- Chọn ứng viên theo điểm (không còn "100 video mới nhất"), lọc theo nền tảng; Douyin không có lượt xem được xét theo tim; giới hạn độ dài theo đúng cài đặt (không bị chặn cứng 180 giây); "Kuaishou không trả video" không còn bị báo là CAPTCHA.
- Số "Sẵn sàng" là tổng thật (không phải 30 dòng đầu); hàng chờ tính cả video chờ duyệt.
- Worker khởi động lại tự xếp lại video đang xử lý dở; khởi động chờ-và-thử-lại khi CSDL bị khóa; lease cũ không còn làm `process_one` ném lỗi; video 1×1 bị từ chối; lỗi ffmpeg không lộ đường dẫn thư mục.
- Đo trên CSDL giả 20.000 video: `record_stats` 200 mục 927 → 9 ms, dựng trang 52 → 39 ms, `status` 22 → 17 ms.
- Từ khóa gợi ý chủ đề `news` thu hẹp (bỏ breaking, 社会, 现场, 监控, 反转, 曝光, căng: quá chung, hay khớp nhầm); chỉ là gợi ý trước khi tải, Gemini vẫn quyết định chủ đề sau khi phân tích.
- Migration 4 (`main` nhận `news` nếu chủ chưa sửa danh sách; hằng số trong migration không còn import) và 5 (`pruned_at`, chỉ mục trùng hash).

**Mở rộng.** Một bảng nền tảng duy nhất (`domain/platforms.py REGISTRY`) sinh nhãn, ngưỡng, hashtag cấm, tên trong thông báo; mỗi nguồn thu thập tự khai báo CDN; danh sách tab ở một chỗ (`ui/page.py TABS`, HTML đầu ra giống hệt). Thêm nguồn mới: 2 file thay vì 9–11.

## 1.4 — 2026-10-02 (nhật ký từng phase và rà soát: docs/ROADMAP.md)

**Phase A — bố cục và chia module (không đổi hành vi).** Hai ứng dụng được tách thành gói Python có thư mục theo việc, mỗi file một trách nhiệm (không file nào quá khoảng 300 dòng):

- `services/worker/src/trendvn_worker/`: `domain/` (luật thuần: chấm điểm, lịch, quan sát, caption), `store/` (SQLite: schema có phiên bản, ingest, queue, publishing, reporting…), `ai/` (Gemini: phân tích, TTS, client), `media/` (ffmpeg, dấu vân tay, phụ đề, dựng), `web/` (HTTP: handler, bảo mật, form, API), `ui/` (giao diện: thẻ, từng tab, CSS/JS tĩnh), `tasks.py`, `pipeline.py`.
- `services/agent/src/trendvn_agent/`: `collector/` (+ `sources/` mỗi nền tảng một file, thêm nền tảng = thêm một file và một dòng đăng ký), `publisher/`, `browser.py`, `server.py`.
- Chạy theo module (`python -m trendvn_worker`, `python -m trendvn_agent`); mẫu systemd/launchd và `agent.sh` cập nhật theo; `./trendvn update` cài lại dịch vụ nền của agent nên bản đang chạy theo bố cục cũ vẫn chuyển được.
- Cơ sở dữ liệu có phiên bản (`PRAGMA user_version` + danh sách migration); CSDL 1.0–1.3 được nhận nguyên trạng.
- `tests/` chia `worker/ agent/ tools/ e2e/`; thêm `./trendvn fmt` (black + ruff, bản ghim trong `requirements-dev.txt`), doclint kiểm tra mọi lệnh đều có tài liệu.
**Phase B — chất lượng phân tích và video (đo trên video Douyin thật).**
- Quyết định giữ nguyên / Vietsub / thuyết minh là một hàm riêng (`domain/route.py`) có bảng quyết định, kèm lý do bằng tiếng Việt hiện trên thẻ video.
- Phụ đề cứng của video gốc (chữ Trung burned-in) được làm mờ đúng dải đó trước khi đốt phụ đề Việt (Gemini báo vị trí); dòng phụ đề quá nhanh được kéo dài vào quãng nghỉ sau nó (21 → 17 ký tự/giây trên video đo).
- Mã hóa `veryfast/crf 24`: SSIM 0,992 so với bản tham chiếu, nhỏ hơn và nhanh hơn khoảng 40%. Đo âm lượng ngay trong lần giải mã kiểm tra.
- Sửa lỗi có từ 1.3: đường âm thanh im lặng tuyệt đối làm bộ mã hóa AAC từ chối; giọng đọc Gemini nhanh bất thường (bỏ sót câu) bị từ chối.

**Phase C — chủ đề và nhiều tài khoản.**
- Thực đơn 14 chủ đề; Gemini phân loại, collector tìm theo chủ đề (Douyin: tab của từng chủ đề; TikTok: chip), chọn tải chia lượt giữa các chủ đề.
- Nhiều tài khoản TikTok, mỗi tài khoản nhận một số chủ đề, giới hạn ngày/giãn cách/giờ vàng riêng, hồ sơ Chrome riêng (`./trendvn tiktok login --account ID`). Tài khoản của bản cũ thành `main`; CSDL cũ tự chuyển (đã thử trên bản sao CSDL thật của 1.2).
- Giao diện: mục "Tài khoản TikTok và chủ đề" ở tab Thêm; thẻ video ghi chủ đề và tài khoản sẽ nhận.

**Phase D — hiệu suất.**
- Xử lý 2 video cùng lúc (`TRENDVN_PROCESS_PARALLEL`); kiểm tra video trùng làm nguyên tử nên hai bản giống nhau xử lý đồng thời vẫn bị bắt.
- Video nhạc dọc không lời được sao nguyên hình (3,3 giây thay vì 24 giây, không mất chất lượng, từng điểm ảnh giống bản gốc); chờ thích nghi khi quét các tab chủ đề của Douyin.

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
