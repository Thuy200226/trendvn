# Prompt Gemini và cách tinh chỉnh

Mọi prompt và schema gửi Gemini nằm trong **một file duy nhất**: [`services/worker/src/trendvn_worker/ai/prompts.py`](../services/worker/src/trendvn_worker/ai/prompts.py). Đổi nội dung, tăng `PROMPT_VERSION`; phiên bản được ghi vào `manifest.json` của từng video để truy vết kết quả theo prompt.

## 1. Có những lần gọi nào

| Lần gọi | Khi nào | Model mặc định | Đầu vào | Đầu ra |
|---|---|---|---|---|
| **Phân tích** (`media.analyze`) | Mỗi video được xử lý, 1 lần | `gemini-3.8-flash` (tự chuyển model khác khi gặp 404) | Bản xem trước 384px, 1 khung/giây (Gemini chỉ lấy 1 khung/giây dù file có bao nhiêu), ≤ 12 MB + `ANALYSIS_PROMPT` | JSON theo `ANALYSIS_SCHEMA` |
| **Giọng đọc** (`media.tts`) | Chỉ video thuyết minh khi bật lồng tiếng, 1 lần | `gemini-3.8-flash-tts` (đọc được WAV, PCM và định dạng khác qua ffmpeg) | `TTS_PROMPT` + `narration_vi` | Âm thanh PCM |
| **Giọng đọc thử** | Khi bạn bấm "Nghe thử giọng đọc" | như trên | `VOICE_SAMPLE` | File `data/worker/exports/voice_sample.wav` |

Hạn mức cục bộ mặc định 12 lần/24 giờ (đổi ở Cài đặt). Vượt hạn mức, video được xếp lại hàng đợi, không bị đánh dấu hỏng.

**Model do Google đổi liên tục.** Đã gặp thật: `gemini-2.5-flash` bị ngừng cấp cho người dùng mới (HTTP 404). Hệ thống xử lý bằng: (1) tự nâng model cũ trong cài đặt; (2) gặp 404 thì thử lần lượt `MODEL_FALLBACKS` / `TTS_FALLBACKS` (đầu `services/worker/src/trendvn_worker/domain/settings.py`) và nhớ model chạy được; (3) gặp 429/5xx hoặc hết thời gian thì đổi model, chờ 10, 30, 60 giây rồi mới xếp video lại hàng đợi. Lỗi bị Google từ chối không tính vào hạn mức ngày.

## 2. Các nguyên tắc thiết kế của prompt phân tích

