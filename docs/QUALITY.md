# Chất lượng đầu ra: đo gì, thấy gì, chọn gì (bản 1.6, 2026-10-02)

Mọi con số dưới đây đo thật (video Douyin thật, API Gemini thật, ffmpeg thật) ngày 2026-10-02; chỗ nào chưa đo được thì ghi rõ. Nguyên tắc: **đo trước, chỉ đổi khi có bằng chứng, giữ tốc độ**.

## 1. Lỗi lớn nhất tìm được: giọng đọc đọc luôn câu hướng dẫn

Các model TTS mới (`gemini-3.x-flash-tts`) coi trường `text` là **bản chép nguyên văn**. Bản cũ đặt trước văn bản một câu hướng dẫn ("Đọc bằng tiếng Việt tự nhiên... chỉ đọc đoạn sau") nên giọng **đọc to cả câu đó** rồi mới đọc lời thuyết minh. Đo bằng cách nghe lại (chép lại âm thanh bằng một model khác):

| Cách gọi | Độ dài âm thanh | Tốc độ | Từ được đọc đúng / từ nghe thấy |
|---|---|---|---|
| Bản cũ: câu hướng dẫn + văn bản (`generateContent`) | 18,2 s | 7,3 ký tự/s | 1,00 / **0,50** (nửa số từ là câu hướng dẫn) |
| Chỉ văn bản (`generateContent`) | 8,2 s | 16,2 ký tự/s | 1,00 / 1,00 |
| Chỉ văn bản (Interactions API) | 8,0 s | 16,5 ký tự/s | 1,00 / 1,00 |

Hệ quả cũ: lời thuyết minh trông "quá dài" so với cửa sổ lời, bị tăng tốc hoặc từ chối (video rơi về Vietsub), và niềm tin "Gemini đọc tiếng Việt khoảng 9,5 ký tự/giây, bắt đọc nhanh thì bỏ sót câu" **sai**: tốc độ tự nhiên là 16–19 ký tự/giây và không bỏ sót chữ nào.

Sửa: văn bản gửi đi **chỉ là lời thuyết minh**; giọng, sắc thái và tốc độ đi riêng trong `speech_metadata.style` của Interactions API (`ai/tts.py`). Model cũ hơn vẫn nhận lời hướng dẫn dưới dạng chữ đứng trước. Có test khóa điều này (`test_the_text_is_sent_as_the_transcript...`).

## 2. Tốc độ đọc điều khiển bằng lời, không bằng cách ép âm thanh

Cùng một câu 134 ký tự, giọng Kore, mọi từ đều được đọc (recall 1,00):

| Style gửi kèm | Độ dài | Tốc độ |
|---|---|---|
| không | 6,9 s (lần khác 8,2 s) | 16–19 ký tự/s |
| "chậm rãi, trầm ấm, nhấn nhá rõ ràng" | 11,0 s | 12,0 |
| "nghiêm túc như bản tin thời sự" | 8,3 s | 15,9 |
| "nhanh, hào hứng, đầy năng lượng" | 5,6 s | 23,6 |

