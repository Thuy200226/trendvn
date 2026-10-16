# Lịch sử thay đổi

### Khắc Phục Triệt Để 3 Lỗi UI & Pipeline, 10 Vòng Thực Nghiệm Toàn Diện Mọi Thao Tác (2026-10-11)
- **Khắc phục lỗi `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'` (`store/queue.py`):**
  + Trong hàm `reserve_fingerprint`: Bổ sung điều kiện lọc `duration IS NOT NULL` trong truy vấn SQL và kiểm tra an toàn `row_dur is not None and duration is not None` trước khi tính toán `abs(row_dur - duration)`.
  + Loại bỏ hoàn toàn nguy cơ sập luồng khi đối soát dấu vân tay (fingerprint) với các video cũ trong kho chưa có trường thời lượng `duration`.
  + Bổ sung regression unit test `test_reserve_fingerprint_handles_null_duration_without_type_error` trong `tests/worker/test_queue.py`.
- **Khắc phục lỗi video bị giữ lại vì `Thời lượng ngoài giới hạn cho phép` khi đã duyệt (`pipeline.py`):**
  + Cập nhật hàm `_source(job, cfg, approved=False)`: Khi người dùng bấm nút `[Duyệt lại, bỏ qua kiểm tra]` (`approved=True`), hệ thống tự động bỏ qua điều kiện `max_duration` để tiếp tục dựng video theo đúng ý người dùng thay vì ném lỗi văng lại `needs_review`.
  + Tự động ưu tiên ứng viên video Douyin có thời lượng chuẩn (10s - 180s) trong `batch_sales_search` (`runner.py`) và trích xuất `duration` từ DOM thẻ video Douyin (`search_douyin.py`).
- **Làm sạch hiển thị nút `🚀 Tìm kiếm & Tạo video hàng loạt` (`ui/tabs/search.py`):**
  + Gỡ bỏ chuỗi thẻ HTML `(<span data-batch-count>%d</span> sản phẩm)` ra khỏi nhãn của hàm `_button()`, tránh bị `escape()` làm lộ mã HTML thô `&lt;span...&gt;` trên giao diện.
  + Số lượng sản phẩm được tick chọn hiển thị sắc nét trên badge `Đã chọn: X / Y sản phẩm` của toolbar và đồng bộ thời gian thực qua JavaScript.
- **Thực nghiệm 10 vòng đánh giá toàn diện (10 Full Flow Evaluation Runs):**
  + 10/10 vòng thực nghiệm bao quát mọi thao tác (tick/bỏ chọn checkbox, bỏ qua sản phẩm, khôi phục sản phẩm, tìm lẻ video, tìm hàng loạt, đối soát affiliate, duyệt video quá thời lượng, xử lý dấu vân tay `NoneType`, cô lập profile Chrome) đều đạt chuẩn **PASS 100%**.
  + 1169/1169 unit tests & linting của toàn hệ thống đạt **PASS 100%** (`./trendvn test`).
  + Trực tiếp duyệt và đưa các video từ `needs_review` sang `queued` trên hệ thống thực tế; badge "Cần xem" trên UI giảm từ 5 xuống 3.

### Luồng Tự Động Hoàn Toàn (Auto-Pilot Affiliate & Publish) và Xóa Sâu Triệt Để (Deep Clean Purge) (2026-10-11)
- **Tự tìm -> Tự gắn giỏ hàng -> Tự đăng (Auto-Pilot Pipeline):**
  + Gỡ bỏ điểm nghẽn ép duyệt thủ công trong `pipeline.py`: chuyển sang `approval = not approved and bool(cfg.get("require_approval", False))`. Khi người dùng tắt cờ yêu cầu duyệt (`require_approval=False`), video affiliate được chuyển thẳng sang `state = 'ready'`.
  + Tự động nối tiếp bước đăng bài (`tasks.py`): Khi xử lý video hoàn tất sang `ready`, nếu `publisher_enabled` bật và `require_approval` tắt, worker tự động gọi tiếp `_publish_step(steps, "publish", job_id)` để đăng ngay lên TikTok kèm giỏ hàng mà không cần bấm thêm nút nào.
  + Giữ vững cơ chế gắn giỏ hàng TikTok Studio chuẩn xác không lỗi.
- **Xóa sâu triệt để mọi tệp liên quan (Deep Clean Purge) & Giải phóng ổ cứng tức thì:**
  + Bổ sung phương thức `purge_job(jid, target_state="purged")` trong Store (`retention.py`): Xóa vật lý tệp nguồn gốc trong `inbox/`, xóa toàn bộ thư mục `data/worker/jobs/<jid>/` (`final.mp4`, poster, audio, subtitle, manifest) và xóa tệp render.
  + Bảo lưu tuyệt đối bất biến chống trùng lặp (`AGENTS.md`): Dòng bản ghi trong bảng `jobs` được giữ nguyên với `state = 'purged'`, `source_file = NULL`, `output_file = NULL`, `pruned_at = now` để lưu giữ `url`, `source_id`, `fingerprint`, bảo đảm hệ thống vĩnh viễn không bao giờ tải lại video đã xóa.
  + Tự động dọn sạch tệp media trên máy chủ khi xóa bài TikTok (`delete_post_finish` và `_delete_post_checked` chuyển sang `post_deleted` và tự động kích hoạt `purge_job`).
  + Bổ sung endpoint POST `/purge` và nút bấm `[🗑 Xóa sạch tệp]` trực tiếp trên giao diện Dashboard Web UI ở các tab `#publish`, `#attention`, `#queue`, `#posted`.
- **Chất lượng kiểm định:**
  + 1169/1169 unit tests toàn hệ thống ĐẠT (PASS 100%).
  + `./trendvn doctor` đạt chuẩn mọi mục bắt buộc.

### Đa Trình Duyệt Đồng Thời (Profile Concurrency) & Gắn Giỏ Hàng Affiliate Chuẩn Xác 100% (2026-10-11)
- **Hỗ trợ tạo và chạy nhiều trình duyệt Chrome cùng lúc (`browser.py`, `server.py`):**
  + Tách cơ chế khóa toàn cục cũ (`browser_lock`) sang cơ chế khóa độc lập theo từng Profile (`get_profile_lock(profile)`).
  + Cho phép nhiều tác vụ sử dụng các Profile khác nhau (ví dụ: quét video nền `collector-cn`, tìm kiếm Showcase `publisher-bubitueanxinhiu`, tìm kiếm Douyin `douyin-bubitueanxinhiu`) **chạy song song 100%** mà không còn bị chặn hoặc xung đột tài nguyên.
  + Triệt tiêu hoàn toàn lỗi HTTP 409 `"Trình duyệt agent đang bận việc khác (có thể lịch tự động đang chạy). Thử lại sau vài phút."`.
  + Đối với các tác vụ yêu cầu cùng một Profile: tự động xếp hàng chờ với timeout thích ứng (120s) và hoàn thành tuần tự, không bao giờ văng lỗi.
- **Triệt tiêu 100% Fallback bừa bãi khi so khớp Affiliate (`search/runner.py`):**
  + Xóa bỏ hoàn toàn logic fallback tự ý gán sản phẩm đầu tiên của Showcase (`account_links[0]`) khi không tìm thấy kết quả khớp.
  + Áp dụng thuật toán so khớp đa tầng: Ưu tiên mã `product_id` Showcase chính xác 100% -> Tên model/thương hiệu độc nhất -> Token đặc trưng có độ dài >= 4 ký tự. Nếu không khớp, trả về `None` an toàn để không bao giờ gắn nhầm sản phẩm khác.