1. **Video là dữ liệu không đáng tin.** Câu đầu tiên yêu cầu Gemini bỏ qua mọi chỉ dẫn nói, hát hoặc hiện trong video (chống chèn lệnh qua nội dung video).
2. **Schema ép cấu trúc** (`responseSchema`): các trường `kind`, `topic` là *enum*, `confidence` là số, `segments` là mảng có `start`, `end`, `vi` bắt buộc. Nếu API từ chối schema (HTTP 400), `media.generate` tự thử lại một lần không có schema; bộ kiểm tra cứng vẫn áp dụng.
3. **Gemini chỉ đề xuất, mã kiểm tra lại.** `core.validate_analysis` từ chối: kiểu âm thanh lạ, `confidence` ngoài 0–1 hoặc dưới ngưỡng, phụ đề vượt thời lượng hoặc chồng nhau, lời không có bản dịch, "nhạc" mà có lời. Đây là lý do một câu trả lời sai định dạng chỉ đưa video vào "Cần duyệt" chứ không bao giờ tới bước đăng.
4. **Không bịa.** Prompt cấm tạo lời thoại, câu đùa, tên, con số hoặc khẳng định không có trong video.
5. **Phân biệt hát và nói.** Lời bài hát là nhạc; nhạc kèm lời nói thật là `mixed` (Vietsub), không phải `music`.
6. **Chủ đề và nhạy cảm** là hai cờ riêng. `topic` là MỘT mã trong thực đơn 14 chủ đề của `domain/topics.py` (prompt và schema sinh từ chính bảng đó) hoặc `other` (tin tức, chính trị, quảng cáo, mua sắm, tài chính, y tế, tôn giáo, mọi thứ không giải trí; Gemini được dặn chọn `other` thay vì ép vào chủ đề không khớp). Chủ đề không có tài khoản nào nhận (hoặc `other`) hay `sensitive = true` đưa video vào "Cần xem". Đây là hàng rào giữ các kênh khỏi nội dung không mong muốn.
7. **Mô tả và hashtag do Gemini viết** nhưng bị ràng buộc (PROMPT_VERSION `2026-10-01.2`): mô tả là MỘT câu hoàn chỉnh, tự nhiên, 40–90 ký tự, nêu đúng điều xảy ra trong video, không lửng kiểu "và cái kết", không viết hoa toàn bộ, không hashtag trong mô tả; đúng 3–4 hashtag không dấu (một về cảm xúc/chủ đề, một về thể loại, một riêng của video), tuyệt đối không tên nền tảng, thương hiệu hay người thật. `core.build_caption` lọc lại: bỏ hashtag chứa tiktok/douyin/kuaishou/instagram/reels/fyp/viral/trending/xuhuong/capcut, chuẩn hóa Unicode, tối đa 4 hashtag của Gemini + hashtag mặc định (tổng ≤ 5), mô tả cắt ở ranh giới từ (≤ 110 ký tự). Video không có mô tả tiếng Việt thì vào "Cần xem". Chất lượng thực tế đã đo trên video thật: xem `docs/REVIEW-1.2.md`.
8. **Thuyết minh** (`narration_vi`) chỉ sinh khi `kind = narration`, với yêu cầu vừa thời lượng lời gốc; `media.make_voice` đo độ dài giọng đọc thật và từ chối nếu lệch quá (tỉ lệ ngoài 0.7–1.4), khi đó video vẫn ra với Vietsub.

## 3. Bảng quyết định sau phân tích (`domain/route.py`)

Quyết định là một hàm thuần `choose_route(kind, có_lời)` nên đọc, kiểm thử và chỉnh ở một chỗ; mỗi đường đi có **lý do bằng tiếng Việt** hiện trên thẻ video ở bảng điều khiển.

| `kind` | Điều kiện | Cách dựng | Lý do hiện cho chủ |
|---|---|---|---|
| `music` | không có lời nói | **giữ nguyên** hình và tiếng | Nhạc, không có lời nói: giữ nguyên âm thanh gốc |
| `silent` | không có tiếng | giữ nguyên (nếu có chữ trên hình cần dịch mà không có lời: vào "Cần xem") | Không có tiếng: giữ nguyên |
| `dialogue`, `mixed` | có lời | giữ tiếng gốc + **Vietsub** | Có lời nói: giữ giọng gốc và thêm phụ đề tiếng Việt |
| `music`, `silent` kèm vài câu nói | có lời | Vietsub cho phần lời nói, giữ nhạc | Video nhạc có kèm lời nói: thêm phụ đề… |
| `narration` | có thuyết minh | **Thuyết minh tiếng Việt** (bật lồng tiếng và giọng khớp): tiếng gốc còn 18% + giọng Việt + Vietsub | Người dẫn kể lại: thay bằng thuyết minh tiếng Việt |
| `narration` | lồng tiếng tắt, hoặc giọng không khớp/không tạo được | Vietsub | …chưa bật lồng tiếng / Không tạo được giọng đọc: dùng phụ đề |
| `uncertain` | Gemini không chắc | vào "Cần xem" (chủ duyệt thì quyết theo những gì nghe được) | |

Nguyên tắc chọn: **giữ nguyên** khi âm thanh gốc là giá trị chính (nhạc); **Vietsub** khi giọng và cảm xúc của người nói là giá trị (hài, phỏng vấn, đời thường); **thuyết minh** chỉ khi người dẫn chỉ đọc lời giải thích trên hình ảnh nên thay giọng không mất gì.

### Chất lượng phụ đề và dựng (Phase B, đã đo trên video thật)

