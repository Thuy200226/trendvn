# AGENTS.md - quy tắc cho mọi agent làm việc trong repo này

Đọc file này trước khi sửa bất cứ thứ gì. Người dùng viết tiếng Việt: trả lời bằng tiếng Việt, rõ ràng, không khoe.
Các chuẩn dùng chung cho mọi dự án (bố cục và module, **bảo mật**, **hiệu năng và tốc độ**, kiểm thử, CI/CD và triển khai, quy trình 3 vòng rà soát) nằm trong skill
`engineering-standards`: bản trong repo ở [skills/engineering-standards](skills/engineering-standards/SKILL.md), cài cho mọi dự án bằng
`cp -r skills/engineering-standards ~/.claude/skills/`. Nếu skill đã cài, hãy dùng nó; file này chỉ ghi những gì **riêng của repo này**.
Mẫu AGENTS.md dùng lại cho dự án khác: `skills/engineering-standards/assets/AGENTS-template.md`.

## Dự án là gì
TrendVN thu thập video xu hướng (Douyin, Kuaishou; TikTok, Instagram cần IP Mỹ), thêm Vietsub hoặc thuyết minh tiếng Việt bằng Gemini, rồi đăng lên một hoặc nhiều tài khoản TikTok qua Chrome thật (không dùng API TikTok), theo lịch của n8n riêng của dự án.
Ba khối: **worker** (Docker: hàng đợi, luật, Gemini, ffmpeg, bảng điều khiển), **agent** (máy chủ: Chrome + Playwright, dịch vụ nền `trendvn-agent`), **n8n** (chỉ hẹn giờ và nối bước).

## Lệnh (một cửa duy nhất: `./trendvn`)
| Việc | Lệnh |
|---|---|
| Kiểm thử nhanh (lint + unit) / đầy đủ (thêm Docker và Chrome thật) | `./trendvn test` / `./trendvn test all` |
| Định dạng mã | `./trendvn fmt` |
| Áp dụng mã mới vào hệ thống đang chạy | `./trendvn update` |
| Chẩn đoán | `./trendvn doctor` |
| Đóng gói | `./trendvn package` |
Toàn bộ lệnh: `docs/COMMANDS.md`. Tiến độ và nhật ký rà soát từng phase: `docs/ROADMAP.md` (đọc trước khi tiếp tục công việc dang dở).

## Bố cục (mỗi file một trách nhiệm, ghi ở dòng docstring đầu file)
- `services/worker/src/trendvn_worker/`: `domain/` (luật thuần, không I/O) -> `store/` (SQLite, mỗi mối quan tâm một mixin) -> `ai/`, `media/` (Gemini, ffmpeg) -> `web/`, `tasks.py`, `pipeline.py` -> `ui/` (mỗi tab một file).
- `services/agent/src/trendvn_agent/`: `collector/` (`sources/<nguồn>.py` + đăng ký một dòng trong `sources/__init__.py`), `publisher/`, `browser.py`, `server.py`.
- `tests/{worker,agent,tools,e2e}` phản chiếu mã; `tests/support.py` là chỗ chung. `docs/` là tài liệu; `data/` và `.env` là trạng thái và bí mật (không bao giờ đóng gói hay commit).
- Hàm dài quá khoảng 60 dòng thì tách bước có tên. Thêm nguồn, tab, chủ đề mới = thêm một file và một dòng đăng ký, không sửa xuyên năm file.

## Cách làm việc
1. Đọc `docs/ROADMAP.md` và chạy `./trendvn test` để biết nền trước khi đổi.
2. Mỗi phase có mục tiêu đo được, và kết thúc bằng **3 vòng rà soát**: tĩnh (tự đọc lại + công cụ), động (chạy trên dữ liệu và hệ thống thật, có số đo trước/sau), độc lập (tác tử chỉ-đọc được giao phá mã; mẫu prompt ở skill). Sửa hết phát hiện, thêm test chặn lại, ghi vào ROADMAP rồi mới sang phase khác.
3. **Đo trước khi tối ưu**; chỉ đổi cái số liệu ủng hộ; ghi cả thử nghiệm không hiệu quả. Đừng so sánh lặp lại với trang đang giới hạn mình (Kuaishou): kết quả bị nhiễu, giữ hành vi đã chứng minh.
4. Tách commit "tái cấu trúc không đổi hành vi" khỏi commit đổi hành vi. Tái cấu trúc phải được kiểm độc lập (so cũ-mới), vì test sẵn có không bắt hết.
5. Mỗi lỗi sửa xong có test thất bại nếu bỏ bản sửa. Cập nhật `CHANGELOG.md` và tài liệu cùng lúc với mã; `scripts/doclint.py` (chạy trong `./trendvn test lint`) bắt tài liệu lệch mã.
6. Báo cáo trung thực: cái gì đã kiểm chứng (kèm số), cái gì **chưa** kiểm chứng và vì sao, việc nào chỉ người dùng làm được.