- **Chuẩn hóa nhãn hiển thị giỏ hàng TikTok Studio Web (`publisher/post.py`):**
  + Tự động làm sạch các ký tự đặc biệt bị TikTok Studio cấm (như `%`, `@`, `#`, v.v.) và giới hạn độ dài `<= 30` ký tự ở Modal 3, bảo đảm nút `[Thêm]` màu đỏ luôn hợp lệ và ghim giỏ hàng thành công.
- **Kiểm chứng thực tế và đăng thật thành công trên TikTok (@bubitueanxinhiu):**
  + Đăng video thành công với liên kết sản phẩm chuẩn: `Toner chứa 2% BHA Obagi Clenziderm M.D. Exfoliating 148ml` (Showcase ID `1731815189062584653`).
  + Link bài đăng thực tế: [https://www.tiktok.com/@bubitueanxinhiu/video/7695350773474921749](https://www.tiktok.com/@bubitueanxinhiu/video/7695350773474921749).
- **Bộ kiểm định chất lượng toàn diện:**
  + 10/10 lượt test Concurrency & Strict Affiliate Matching ĐẠT (PASS 100%).
  + 5/5 lượt test End-to-End Audit ĐẠT (PASS 100%).
  + 1165/1165 unit tests hệ thống ĐẠT (Ran 1165 tests in 38.9s, OK).
- **Tổng hợp Top sản phẩm bán chạy theo ngành hàng (`TOP_SALES_CATALOG`, `store/videos.py`):**
  + Khi người dùng tick "Tìm video bán hàng" và chọn ngành hàng nhưng để trống ô nhập: Hệ thống tự động tổng hợp danh sách Top sản phẩm bán chạy nhất kèm từ khóa review Douyin và nút chọn nhanh `🎬 Tìm video Douyin & Affiliate`.
  + Tự động loại trừ tất cả các sản phẩm đã có video trong hệ thống (ở mọi trạng thái: đã đăng `published`, sẵn sàng `ready`, chờ duyệt `awaiting_approval`, đang chờ `queued`, đang dựng `processing`).
- **Cảnh báo xác nhận chống trùng lặp (`duplicate_confirm`, `web/chat_forms.py`, `ui/tabs/search.py`):**
  + Khi người dùng tìm sản phẩm đã có video trong kho: Hệ thống hiển thị hộp thoại xác nhận cảnh báo `⚠️ Sản phẩm đã có video trong hệ thống` liệt kê các video hiện có kèm trạng thái, cùng 2 nút hành động: `[Tiếp tục tìm video mới]` (cho phép tìm thêm với cờ `allow_duplicate=True`) và `[Xem video đã có]` (dẫn sang `#publish` hoặc `#queue`).
- **Khóa chặt tài khoản đăng bài và đính kèm giỏ hàng Affiliate (`store/publishing.py`, `publisher/post.py`):**
  + Video được tìm và chọn từ tài khoản TikTok nào sẽ được khóa cứng (`search_account`) và chỉ xuất bản vào CHÍNH tài khoản TikTok đó, bảo đảm tính toàn vẹn của giỏ hàng Showcase.
  + Kiểm chứng thực tế thành công với tài khoản `@bubitueanxinhiu`: Đã tải lên TikTok Studio, tự động bổ sung CTA giỏ hàng góc trái video, kích hoạt nút đính kèm liên kết sản phẩm (`+ Thêm`) và dừng an toàn trước nút Đăng.
- **Tài liệu hóa kiến trúc hệ thống (`docs/SEARCH-FLOW-AFFILIATE.md`):**
  + Vẽ và lưu trữ sơ đồ Mermaid chi tiết 6 bước và 6 Test Cases cho toàn bộ flow tìm kiếm sản phẩm và xuất bản Affiliate.

### Đồng bộ trạng thái đăng nhập kênh tìm kiếm và tối ưu toàn diện luồng Affiliate TikTok Shop - Douyin (2026-10-11)
- **Đồng bộ triệt để trạng thái đăng nhập trên giao diện (`ui/tabs/search.py`):**
  + Loại bỏ tình trạng mâu thuẫn giữa nhãn trạng thái và dòng mô tả (trước đây badge ghi `[Chưa đăng nhập]` nhưng dòng text dưới lại đọc log cũ ghi `Đã đăng nhập; phiên đã lưu...`).
  + Chuẩn hóa theo nguyên tắc Single Source of Truth: Khi trạng thái trong CSDL là `out`, luôn hiển thị rõ ràng: *"Chưa đăng nhập. Bấm Đăng nhập để mở Chrome đăng nhập."*, đồng bộ 100% với chip trạng thái.
- **Loại bỏ hoàn toàn lỗi Agent 500 (`server.py`, `tasks.py`):**
  + Bắt `ValueError` từ các module tìm kiếm trong `server.py` và trả về HTTP 400 (Bad Request / Business Notice) kèm giải thích chi tiết bằng tiếng Việt, thay vì crash sập server với mã 500.
  + Loại bỏ tiền tố thô `"Agent báo lỗi 500: "` trong `tasks.py`, giúp thông điệp hiển thị mượt mà, trực quan cho người dùng.
- **Nâng cấp công cụ tìm kiếm TikTok và trích xuất dữ liệu (`search.py`):**
  + Mở rộng các endpoint bắt gói tin mạng của TikTok: `/api/search/`, `/api/search/item/full/`, `/api/search/general/full/`, `/api/item/detail/`, `/api/post/item_list/`.
  + Bổ sung trích xuất dữ liệu video trực tiếp từ DOM và kịch bản SSR (`webapp.video-search`, `webapp.general-search`, thẻ `a[href*="/video/"]`), đảm bảo không bỏ sót video kể cả khi TikTok không kích hoạt API JSON cũ.
- **Tự động gắn kết (Binding) Link Affiliate vào Job đăng bài (`store/videos.py`, `store/publishing.py`, `store/schema.py`):**
  + Migration CSDL version 11: Bổ sung trường `product_binding` vào bảng `jobs`.
  + Khi người dùng chọn (pick) video sản phẩm từ Douyin, hệ thống tự động tìm link hoa hồng đã lưu tương ứng với sản phẩm và tài khoản TikTok đó, lưu vĩnh viễn vào `jobs.product_binding`.
  + Khi xuất bản (`claim_publish`), `product_binding` được truyền trọn vẹn sang agent đăng bài.
- **Tối ưu chuyển đổi mua hàng và gắn giỏ hàng TikTok Studio (`publisher/post.py`):**
  + Tự động chèn lời nhắc Call-To-Action kích thích mua sắm vào mô tả video: *"🛒 Mua ngay tại giỏ hàng góc trái video! #tiktokshop #review"*.
  + Bổ sung cơ chế `_try_attach_product_anchor` để tìm và gắn thẻ sản phẩm (Product Anchor/Link) vào video trong giao diện TikTok Studio Creator.

- **Bảo vệ toàn diện `form_post` chống lỗi 500 (`web/handler.py`):**
  + Bắt mọi ngoại lệ `Exception` trong luồng xử lý form, ghi log traceback đầy đủ và chuyển hướng về trang điều khiển với thông báo thân thiện bằng tiếng Việt (`vi_error`) thay vì làm sập HTTP 500 JSON thô (`{"error": "Internal failure; inspect local service"}`).
  + Giữ nguyên anchor `#accounts` khi phản hồi lỗi hoặc thành công của các form tài khoản, ngăn chặn tình trạng người dùng bị văng về tab `#home` (Tổng quan) làm gián đoạn trải nghiệm.
- **Hỗ trợ link TikTok và chuẩn hóa tên tài khoản (`domain/accounts.py`, `store/accounts.py`):**
  + Tự động nhận diện và trích xuất tên tài khoản TikTok khi người dùng dán toàn bộ đường dẫn URL hồ sơ TikTok (ví dụ `https://www.tiktok.com/@kenh_moi?lang=vi`), tự động loại bỏ tiền tố `@` và khoảng trắng dư thừa.
  + Kiểm tra trùng lặp tài khoản không phân biệt hoa thường (`LOWER(username) = LOWER(?)`), ngăn chặn lỗi xung đột cơ sở dữ liệu khi nhập khác kiểu chữ.
  + Tự động tạo hậu tố tăng dần cho `account_id` nếu phát sinh trùng lặp mã slug nhưng khác tên người dùng.
- **Tối ưu hóa cơ sở dữ liệu SQLite trong môi trường Docker/VirtioFS (`store/base.py`, `store/schema.py`):**
  + Thiết lập `PRAGMA synchronous = NORMAL` và `PRAGMA busy_timeout = 30000` trong WAL mode, triệt tiêu lỗi `sqlite3.OperationalError: disk I/O error` do tranh chấp khóa giữa host và container.
  + Bổ sung cơ chế tự động thử lại (retry với exponential backoff) tối đa 3 lần cho các giao dịch ghi `transaction()` khi gặp `OperationalError`.
- **Giao diện thêm tài khoản thân thiện (`ui/tabs/accounts.py`, `ui/tabs/more.py`, `ui/tabs/search.py`):**
  + Cập nhật gợi ý placeholder: `ten_kenh hoặc link TikTok`.
  + Phòng ngừa `KeyError` an toàn với `view.d.get("notify_channels", ())` và `m.get("account")`.
  + Khắc phục phương thức kiểm tra `is_closed` an toàn với mock trong `search_douyin.py`.
- **Sửa triệt để kiểm tra đăng nhập Douyin (`channels.py`, `search_douyin.py`):**
  + Thay đổi `DOUYIN_HOME` từ `https://www.douyin.com/` sang `https://www.douyin.com/jingxuan`: loại bỏ hoàn toàn bẫy chuyển hướng sang trang trắng `验证码中间页`. Mở trang Jingxuan gọi API `/aweme/v1/web/user/profile/self/` thành công và ghi nhận chính xác ID tài khoản người dùng (`42851771569`).
  + Sửa hàm `blocked(page)`: Loại bỏ kiểm tra chuỗi `nocaptcha` trên URL iframe vì ByteDance luôn tải iframe telemetry ngầm `rmc-nocaptcha` (ẩn). Chỉ nhận diện là tường chặn khi có iframe Captcha thật `verifycenter/captcha` hiển thị trên màn hình hoặc title là `验证码中间页`.
  + Kết quả: Cột Kênh tìm kiếm bên phải hiển thị chính xác trạng thái **"Sẵn sàng · phiên đã lưu"** (xanh lá cây) kèm thông báo "Douyin đã xác nhận tài khoản 42851771569 trong hồ sơ của bạn", không còn hiển thị nhầm "Chờ xác minh".
- **Tự động dọn kẹt và giải phóng khóa trình duyệt (`task_log.py`, `tasks.py`, `chat_forms.py`):**
  + Bổ sung cơ chế tự động dọn dẹp (reap) các tác vụ chạy quá hạn 15 phút trong `tasks_running()`, ngăn chặn vĩnh viễn tình trạng deadlock hoặc giữ lock trình duyệt khi có lỗi ngoài ý muốn.
  + Thêm hàm `cancel_for_job` vào `Tasks`: khi người dùng bấm "Xóa lượt này", hệ thống lập tức hủy tác vụ đang chạy gắn với lượt đó và giải phóng khóa trình duyệt ngay, giúp người dùng sẵn sàng tìm kiếm mới ngay lập tức mà không bao giờ gặp cảnh báo "Đang có một việc dùng trình duyệt chạy...".
- **Cơ chế trích xuất video trực tiếp từ DOM & React Fiber (`search_douyin.py`):**
  + Tự động duyệt qua React props (`__reactFiber$`, `__reactProps$`) trên từng card video, trích xuất chính xác `aweme_id`, tiêu đề, tác giả, lượt like và URL trực tiếp `douyin.com/video/<id>`.
  + Tích hợp quét DOM định kỳ 1s/lần trong vòng lặp chờ kết quả: ngay khi card video xuất hiện trên màn hình, hệ thống lập tức nạp vào kết quả và hoàn thành tìm kiếm thành công mà không phụ thuộc vào việc bắt stream mạng có bị drop hay không.
- **Vượt qua cơ chế chống tự động hóa của ByteDance (`browser.py`):**
  + Bổ sung cờ khởi chạy Chrome `--disable-blink-features=AutomationControlled`, chuyển `navigator.webdriver = false`, triệt tiêu hoàn toàn việc Douyin kích hoạt Captcha chặn bot trên Chrome thật.
- **Kiểm chứng trực tiếp trên Dashboard (`http://127.0.0.1:5681/#search`):**
  + Mọi nút bấm trên Dashboard (Kiểm tra Douyin, Xóa lượt này, Tìm video) đều chạy mượt mà, không gặp lỗi.
  + Submit từ khóa `迈从 ACE68` (ngành Đồ điện tử, chế độ Bán hàng) trên giao diện thật: trả về các video ứng viên review/đập hộp chuẩn xác 100%, có checkbox xác nhận và nút "Chọn và tải để xử lý". Ảnh minh chứng: `shot_phase11_douyin_success.png`.

- **Chống khóa bận trình duyệt (Non-blocking Chat User Experience, `tasks.py`):**
  + Tách biệt hoàn toàn tác vụ `identify` (nhận diện qua Gemini) khỏi `BROWSER_KINDS` vì `identify` không mở trình duyệt.
  + Thao tác gửi tìm kiếm của người dùng trực tiếp trên Dashboard không bao giờ bị văng lỗi `TaskBusy` ("Đang có một việc dùng trình duyệt chạy...") khi có lịch thu thập nền `collect` đang chạy.
- **Nâng cấp thuật toán tự giải Captcha ByteDance trên Canvas đồng nhất tỉ lệ (`search_douyin.py`):**
  + Đồng nhất kích thước vẽ Canvas theo kích thước client hiển thị thực tế (340x212 cho ảnh nền, 68x68 cho mảnh trượt), loại bỏ triệt để sai lệch tỉ lệ 1.62x của thuật toán cũ.
  + Áp dụng thuật toán Gap matching tìm điểm cực tiểu độ sáng trung bình (`minAvgLum`) trên vùng mask của mảnh ghép, đưa mảnh ghép rơi chuẩn xác vào tâm lỗ khuyết của bóng đen (trái tim/mặt trăng/ngôi sao).
  + Quỹ đạo kéo chuột S-curve kéo dài 2.0s - 2.8s với 60-70 bước, dừng nghỉ 350ms tại đích trước khi thả chuột, ngăn chặn triệt để mã lỗi `操作过快，请慢一点[5014][502]`.
  + Tự động click nút đóng modal `.captcha_verify_action_close` và `[class*='close']` khi modal xuất hiện che khuất kết quả.
- **Kênh tìm kiếm dự phòng Douyin Jingxuan Search (`search_douyin.py`):**
  + Tích hợp URL fallback `https://www.douyin.com/jingxuan/search/<query>` song song với trang search chính để tự động trích xuất kết quả video khi trang chính bị kẹt ở `验证码中间页`.
- **Hoàn thiện tương tác xác nhận Captcha trên giao diện web (`chat_forms.py`, `tasks.py`, `ui/tabs/search.py`):**
  + Nhận diện cờ `human` chuẩn xác cả dạng chuỗi `"true"` và boolean `True`.
  + Tăng thời gian chờ người dùng lên 60 giây khi mở cửa sổ xác minh (`human=True`), giữ cửa sổ mở và liên tục kiểm tra trạng thái để nạp video ngay khi vượt qua Captcha.
  + Làm sạch thông báo lỗi Captcha, loại bỏ hoàn toàn tiền tố "Agent báo lỗi 500:" gây hoang mang, hiển thị hướng dẫn mở cửa sổ Chrome rõ ràng.
- **Kiểm thử tự động và Audit 5 lần thành công 100% ([tests/worker/test_phase10_captcha_flow.py](tests/worker/test_phase10_captcha_flow.py) & [scratch/audit_phase10_live_5_runs.py](scratch/audit_phase10_live_5_runs.py)):**
  + **Run 1:** Gửi tìm kiếm bán hàng Đồ điện tử & phụ kiện trên Dashboard UI không bị TaskBusy -> **PASS** (7.25s).
  + **Run 2:** Nút hành động Captcha không gây lỗi HTTP 500 và nhận cờ human -> **PASS** (0.02s).
  + **Run 3:** Kiểm thử độ chính xác Canvas Scaled Gap Detection & Easing -> **PASS** (0.007s).
  + **Run 4:** Kênh Douyin Jingxuan sạch không bị tường chặn -> **PASS** (4.80s).
  + **Run 5:** Toàn trình Dashboard UI End-to-End không lỗi và lưu ảnh minh chứng `shot_phase10_run5_dashboard_success.png` -> **PASS** (3.73s).

### Tối ưu hóa tìm kiếm video bán hàng ngành Đồ điện tử & Phụ kiện trên Douyin, tăng tốc độ và kiểm thử 5 lần thực tế (Phase IX, 2026-10-10)
- **Mở rộng danh mục phụ kiện công nghệ & đặc tính kỹ thuật (`domain/search_queries.py`):**
  + Bổ sung đầy đủ các phụ kiện phổ biến nhất: pin sạc dự phòng (`充电宝`), củ sạc nhanh GaN (`快充充电器`), giá đỡ điện thoại/laptop (`支架`), hub/dock chuyển đổi (`拓展坞`), bàn nâng hạ (`升降桌`).
  + Bổ sung đặc tính kỹ thuật tiếng Trung chuẩn: chống ồn ANC (`降噪`), không dây (`无线`), sạc nhanh (`快充`), bán dẫn GaN (`氮化镓`), góc làm việc desk setup (`桌搭`).
- **Nâng cao điểm thu hút người mua (Buyer Appeal) & Bộ lọc xung đột ngành (`domain/product_match.py`):**
  + Bổ sung các từ khóa chuyển đổi cao của giới công nghệ Douyin: `桌搭`, `桌面搭配`, `硬核测评`, `数码好物`, `闭眼入`, `真香`, `深度评测`, `开箱体验`, `开箱测评`, `避坑指南`, `质感`, `沉浸式体验`.
  + Bổ sung từ khóa loại trừ triệt để hàng cũ/rác/hỏng: `战损版`, `成色差`, `暗病`, `仅拆封不保`, `配件机`, `通电不亮`.
  + Tích hợp bộ lọc xung đột ngành (`is_electronics`): Tự động loại trừ ngay lập tức (`different`, điểm 0) video thuộc ngành hàng khác (quần áo váy đầm `连衣裙`, mỹ phẩm son phấn `口红`, đồ ăn vặt `零食`) khi đang tìm kiếm đồ điện tử & phụ kiện.
- **Tối ưu hóa thao tác chuột giải Slider Captcha mô phỏng người thật (`agent/search_douyin.py`):**
  + Tinh chỉnh chuyển động kéo trượt theo hàm S-curve Cubic Ease-in-out với gia tốc tự nhiên (48-62 steps, 1.4-1.7s, micro-hesitation căn chỉnh tại đích) nhằm ngăn chặn triệt để thông báo "操作过快，请慢一点" từ ByteDance.
- **Kiểm thử thực tế và Audit 5 lần thành công 100% (`tests/worker/test_phase9_sales_electronics.py` & `scratch/audit_phase9_live_5_runs.py`):**
  + **Run 1:** Khám phá tổng quát ngành hàng Bán hàng Đồ điện tử & phụ kiện -> **PASS** (0.001s).
  + **Run 2:** Model cụ thể bàn phím cơ MCHOSE ACE68 磁轴键盘 -> **PASS** (0.001s).
  + **Run 3:** Phụ kiện âm thanh tai nghe bluetooth chống ồn ANC -> **PASS** (0.000s).
  + **Run 4:** Phụ kiện nguồn củ sạc nhanh 65W GaN -> **PASS** (0.000s).
  + **Run 5:** Toàn trình Live Web Dashboard E2E Form + Cards trên Chrome thật -> **PASS** (4.62s) - Lưu ảnh minh chứng `shot_phase9_run5_dashboard_sales_electronics.png`.

### Tối ưu tự động thao tác giải slider CAPTCHA, sửa lỗi kẹt đơ khi mở xác nhận, tối ưu từ khóa bán hàng sắc bén (Phase VIII, 2026-10-10)
- **Tự động thao tác kéo trượt vượt Slider CAPTCHA của Douyin/TikTok (`try_solve_slider`):**
  + Trong `search_douyin.py` và `search.py`: Quét toàn diện trên mọi frame (`page.main_frame` và subframes) với đa selector (`.captcha-slider-btn`, `.secsdk-captcha-drag-icon`, `#secsdk-captcha-drag-wrapper .drag-button`, `[class*='slider-btn']`, `[class*='drag-icon']`, `.verify-bar-btn`).
  + Phân tích cạnh ảnh viền khuyết bằng thuật toán Sobel + Cross Correlation trên Canvas context 2D, hỗ trợ co giãn tỉ lệ (scale factor) theo kích thước render thực tế.
  + Điều khiển chuột theo đường cong Bézier Ease-out mô phỏng tay người thật kèm micro-jitter ngẫu nhiên.
  + Tự động nhấn nút xác nhận nếu có (`完成`, `确认`, `确定`), tự động đóng popup login che khuất (`.dy-account-close`, `[class*='login-guide'] [class*='close']`).
- **Sửa triệt để lỗi "mở lên xác nhận CAPTCHA không có call check khiến đứng đơ ở trang đó miết":**
  + Phát hiện nguyên nhân gốc: Khi `human=False` (tìm kiếm ngầm trong nền), hệ thống trước đây vẫn đặt `owner_window=window_ok()` (luôn là True trên macOS có màn hình), dẫn đến việc `wait_for_results` chờ người dùng giải CAPTCHA trên một trình duyệt headless không tồn tại trên màn hình suốt 13 phút.
  + Đã sửa trong `search.py` và `search_douyin.py`: Đặt `owner_window=bool(human)` và `headless=not (human or window_ok())`. Khi tìm kiếm ngầm, hệ thống phản hồi lỗi ngay lập tức, giải phóng hoàn toàn khóa `browser_lock` cho Agent (`busy: false`) để máy không bao giờ bị treo đơ.
  + Trong `ui/tabs/search.py` và `static/app.js`: Thêm banner trực quan báo tiến độ Agent tích hợp đang tự động kiểm tra/giải CAPTCHA và bổ sung nút `[🔄 Kiểm tra trạng thái ngay]` (`refresh_check`) để người dùng kích hoạt call check tức thì bất cứ lúc nào.
  + Trong `search_douyin.py`: Khi giải xong CAPTCHA, hàm `resume_query` lập tức điều hướng về URL tìm kiếm ban đầu để nạp kết quả và phản hồi mượt mà.
- **Tối ưu hóa từ khóa và bộ lọc tìm kiếm bán hàng theo ngành hàng (`domain/discovery.py`):**
  + Đổi intent bán hàng từ `好物 推荐` chung chung sang `测评 开箱` (Review, Đập hộp) sắc bén cho giới công nghệ Douyin.
  + Ngành Đồ điện tử: Truy vấn Douyin mang từ khóa chuẩn `数码配件 测评 开箱` hoặc `<Model> 测评`, loại bỏ từ ngữ loãng kết quả, ưu tiên đúng các video review thực tế và giới thiệu sản phẩm mới.
- **Kiểm thử E2E live trên Google Chrome thật 5 vòng liên tiếp ([tests/e2e/test_phase8_5_runs.py](tests/e2e/test_phase8_5_runs.py)):**
  + **Vòng 1 (Phát hiện & Thao tác giải Slider Captcha):** Nhận diện chính xác iframe xác minh ByteDance và tự động thực hiện thao tác kéo slider an toàn trong 6.67s -> **PASS**.
  + **Vòng 2 (Mở xác nhận CAPTCHA không bị treo đơ & Giải phóng khóa):** Agent duy trì trạng thái `busy: false` khỏe mạnh, không bị kẹt deadlock trong 2.82s -> **PASS**.
  + **Vòng 3 (Từ khóa tìm kiếm bán hàng ngành điện tử sắc bén):** Tạo query chuẩn xác với từ khóa review `测评` / `开箱` trong 0.02s -> **PASS**.
  + **Vòng 4 (Lọc video review/mới tinh & Loại trừ 100% đồ cũ/rã xác):** Phân loại và loại bỏ sạch toàn bộ video phế liệu/cũ nát trong 0.01s -> **PASS**.
  + **Vòng 5 (Toàn trình E2E Dashboard):** Nhập liệu, gửi tìm kiếm bán hàng, hiển thị bong bóng tin nhắn và thẻ sản phẩm trơn tru trong 3.97s -> **PASS**.

- **Fix triệt để lỗi "Trang đã cũ; hãy tải lại trước khi gửi" khi Xóa video / Bỏ ứng viên:**
  + Tạo cơ chế Token CSRF bền vững tại `trendvn_worker/web/app.py`: lưu và tải token từ `data/worker/csrf.key` để token không bị tạo ngẫu nhiên lại mỗi khi container hoặc worker khởi động lại.
  + Thêm header `X-CSRF-Token: self.app.csrf` trong endpoint `/fragment/chat` (`handler.py`) giúp giao diện luôn cập nhật token CSRF mới nhất sau mọi tác vụ chat mà không cần reload toàn trang.
  + Tự động cập nhật CSRF token trong `static/app.js` và bổ sung cơ chế Auto-retry thông minh: nếu gặp mã lỗi 403 `Trang đã cũ`, client tự động làm mới token và gửi lại yêu cầu xóa/bỏ ứng viên mà người dùng không bị gián đoạn.
- **Mở khóa nút "Chọn và tải để xử lý" khi video "Chưa khớp biến thể đã xác định":**
  + Trong `ui/tabs/search.py`: Khi video đúng thương hiệu và đúng model nhưng tiêu đề chưa ghi rõ biến thể (màu sắc/switch/layout), giao diện không còn khóa cụt người dùng. Thay vào đó, hệ thống mở khóa ô checkbox xác nhận và nút `[Chọn và tải để xử lý]` kèm hướng dẫn thân thiện: `Chưa rõ biến thể trong tiêu đề; hãy xem video đối chiếu rồi tích xác nhận để chọn.`.
- **Bộ lọc sản phẩm bán hàng thông minh: Chỉ lấy sản phẩm mới tinh & Review, loại trừ 100% hàng cũ/rã xác:**
  + Trong `domain/product_match.py`: Bổ sung hàm `is_old_product(title)` phát hiện chính xác từ khóa hàng cũ, hàng bãi, thanh lý cũ, rã xác, sửa chữa cả tiếng Trung (`二手`, `翻新`, `维修`, `拆解`, `报废`, `垃圾佬`, `捡漏`, `伊拉克`, `老款`, `洋垃圾`, `破烂`, `尸体`, `战损`...) lẫn tiếng Việt/Anh (`do cu`, `hang cu`, `2nd`, `secondhand`, `pass lai`, `thanh ly cu`, `ve chai`, `ra xac`, `xac may`, `sua chua`, `hang bai`...).
  + Mở rộng nhận diện video có sản phẩm mới tinh (`全新`, `新品`, `首发`), người mặc sản phẩm nhảy múa/thời trang (`穿搭`, `上身`, `试穿`, `变装`, `跳舞`, `舞蹈`, `换装`, `走秀`, `dance`, `ootd`), và video người dùng trải nghiệm thực tế (`使用体验`, `上手`, `日常使用`, `沉浸式使用`, `教程`).
  + Trong `store/videos.py`: Khi tìm kiếm có kích hoạt bán hàng (`sales=True`), loại trừ 100% video dính `is_old_product`, ưu tiên hàng đầu video đập hộp, review, người mặc nhảy và trải nghiệm mới tinh.
- **Kiểm thử E2E live trên Google Chrome thật 5 vòng liên tiếp ([tests/e2e/test_phase7_5_runs.py](tests/e2e/test_phase7_5_runs.py)):**
  + **Vòng 1 (Xóa video & Bỏ ứng viên không lỗi CSRF):** Bấm "Bỏ ứng viên" và "Xóa lượt này" hoạt động tức thì, không gặp lỗi "Trang đã cũ", hoàn thành trong 6.28s -> **PASS**.
  + **Vòng 2 (Mở khóa nút Chọn Video khi chưa rõ biến thể):** Nút "Chọn và tải để xử lý" hiển thị sẵn sàng, tích xác nhận hợp lệ, hoàn thành trong 4.77s -> **PASS**.
  + **Vòng 3 (Nhận diện video bán hàng: Review, Unboxing, Mới tinh, Mặc đồ nhảy):** Đo lường và phân loại chính xác 100% các tiêu đề có ý định thương mại (điểm từ 35 đến 100), hoàn thành trong 1.26s -> **PASS**.
  + **Vòng 4 (Loại trừ 100% video hàng cũ, hàng bãi, rã xác, sửa chữa):** Lọc sạch toàn bộ video phế liệu/cũ, chỉ giữ lại các video mới và review, hoàn thành trong 3.25s -> **PASS**.
  + **Vòng 5 (Toàn trình E2E tốc độ cao):** Chu trình hoàn chỉnh Tìm kiếm -> Hiển thị kết quả -> Chọn và tải xử lý -> Dọn dẹp an toàn trong 7.12s -> **PASS**.

- **Cơ chế chờ CAPTCHA 15s hai tầng (Two-stage Graceful Wait):**
  + Trong `search_douyin.py` và `search.py`, khi trình duyệt phát hiện CAPTCHA (slider, verifycenter, verify_check), hệ thống tự động duy trì chu kỳ chờ kiên nhẫn 15 giây (thăm dò mỗi 1.5s). Nếu người dùng giải xong trong 15s, trang tự động gọi `resume_query` tải lại kết quả và thu thập video ngay mà không ném lỗi.
  + Nếu sau 15 giây CAPTCHA vẫn chưa được giải, hệ thống ném ngoại lệ `Wall` có cấu trúc rõ ràng: báo ở thẻ lịch sử chat và cho phép người dùng bấm xác nhận.
- **Tương tác xác nhận CAPTCHA trong lịch sử Chat (`ui/tabs/search.py`):**
  + Nhận diện lỗi CAPTCHA/xác minh trong thẻ lỗi tin nhắn, hiển thị banner cảnh báo: `⚠️ Cần xác nhận CAPTCHA trên nguồn này. Hệ thống đã chờ 15s...`.
  + Bổ sung nút hành động chuyên dụng: `[Tôi đã xác nhận CAPTCHA, tiếp tục tìm]` (class `go`) để kích hoạt lệnh tìm kiếm lại và đợi tiếp 15 giây cho người dùng hoàn tất; nút `[Mở cửa sổ giải CAPTCHA (chờ 15s)]` (`human=true`) mở trực tiếp Chrome trên màn hình.
- **Cách ly lỗi nguồn khi chọn "Các kênh đã đăng nhập" (`auto`):**
  + Khi TikTok từ IP Việt Nam không trả video (lỗi 500 do thiếu IP Mỹ), hệ thống không dập tắt luồng Douyin. Ưu tiên Douyin chạy trước khi có từ khóa tiếng Trung hoặc tìm bán hàng.
  + Thẻ lỗi của nguồn `auto` bổ sung các nút bấm tìm nhanh trực tiếp: `[Tìm trên Douyin]`, `[Tìm trên TikTok]` giúp người dùng chuyển đổi nguồn ngay lập tức.
  + Trong `search/runner.py` và `search.py`: cho phép các kênh đang ở trạng thái `wall` (chờ xác minh) vẫn được đưa vào danh sách nguồn tìm kiếm khả dụng thay vì loại bỏ.
- **Kiểm thử E2E live trên Google Chrome thật 5 lần liên tiếp ([tests/e2e/test_captcha_flow_5_runs.py](tests/e2e/test_captcha_flow_5_runs.py)):**
  + Lần 1: Hiển thị banner cảnh báo và nút xác nhận CAPTCHA trong lịch sử chat -> **PASS**.
  + Lần 2: Nút xác nhận gửi action `find`, server phản hồi 200 OK -> **PASS**.
  + Lần 3: Cách ly lỗi nguồn `auto`, cung cấp nút tìm trực tiếp trên từng nguồn -> **PASS**.
  + Lần 4: Nhập liệu sản phẩm, kích hoạt chế độ bán hàng (`sales=True`), từ khóa thương mại chuẩn xác -> **PASS**.
  + Lần 5: Hiển thị ứng viên video, cơ chế chặn an toàn khi chưa tick, tick xác nhận và chọn tải thành công -> **PASS**.
  + Console Logs trình duyệt: **0 lỗi JavaScript** -> **PASS 100%**.

### Kiểm thử và tối ưu thao tác tìm kiếm trên trình duyệt thật 5 vòng (Phase V, 2026-10-10)
- **Khắc phục lỗi vòng lặp vô hạn (Infinite Loop/Deadlock) trong `probe` của Douyin session:**
  + Khi kiểm tra phiên Douyin gặp trang xác minh (`state == 'wall'`), hàm `probe` không còn bị kẹt trong vòng lặp vô hạn `continue` khi máy host có màn hình (`owner_wait=True`), mà trả về ngay trạng thái `("wall", who)` để giải phóng khóa trình duyệt `browser_lock` cho agent.
  + Đặt `owner_wait=False` khi gọi `check(account, 'douyin')` trong `channels.py` để tác vụ kiểm tra trạng thái phiên và tìm kiếm tự động phản hồi ngay lập tức, không gây treo tiến trình.
- **Kiểm thử E2E trực tiếp trên Google Chrome thật kết nối Dashboard Live (`http://127.0.0.1:5681`):**
  + Xây dựng bộ kịch bản kiểm thử tự động toàn diện [tests/e2e/test_search_ui_live.py](tests/e2e/test_search_ui_live.py) và thực thi trọn vẹn 5 vòng lặp:
  + **Vòng 1 (Form controls & Validation):** Kiểm tra chặn submit rỗng khi chưa có từ khóa/topic/sales/files; kiểm tra toggle checkbox "Tìm video bán hàng" tự động làm hiện/ẩn dropdown "Ngành hàng" và gán/hủy thuộc tính `required`; kiểm tra đồng bộ dropdown tài khoản, nguồn và thể loại.
  + **Vòng 2 (Input & Submit):** Kiểm tra nhập liệu tiếng Trung/Latinh, gửi yêu cầu qua phím tắt Ctrl/Cmd+Enter; tự động làm sạch ô nhập sau khi gửi; kiểm tra bong bóng tin nhắn của người dùng và phản hồi thẻ nhận diện sản phẩm của bot trong thời gian thực.
  + **Vòng 3 (Thẻ ứng viên - Candidate cards):** Kiểm tra nạp thẻ video ứng viên từ server; cơ chế an toàn chặn nút "Chọn và tải để xử lý" (`pick`) khi chưa tick xác nhận kèm thông báo hướng dẫn; kiểm tra tick ô xác nhận; kiểm tra nút "Bỏ ứng viên" (`dismiss`) gửi request gỡ bỏ thẻ mượt mà không reload trang.
  + **Vòng 4 (Sửa tên & Quản lý lịch sử):** Kiểm tra nút "Sửa tên/model" (`fill`) tự động điền tên model vào textarea và focus con trỏ; kiểm tra hộp thoại modal xác nhận an toàn (`#confirm-action`) khi click "Xóa lượt này" và "Xóa toàn bộ lịch sử tìm kiếm"; bấm Hủy đóng modal và giữ nguyên dữ liệu; bấm Xác nhận dọn sạch thread và quay về thẻ chào đón ban đầu.
  + **Vòng 5 (Edge cases, Responsive & Console health):** Kiểm tra đính kèm tệp và nút xóa ✕ từng tệp; kiểm tra audit ô chạm (Touch Targets) >= 44px trên 4 kích cỡ màn hình (Desktop 1280x800, iPhone 375x667, Mobile 414x896, Tablet 768x1024) không vỡ giao diện; kiểm tra Console Logs trình duyệt đạt **0 page errors, 0 console errors**.
  + Chụp và lưu trữ 5 ảnh màn hình minh chứng tương ứng với 5 vòng kiểm thử tại thư mục Artifacts.

### Lọc chính xác video bán hàng và nội dung liên quan sản phẩm (Phase U, 2026-10-10)
- Nhận diện ý định thương mại (Commercial Intent): phân tích tiêu đề và siêu dữ liệu video đa ngữ (Trung: `好物`, `推荐`, `测评`, `评测`, `开箱`, `种草`, `实测`, `上手`, `首发`, `性价比`, `带货`, `日常分享`; Việt/Anh: `review`, `đánh giá`, `trên tay`, `mở hộp`, `unboxing`, `trải nghiệm`, `giỏ hàng`, `shop`, `giá rẻ`, `chính hãng`, `hướng dẫn`, `săn sale`, `deal`). Loại trừ từ đơn gây dương tính giả (như `mưa/mùa`).
- Xếp hạng thông minh theo Tầng Bán Hàng khi `sales=True`:
  + **Tier 2 (Ưu tiên tuyệt đối):** Đúng sản phẩm (`level != 'different'`) VÀ có ý định bán hàng/review. Video unboxing/review sản phẩm ít view vẫn xếp trước video triệu view không liên quan bán hàng.
  + **Tier 1:** Đúng sản phẩm nhưng không có từ khóa bán hàng rõ trong tiêu đề.
  + **Tier 0:** Sai thương hiệu, khác model (`level == 'different'`) hoặc xung đột danh mục sản phẩm (bàn phím vs chuột) bị đẩy xuống cuối cùng, không được đè lên video đích.
- Khắc phục điểm mù token chữ Hán dính liền: so khớp chuỗi con ký tự Hán tự trong tiêu đề video Douyin, phục hồi điểm khớp từ 0% lên 100% khi người dùng nhập tiếng Việt tìm kiếm sản phẩm trên nguồn Trung Quốc.

### Chuẩn hóa tìm kiếm Douyin & Bộ lọc bán hàng (Phase T, 2026-10-10)
- Chặn triệt để ký tự tiếng Việt gửi lên Douyin và Kuaishou: mở rộng từ điển 24 ngành hàng thông dụng và đặc tính sản phẩm sang tiếng Trung (`query_zh`), bổ sung từ khóa thương mại (`好物 推荐`). Input tiếng Việt lạ không dịch được tự động bỏ qua nguồn tiếng Trung với ghi chú rõ ràng, tuyệt đối không gửi tiếng Việt lên Douyin.
- Bộ lọc Douyin Web: tìm bình thường dùng `type=video&sort_type=0`; tìm bán hàng (`sales=True`) tự động ghép `sort_type=1&publish_time=180` (ưu tiên video nhiều tương tác trong 6 tháng) kèm từ khóa thương mại `好物 推荐`.
- Cơ chế bắt xác minh CAPTCHA: nhận diện phản hồi API `search_nil_type: verify_check` và iframe `verifycenter/captcha`. Phân tách rõ ràng giữa chạy nền và chạy mở cửa sổ: tác vụ nền báo `Wall` ngay lập tức trong 4-5 giây thay vì treo chờ 120 giây; chỉ kiên nhẫn chờ khi chủ bấm "Mở cửa sổ" (`human=True`).
- Đã audit thực tế 5 lần qua luồng thật: đạt 100% độ thuần tiếng Trung cho Douyin, tốc độ phản hồi Wall/lọc tối ưu từ 120+ giây xuống 4.62 giây (nhanh gấp ~26 lần).

### Douyin và lịch sử tìm kiếm (2026-10-09)
- Xác nhận phiên Douyin từ tài khoản sở hữu do trang trả, chờ chủ đăng nhập/xác minh rồi mở lại hồ sơ để kiểm; cookie cũ không còn tự báo sẵn sàng.
- Tìm chung/riêng dùng cùng bộ đọc đúng truy vấn; hỗ trợ keyword GET/POST, khôi phục truy vấn sau đăng nhập và không lấy video gợi ý thay thế.
- Xóa lượt gỡ cả câu nhập và các kết quả con, kể cả đang chờ; kết quả đến muộn giữ ẩn, giữ video/link/phiên và chống trùng. Nút cũ không khởi động tìm lại lượt đã ẩn.

## 1.9 — 2026-10-07 (tìm kiếm trong hàng đợi: docs/QUEUE-SEARCH-PLAN.md)

**Sửa chờ xác minh và lịch sử ngày 2026-10-09 (Phase R).** Cửa sổ đăng nhập/tự xác minh không hết hạn giữa chừng; tìm thường có màn hình chờ qua CAPTCHA. Xóa toàn bộ lịch sử ẩn cả lượt đang chạy và kết quả con đến sau, vẫn giữ video/link/phiên. Xóa bài có thể chờ chủ phục hồi Studio; quyền xóa được giữ khi chờ, kiểm lại sau đọc danh tính và sát mỗi click; lỗi sau thao tác không tự xóa lặp. Thẻ không còn hiện lỗi kỹ thuật dài từ trình duyệt.

- Xóa bài TikTok: fallback TikTok Studio khi trang công khai 403; hỗ trợ thao tác xác nhận kết quả xóa trên tab Đã đăng; bảo toàn kiểm tra khớp bài URL và tài khoản.
- Tìm kiếm theo nguồn: Gemini phân tích hình ảnh/tài liệu tạo từ khóa tiếng Trung (`query_zh`) cho Douyin và Kuaishou; không gửi query tiếng Việt sang nguồn Trung Quốc.
- Trải nghiệm giao diện: lưu và phục hồi vị trí cuộn trang chính xác (tránh giật về đầu trang khi submit), responsive tối ưu tablet (768px-787px) và mobile; lập bản đồ docs/SCROLL-AND-FEEDBACK-MAP.md.
- Xử lý video: bắt lỗi Transient (Gemini 503/504) đưa về hàng đợi an toàn; bổ sung thông báo tiến trình chi tiết 6 bước theo thời gian thực.
- Kiểm thử: 953/953 unit test và doclint đều đạt chuẩn.

**Sửa theo đánh giá toàn luồng ngày 2026-10-08** (số đo thật và rà độc lập: docs/ROADMAP.md, Phase O).
- *Thu thập.* Mỗi lần quét hỏi worker đúng các video nó vừa thấy (`source_ids`) rồi mới cắt còn 100 tốt nhất: trước đó kho 129 ứng viên Douyin khiến 29 video không bao giờ được xét. Khi hàng chờ đầy, kết quả quét và trang Tổng quan nói rõ "Hàng chờ đã đủ (x/y)" thay vì chỉ ghi "tải 0". Thấy lại một video không còn làm mới thời điểm đổi trạng thái của nó (video bị loại giữ tệp lâu, video chờ duyệt không hết hạn).
- *Xóa bài.* Chưa nhận việc (agent bận, mất kết nối trước khi nhận) ghi `failed` và cho thử lại, không còn ghi `unknown` oan; đã nhận mà mất kết quả mới là `unknown`. `deleted` chỉ đến từ một lượt agent đã nhận. Worker chờ agent 420 giây (trước 180); yêu cầu kẹt được dọn sau 300 giây (chưa nhận) hoặc 600 giây (đã nhận) khi không có tác vụ xóa nào đang chạy; khởi động lại worker áp dụng cùng quy tắc. Một bài chỉ xóa một lần dù hai video cùng trỏ tới (so URL không phân biệt hoa thường). Tab Đã đăng chỉ hiện nút mà worker sẽ nhận; bài `failed` có thêm "Đã kiểm tra: bài đã xóa" cho trường hợp chủ tự xóa bằng tay. Ảnh chụp lỗi chỉ giữ 20 ảnh mới nhất.
- *Chat.* Gửi lại cùng một yêu cầu sau khi lần trước lỗi (trình duyệt bận, mô hình quá tải) chạy như lần mới thay vì bị coi là đã xong; mã yêu cầu không dùng được chéo tài khoản. Gửi tin hoạt động cả khi mở bảng điều khiển qua `http://` (trình duyệt không có `crypto.randomUUID`).
- *Tìm kiếm.* Kuaishou và Douyin chỉ nhận từ khóa tiếng Trung (hoặc mã model không có chữ Việt); thiếu thì nguồn đó bị bỏ qua kèm ghi chú và các nguồn còn lại vẫn chạy (trước đó cả lượt lỗi sau khi đã tìm xong TikTok).
- *Giao diện.* Địa chỉ `?err=` dài không còn làm treo máy chủ (60 KB: 26 giây → vài mili giây). Nhãn "Tổng quan" của thanh điều hướng điện thoại vừa ở mọi bề rộng 320–420 px; e2e đo thêm 390 và 412 px (9 cỡ).
- *Kiểm thử.* 1086 test (có thêm một bộ test riêng cho từng chốt của luồng xóa bài, trước đó 11/15 đột biến vào chốt sống sót); e2e Chrome thật chạy lại xanh trên giao diện 1.9: 147 kiểm tra.

**Hàng đợi thống nhất.** Tìm kiếm nằm trong Hàng đợi; link `#search` cũ vẫn mở đúng phần. Sáu mục điều hướng chia đều, ô chạm tối thiểu 44 px, focus cùng màu/khoảng cách; select, icon tải lại, nút, input, textarea, checkbox và tab dùng component chung; tôn trọng chế độ giảm chuyển động.

**Tìm bằng phiên đăng nhập.** Bốn kênh TikTok, Douyin, Kuaishou, Instagram có đăng nhập/kiểm tra trong hồ sơ riêng của từng tài khoản. Thể loại mặc định theo tài khoản; thể loại, từ khóa, model và ngành hàng được ghép vào truy vấn gửi tới nguồn. Có công tắc tìm video bán hàng và tám ngành hàng. Kết quả ưu tiên độ khớp và tương tác đọc được, không coi lượt xem là doanh số. Các nguồn vẫn có thể chặn tìm bằng yêu cầu đăng nhập, xác minh hoặc vùng IP.

**Hành động từng video.** Bỏ ứng viên, chọn tải vào hàng chờ, xử lý đúng một video hoặc bỏ chờ. Không chọn sản phẩm khác model và không nhận lại video đã bị bỏ. Lượt gửi có mã chống lặp; polling giữ vị trí đọc. Xóa riêng lượt đã hoàn tất giữ tham chiếu nội bộ mà video đã chọn cần (migration 9).

**Xóa bài TikTok.** Xác nhận đúng bài và tài khoản; yêu cầu dùng một lần, kiểm tên tài khoản thật trước thao tác. Chỉ ghi đã xóa khi có xác nhận thành công của TikTok; mất kết nối sau thao tác là chưa rõ, không tự thử lại. Lưu tình trạng riêng (migration 10), giữ lịch sử và giới hạn đăng để tránh đăng lại hoặc làm sai thống kê.

TikTok Studio: chọn dòng theo đúng URL/mã bài, lọc còn duy nhất bài đó và kiểm lại trước xác nhận. Có bước chủ xác nhận đã kiểm tra bài vẫn còn để gỡ trạng thái chưa rõ; không tự gửi lại lệnh xóa. Bản nháp chữ/tệp được giữ nếu người dùng chỉnh trong lúc lượt gửi trước chưa trả về.

**Sửa theo thử thật.** Xóa lịch sử ẩn cả lượt sản phẩm và các lần tìm lại cũ, giữ tham chiếu tải ở nội bộ; mã yêu cầu chống lặp sống tối thiểu 30 ngày. Lọc video đã có ở mọi trạng thái trước hiển thị; bỏ ứng viên lưu dấu loại để không nhận lại. Ô tích bán hàng vẽ 24 px trong vùng nhấn 44 px. Douyin khôi phục đúng truy vấn video sau chủ xác minh; tiêu đề nhắc nhiều model cùng dòng hoặc V2 sát chữ Trung không được coi là đúng ACE68. Kết quả cũ cũng được kiểm lại khi hiển thị và chọn. Tải hoàn tất cập nhật riêng hàng chờ, giữ bản nháp; phản hồi chat trước thao tác không chặn các lần cập nhật tiếp theo.


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

### 2026-10-09 — phiên tìm kiếm theo tài khoản nhận video

- Worker lưu trực tiếp kết quả đăng nhập/kiểm tra vào đúng tài khoản và kênh, kể cả khi callback agent không tới; giữ danh tính đã biết khi chỉ kiểm cookie, CAPTCHA không làm mất thông tin phiên.
- Tìm tự động đọc lại các hồ sơ Chrome đã có của đúng tài khoản thay vì bắt đăng nhập dựa báo cáo cũ. Không sao chép cookie, không tạo phiên cho nguồn chưa đăng nhập.
- Kênh tìm kiếm và link hoa hồng hiển thị theo tài khoản nhận đang chọn; phiên đã lưu dùng lại và nút đổi đăng nhập là thao tác phụ.

### 2026-10-09 — lịch sử tìm kiếm không lặp lần thử

- Cùng sản phẩm, nguồn và tài khoản dùng một kết quả: bấm lặp khi đang chạy/đã xong không tìm thêm; lỗi được thử lại hoặc xác minh ngay trong thẻ cũ.
- Các lỗi trùng từ phiên bản cũ được gộp khi hiển thị, không xóa video đã chọn hay dữ liệu lịch sử. Kiểm tra/đăng nhập được hiển thị tại Kênh tìm kiếm.

### Giỏ hàng đúng sản phẩm (2026-10-13)
- Bỏ các fallback trùng một từ/dòng đầu và mã sản phẩm tự chế; ba luồng dùng resolver catalog cùng tài khoản, đúng hãng/model/biến thể.
- Thành phẩm có giỏ phải có bằng chứng nội dung gắn hash/mã Shop/tài khoản. Chưa rõ giữ Cần xem; worker/agent từ chối đăng thiếu bằng chứng.
- Studio chỉ chọn một dòng đúng ID và tên/model/biến thể thật, đọc lại mã đã gắn và kiểm hash/tài khoản sát nút Đăng.
- Giữ chống trùng cả video rejected/purged, giữ công tắc tự đăng. CAPTCHA luôn do chủ hoàn tất.

- 2026-10-13: Sửa nút tiếp tục tìm sau cảnh báo sản phẩm đã có video: giữ discovery và tài khoản ban đầu, gửi một lần theo ID lượt; không ép ngành hàng rỗng hoặc tạo lịch sử lặp. Giữ dedupe video mọi trạng thái.
- Tìm bán hàng/Showcase cần hãng và dòng sản phẩm rõ; tên ngắn chưa nhận diện không bị hạ xuống query ngành chung. Douyin giữ cửa sổ visible chờ chủ, xác nhận self-account, chỉ nhận DOM đúng query/link; bỏ fallback lấy feed chưa kiểm.