- **Phụ đề cứng của video gốc** (chữ Trung burned-in thường thấy ở Douyin/Kuaishou) bị phụ đề Việt đè nửa chừng và hiện ra lộn xộn. Gemini nay báo `hard_subtitles {present, top, bottom}` (tỉ lệ chiều cao hình); `domain/hardsubs.py` kiểm tra rồi thêm lề 1,2%; `media/render.py` làm mờ và hạ sáng đúng dải đó trước khi đốt phụ đề Việt. Dải sai hoặc vô lý (cao quá 30%, ngược, không phải số) bị bỏ qua, không làm hỏng video. Video **giữ nguyên** (nhạc) không bị làm mờ, nên lời bài hát burned-in còn nguyên.
- **Tốc độ đọc** (`domain/readability.py`): prompt yêu cầu ≤ 16 ký tự/giây; mã kéo dài thời gian hiện của dòng quá nhanh vào quãng nghỉ sau nó (tối đa +1 giây, không đè dòng kế, không quá hết video). Trên video thật: dòng nhanh nhất giảm từ 21 xuống 17 ký tự/giây. Còn nhanh quá 24 thì thẻ video báo cảnh báo.
- **Mã hóa**: `libx264 -preset veryfast -crf 24`, trần 4 Mb/s. Đo với bản tham chiếu crf 12 trên clip thật: SSIM 0,992 (mắt thường không thấy khác), file nhỏ hơn khoảng 40% và dựng nhanh hơn khoảng 40% so với `fast/crf 23` cũ.
- **Âm lượng**: giữ `loudnorm` -14 LUFS (đo thực tế: nhạc live -10 LUFS về -14,1; lời thoại -14,6 về -14,5). Âm lượng và đỉnh của bản dựng được đo ngay trong lần giải mã kiểm tra (không thêm lần đọc file), hiện trong thông tin video; video im lặng hoặc quá nhỏ (< -35 LUFS) có cảnh báo.
- **Giọng đọc**: thử bắt Gemini đọc nhanh (16,6 ký tự/giây): nó **bỏ sót cả câu** (nghe lại bằng chính Gemini chỉ khớp 79% số từ), còn tốc độ mặc định (9,6 ký tự/giây) khớp 100%. Vì vậy giữ prompt mặc định, để `atempo` tăng tốc tới 1,4 lần cho vừa cửa sổ lời, và thêm chốt: giọng đọc nhanh hơn 14 ký tự/giây bị từ chối (video dùng Vietsub thay thế).

## 4. Tinh chỉnh thực tế

| Muốn | Sửa ở đâu |
|---|---|
| Phụ đề văn phong khác (trẻ trung hơn, trang trọng hơn) | mục 5 trong `ANALYSIS_PROMPT` (yêu cầu về `vi`) |
| Mô tả bài đăng ngắn hơn/dài hơn, thêm emoji | mục 7 của prompt và `build_caption` (giới hạn 150 ký tự) |
| Thêm chủ đề được phép (ví dụ thể thao) | `topic` (prompt + `enum` trong schema + `validate_analysis`) |
| Khắt khe hơn với nội dung nhạy cảm | mục 4 của prompt; hạ `audio_confidence` xuống thấp hơn không cần, cứ tăng lên 0.95 |
| Giọng đọc khác | ô "Giọng đọc" ở Cài đặt (Kore, Puck, Charon...); nghe thử trước |
| Giọng đọc nhanh/chậm, ấm hơn | `TTS_PROMPT` |
| Đổi model | `model` và `tts_model` trong bảng `settings` của SQLite (hoặc thêm vào form nếu cần) |

Sau mỗi lần đổi prompt: bật "Duyệt tay trước khi đăng" trong vài video để so sánh, và chạy `./trendvn test unit` (có `PromptTests` kiểm tra schema và prompt còn nhất quán).

## 5. Vì sao dùng bản xem trước 384px

Video gửi Gemini đã hạ còn 384px, 1 khung/giây, âm thanh 48 kbps, ≤ 12 MB: đủ để nhận giọng nói, chữ trên hình và kiểu nội dung, nhưng rẻ và nhanh hơn nhiều so với video gốc. Video dựng cuối cùng vẫn từ file gốc chất lượng cao.