Vì vậy `make_voice` chọn nhịp theo số ký tự cần nói mỗi giây trong cửa sổ lời (dưới 14,5: chậm; trên 19: nhanh), gọi TTS, nếu dài hơn cửa sổ quá 15% thì gọi **một lần nữa, nhanh hơn một bậc** (chậm → thường → nhanh; nhảy thẳng từ chậm lên nhanh vượt quá cửa sổ nên bản thứ hai không bao giờ gần hơn bản đầu). Lần gọi thứ hai chỉ cải thiện bản đã có nên chỉ chờ Google bận một vòng (tối đa 25 giây) và lỗi gì cũng giữ bản đầu; bản nào gần cửa sổ hơn thì được dùng. Sau đó chỉ chỉnh tốc độ tối đa +25% (không bao giờ chậm quá 8%). Từ chối và video giữ phụ đề khi: dài hơn cửa sổ 25%, ngắn hơn một nửa cửa sổ, nhanh quá 24 ký tự/giây, giọng kéo dài quá hết video hơn 0,3 giây (chỉ xảy ra với cửa sổ lời ngắn hơn 2 giây ở cuối video), hoặc giọng im lặng (dưới -50 LUFS; file đó bị xóa để lần chạy lại tạo giọng mới thay vì đọc lại đúng đoạn im lặng). Giọng đã tạo được nhớ trong thư mục việc theo (lời, giọng, nhịp): video quay lại hàng đợi hoặc được duyệt tay không phải tạo, không phải trả phí lại. Lời đưa cho giọng đọc đã lọc như chú thích (không liên kết, số điện thoại, emoji, thẻ `{an8}`, ngắt dòng `\N`). Nhịp tự nhiên giữ chất lượng giọng tốt hơn kéo giãn âm thanh.

## 3. Chọn giọng theo người nói

Gemini nay báo thêm `speaker` (giới tính, sắc thái, số người nói) và `dub_ok` (thay giọng có mất gì không). Giọng nam không bị lồng bằng giọng nữ. Đã kiểm chứng bằng cách để một model khác nghe từng giọng đọc cùng một câu:

| Giọng | Nghe ra | Dùng cho |
|---|---|---|
| Kore | nữ, trưởng thành, vừa | nữ: bình tĩnh, nghiêm túc, kịch tính |
| Aoede | nữ, trẻ, thân thiện | nữ: ấm áp, nhẹ nhàng |
| Leda | nữ, trẻ, thân thiện | nữ: sôi nổi, tinh nghịch (và trẻ em) |
| Zephyr | nữ, trẻ | (chưa dùng) |
| Orus | **nam**, trưởng thành | nam: mọi sắc thái |

**Chưa nghe được**: Puck, Charon, Fenrir, Achird, Sadaltager, Algieba, Gacrux, Sulafat, Callirrhoe, Despina (Google ghi Puck, Charon, Fenrir, Orus... là giọng nam; chưa có bằng chứng của chính ta). Lúc đó hạn mức ngày của khóa Gemini hết (HTTP 429 "exceeded your current quota"), nên chỉ có một giọng nam được xác nhận và bảng `POOLS` (`domain/voices.py`) chỉ dùng giọng đã nghe. Muốn thêm: gọi TTS cùng một câu với giọng đó, nhờ model nghe và hỏi giới tính/độ tuổi (xem `docs/PROMPTS.md`, mục TTS), rồi thêm vào `GENDER` và `POOLS` cùng một test.

## 4. Lồng tiếng được ưu tiên khi phù hợp

- `narration` (người dẫn kể lại): lồng tiếng như cũ.
- Một người nói và Gemini cho `dub_ok = true` (giải thích, hướng dẫn, đọc tin, đánh giá sản phẩm, vlog kể chuyện): lồng tiếng. Phạm vi chỉnh ở "Lồng tiếng cho" (`voiceover_scope`: `monologue` mặc định hoặc `narration`).
- Hài, kịch, tranh cãi, cảnh xúc động, hát, nhiều người nói: giữ giọng gốc và Vietsub. Đo thật: video tiểu phẩm 2 người (53 giây) được Gemini xếp `dub_ok = false`, `count = 2`, sắc thái "tinh nghịch" → Vietsub, đúng.
- Công tắc tổng "Lồng tiếng Việt" nay **bật mặc định**. Google bận lúc tạo giọng thì video quay lại hàng đợi (phân tích đã nhớ trong `jobs/<id>/analysis.json`, chờ không tốn thêm lượt gọi video), tối đa 4 lần rồi mới ra với Vietsub.

## 5. Âm thanh khi lồng tiếng