## Chất lượng
- Công cụ định dạng và lint **ghim đúng phiên bản** trong `requirements-dev.txt` (black, ruff): bản khác cho kiểu mã khác. Không có đúng bản thì `./trendvn test lint` tự bỏ qua kèm thông báo; dựng venv phát triển riêng (ví dụ ở thư mục tạm) bằng `pip install -r requirements-dev.txt` và đặt nó đầu `PATH`. Đừng dùng black của anaconda/hệ thống: nó định dạng lại file khác đi.
- Test không được ghi vào `data/` hay `agent.log` thật (`tests/support.py` đã chuyển hướng log); test đổi trạng thái chung (tài khoản, cài đặt) dùng máy chủ/CSDL riêng.
- Bộ test đầy đủ chạy cả trong image Docker (có ffmpeg thật); host không có ffmpeg sẽ bỏ qua một số test. Nếu Docker Hub không với tới được, chạy bước container bằng tay trong image sẵn có và nói rõ.
- Bố cục e2e đo sau khi trang đã đứng yên; sau khi thêm giao diện, chạy `./trendvn test e2e` (Chrome thật, 7 cỡ màn hình, ô chạm >= 44 px).

## An toàn (bắt buộc)
- Hệ thống thật đang chạy trong thư mục này: container `trendvn-*`, dịch vụ nền `trendvn-agent`, cổng 5680-5682, `data/`. **Không bao giờ** chạy thử lệnh phá hủy (down, restore, uninstall, xóa volume) trên project mặc định; test như vậy phải export `COMPOSE_PROJECT_NAME` riêng và kiểm ID container trước/sau. `guard_project` chặn lệnh thay đổi khi project thuộc thư mục khác (`TRENDVN_ALLOW_TAKEOVER=1` chỉ chủ dùng).
- **Không đăng thật lên TikTok** nếu người dùng chưa đồng ý rõ cho đúng lần đó; không xóa bài đã đăng; không bao giờ giải hay né CAPTCHA (hệ thống chỉ phát hiện, tạm dừng, báo chủ). Công tắc "Tự đăng" và việc bật lịch n8n là việc của người dùng.
- Không xóa vĩnh viễn dữ liệu hay thư mục cũ của người dùng: đưa lệnh chính xác và cảnh báo (đừng `docker compose down -v` ở thư mục cũ vì volume `trendvn_n8n_data` giờ thuộc hệ thống này).
- Bí mật (`.env`, `data/worker/gemini.key`, phiên Chrome trong `data/agent/profiles`) không vào git, gói, log, API, hay thư mục tạm; nếu buộc phải chép để thử thì xóa ngay.
- CSDL có phiên bản (`PRAGMA user_version`); migration mới chạy trong một giao dịch cùng việc nâng phiên bản và thử trên bản sao CSDL thật.
- Subagent rà soát phải chỉ-đọc, dùng thư mục tạm, không chạm hệ thống thật, không gọi Gemini, không mở TikTok/Douyin. Đừng sửa file mà họ đang đọc.

## Bẫy đã gặp (đừng lặp lại)
- Ổ đĩa luôn gần đầy (~1-2 GB trống): không tạo tệp lớn, xóa video thử ngay; `./trendvn doctor` báo.
- Gemini thường trả 503 kéo dài cho video (văn bản thì chạy được): coi là "xếp hàng lại", không phải video hỏng; đừng chỉnh `thinkingConfig`/độ phân giải khi không đo được (tham số sai làm hỏng mọi lần gọi).
- `loudnorm` trên âm thanh toàn số 0 cho NaN: video `silent` không chỉnh âm lượng. Bắt Gemini TTS đọc nhanh làm nó bỏ sót câu: giữ tốc độ mặc định và chốt `MAX_CHARS_PER_SECOND`.
- Douyin: tìm kiếm ra CAPTCHA; dùng các tab chủ đề của trang `jingxuan` (bấm bằng `dispatch_event` vì cửa sổ đăng nhập chặn chuột). Kuaishou chỉ có một luồng cho khách và hạn chế khi tải lặp; chờ thích nghi chỉ dùng cho Douyin.
- Khi đổi mã nguồn thực thể chạy (`./trendvn update`), đừng quên dịch vụ nền của agent cũng được cài lại; kiểm `./trendvn doctor` sau đó. Máy có thể khởi động lại và xóa `/tmp`: dựng lại công cụ phát triển từ phiên bản ghim.
- Nhiều tài khoản: mỗi tài khoản một hồ sơ Chrome (`publisher` cho `main`, `publisher-<mã>` cho còn lại); phải kiểm tên đăng nhập thật trước khi đăng; tài khoản chưa đăng nhập bị bỏ qua và không tính là lỗi của video.

## Chưa kiểm chứng được (cập nhật khi thay đổi)
Gemini thật báo vị trí phụ đề cứng (API video hay quá tải), nguồn Mỹ (cần IP Mỹ), đăng thật lên nhiều tài khoản, macOS thật, chạy dài ngày theo lịch thật. Link chia sẻ thật từ ứng dụng TikTok (dạng tham số chỉ người chia sẻ), tìm video thật trên TikTok/Douyin cho khung chat tìm sản phẩm (hay gặp xác minh).