Bản cũ: giọng lồng trộn với tiếng gốc hạ cố định còn 18% **suốt cả video**. Nay: giọng được cân riêng (-16 LUFS) rồi mới trộn; tiếng gốc chỉ hạ còn 14% (khoảng -17 dB) **trong cả cửa sổ lời gốc** (từ 0,3 s trước giọng đến hết cửa sổ hoặc hết giọng, cái nào muộn hơn, rồi ra mềm 0,5 s; một giọng ngắn hơn lời gốc không trả tiếng gốc về âm lượng đầy khi người gốc còn đang nói) và giữ nguyên ở đoạn đầu, đoạn nghỉ và đoạn cuối; cả bản trộn vẫn đưa về -14 LUFS như mọi video. Đo bằng ffmpeg thật: tiếng gốc (300 Hz) thấp hơn **trên 8 dB** dưới giọng so với trước và sau giọng (`test_the_bed_is_lower_under_the_voice_than_outside_it`). Sau bản trộn có thêm bộ giới hạn đỉnh (`alimiter`, -1,5 dBFS) vì người phản biện đo được đỉnh vượt 0 dBTP sau AAC trên nền nhạc xung (+3,9 dBTP khi không có, +0,3 khi có). **Giới hạn của phép đo:** trên 7 nền nhạc tôi tự dựng (xung thưa/dày, vuông, đá trống, cắt cứng, to rồi nhỏ) bộ giới hạn đổi đỉnh không quá 0,3 dB theo cả hai hướng và mọi đỉnh đều dưới -2,7 dBTP, nên **không có test nào phân biệt được có hay không có nó** (chỉ có test kiểm nó nối đúng chỗ); và nó chưa bảo đảm không vượt 0 dBTP (nền của người phản biện vẫn ra +0,3).

## 6. Làm mờ phụ đề gốc: chỉ khi cần, chỉ lúc cần

Bản đầu làm mờ một dải ngang **suốt cả video** nên che người và cảnh ngay cả khi không ai nói. Nay quyết định theo điều kiện (cài đặt "Làm mờ phụ đề gốc"):

| Chế độ | Làm gì |
|---|---|
| Tự động (mặc định) | Chỉ làm mờ khi **phụ đề Việt sẽ đè lên dải chữ gốc** (so hình học thật của hộp phụ đề với dải Gemini báo, có đệm 1,5% chiều cao), và chỉ trong lúc phụ đề Việt hiện (+0,5 s trước, +0,6 s sau, gộp các dòng cách nhau dưới 1,5 s) |
| Luôn | Làm mờ khi biết dải chữ gốc, vẫn chỉ trong lúc phụ đề Việt hiện |
| Không bao giờ | Không làm mờ |

Hệ quả hình học (có test): video **ngang** đưa vào khung dọc đặt phụ đề Việt **dưới khung hình** nên không bao giờ đè chữ gốc → chữ gốc giữ nguyên, hình không bị che. Video dọc có chữ gốc ở đúng chỗ phụ đề Việt (khoảng 70–76% chiều cao) → làm mờ đúng lúc; chữ gốc ở sát đáy (dưới vùng TikTok che) hoặc ở cao → để nguyên. Video nhạc giữ nguyên không bao giờ bị làm mờ (giữ lời bài hát). Dải Gemini báo không dùng được (thiếu `bottom`, cao quá 30%) bị bỏ qua. Thẻ video trên bảng điều khiển ghi rõ đã làm mờ hay để nguyên.

## 7. Phụ đề: bớt lời bịa và bớt quá nhanh

- **Dòng bịa**: một video tiểu phẩm 53 giây trả về 11 dòng thật rồi 11 dòng nữa với mốc 1,0–2,1 giây (mô hình "đặt lại đồng hồ" và viết tiếp); sắp xếp theo thời gian thì dòng thật đầu tiên bị cắt ngắn và một dòng bịa hiện ở giây 1,6. Nay phát hiện đồng hồ bị đặt lại và phần đuôi toàn dòng dài trong chưa đầy nửa giây thì bỏ cả đuôi; dòng lẻ "hơn 20 ký tự trong dưới 0,5 giây" cũng bỏ, và một đuôi từ 4 dòng trở lên dồn trong một khoảng ngắn đến mức cộng lại hơn 30 ký tự/giây cũng bỏ nốt (kiểm bằng dữ liệu của người phản biện: 11 dòng bịa dài 0,6 giây vẫn bị loại) (`domain/analysis.py`). Nhóm dòng theo người nói (hợp lệ) vẫn được giữ.
- **Quá nhanh**: Gemini hay viết 25 ký tự/giây cho các câu qua lại nhanh (mục tiêu 16). Sau khi mượn thời gian từ quãng nghỉ, dòng còn nhanh hơn 20 ký tự/giây được viết ngắn lại bằng **một lần gọi văn bản** (hoạt động cả khi API video quá tải), mỗi dòng được kiểm riêng, dòng nào không đạt giữ nguyên lời cũ (`ai/condense.py`).

## 8. Mã hóa và tốc độ dựng: đo xong, không đổi

Đoạn 30 giây của video ngang 1080p (nguồn 1,9 Mb/s) dựng lên khung 1080×1920 với nền mờ; SSIM so với bản tham chiếu `crf 12 slow`:

| Thiết lập | Thời gian | Dung lượng | SSIM |
|---|---|---|---|
| **hiện tại** veryfast, crf 24, tối đa 4 Mb/s | **7,6 s** | **8,5 MB** | 0,9927 |
| veryfast, crf 22, 4 Mb/s | 7,9 s | 10,9 MB (+29%) | 0,9940 |
| veryfast, crf 20, 6 Mb/s | 8,0 s | 14,4 MB (+69%) | 0,9951 |
| faster, crf 22, 6 Mb/s | 11,2 s (+48%) | 13,1 MB | 0,9948 |
| fast, crf 22, 6 Mb/s | 13,5 s (+78%) | 13,5 MB | 0,9952 |
| veryfast, crf 24, `-tune film` | 10,0 s (+31%) | 8,5 MB | 0,9927 |

Chênh SSIM chỉ 0,001–0,002 (mắt không phân biệt được) trong khi dung lượng tăng 30–70% và thời gian tăng đến 78%; nguồn Douyin chỉ 1–2 Mb/s nên thêm bit không lấy lại được chi tiết đã mất. **Giữ nguyên.** Thông số TikTok khuyến nghị (1080×1920, H.264, 30 fps, tối thiểu 720×1280) đã đạt; bản dựng chạy nhanh khoảng 4 lần thời gian thực. Đo lại bằng ffmpeg thật (người phản biện, video 60 giây, trung vị 3 lần): dựng Vietsub 21,5 s → 20,5 s, dựng lồng tiếng 21,9 s → 22,0 s; riêng nhánh âm thanh +1 s (thêm `loudnorm` cho giọng và bộ giới hạn đỉnh). Việc làm mờ vẫn chạy bộ lọc mờ mỗi khung hình (chỉ phần dán lên được bật/tắt theo thời gian), nên tiết kiệm nằm ở chỗ video ngang và dải thấp không còn bị dán gì, không phải ở thời gian lọc.

## 9. Giới hạn của các phép đo này

- Không có tai người: "giọng nghe hay" được kiểm bằng cách nhờ một model khác nghe và chép lại (độ chính xác từng chữ, giới tính, tuổi, nhịp), không phải bằng thẩm mỹ. Hãy bấm "Nghe thử giọng đọc" ở Thêm → Cài đặt và nghe vài video thật trước khi tin.
- Hạn mức ngày của khóa Gemini hết giữa chừng nên bộ giọng nam, và việc chạy lại trọn vẹn một video lồng tiếng từ đầu tới cuối trên API thật (phân tích → giọng → dựng), chưa làm được. Phần ghép giọng, trộn âm và dựng đã chạy thật bằng ffmpeg với âm thanh giả; phần gọi TTS đã chạy thật ở mức từng lần gọi.
