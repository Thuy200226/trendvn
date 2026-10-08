# Luồng vận hành và tiêu chí thay đổi TrendVN

Ngày 2026-10-07. Đây là bước thiết kế bắt buộc trước khi sửa logic theo yêu cầu của chủ. Tài liệu mô tả hành vi đang có, vấn đề cần kiểm chứng và hành vi dự kiến; không coi mọi đề xuất là đã triển khai.

## 1. Mục tiêu và bất biến

Luồng chính: **chọn tài khoản → tìm/thu thập → ứng viên → tải đúng video → chờ xử lý → dựng → duyệt nếu cần → đăng đúng tài khoản → xác minh → theo dõi hoặc xóa đúng bài**.

- Không lấy lại video đã có ở bất kỳ trạng thái nào, kể cả đã bỏ, lỗi, trùng hoặc đã xóa bài TikTok. Xóa lịch sử không xóa dấu chống trùng.
- Thương hiệu/model, thể loại và ngành hàng phải đi vào truy vấn nguồn thật. Ảnh chỉ giúp nhận diện, không chứng minh model khi mâu thuẫn với chữ.
- Mỗi tài khoản/nguồn dùng đúng hồ sơ của nó. TikTok phải đọc đúng tên tài khoản trước tìm, đăng và xóa.
- Tác vụ nền và nút tay dùng cùng luật/khóa. Không chạy hai thao tác trình duyệt cùng lúc; không nhận một video xử lý hai lần.
- Chưa rõ đã đăng/xóa thì không tự lặp hành động. CAPTCHA chỉ do chủ giải, không né hoặc tự giải.
- Kết quả thực tế quyết định nghiệm thu. Test fixture, cookie phiên, lượt xem và hình dáng sản phẩm không thay thế bằng chứng đăng nhập, doanh số hay model chính xác.

## 2. Trách nhiệm ba khối

| Khối | Trách nhiệm | Không giữ quyết định thay khối khác |
|---|---|---|
| Worker | SQLite, hàng đợi, quy tắc, quyền nhận việc, Gemini, ffmpeg, giao diện, lịch sử | Không tự điều khiển Chrome |
| Agent | Chrome thật, phiên theo nguồn/tài khoản, tìm/tải/đăng/xóa, gửi kết quả | Không tự cấp quyền đăng/xóa |
| n8n | Hẹn giờ và nối các bước đã có | Không sao chép luật nghiệp vụ |

SQLite live chỉ được mở từ worker/container cùng kernel; không mở trực tiếp từ macOS khi Docker đang giữ WAL. Bí mật và phiên Chrome ở nơi dữ liệu riêng, không vào Git hoặc tệp chẩn đoán.

## 3. Tài khoản và phiên

1. Chọn tài khoản nhận video; lấy thể loại mặc định nhưng cho phép đổi trước khi gửi.
2. TikTok dùng publisher của tài khoản đó; Douyin/Kuaishou/Instagram dùng hồ sơ nguồn riêng gắn với mã tài khoản.
3. Phân biệt **có cookie**, **đọc đúng danh tính**, **tìm được dữ liệu** và **đang cần xác minh**. Không ghi “thành công” chỉ vì có cookie.
4. Nguồn tự động chọn nguồn có phiên dùng được; nguồn chỉ định báo lỗi đúng nguồn, không âm thầm chuyển sang tài khoản/nguồn khác.
5. Đổi tên/xóa tài khoản không được làm việc đang xử lý hoặc quyền xóa cũ áp dụng sang danh tính mới.

## 4. Tìm kiếm: đầu vào tới kết quả

1. Chụp các lựa chọn tài khoản, nguồn, thể loại, công tắc bán hàng, ngành hàng và nội dung tại thời điểm gửi. Mã yêu cầu giữ nguyên khi gửi lại cùng lần; lần mới có mã mới.
2. Kiểm giới hạn chữ/tệp, loại tệp và đường dẫn. Tệp được đọc trong bộ nhớ; giao diện nói rõ ảnh/tài liệu chuyển cho Gemini.
3. Nhận diện chữ và ảnh độc lập; giữ mã model và cảnh báo mâu thuẫn. Không âm thầm thay sản phẩm chủ nhập bằng sản phẩm AI đoán.
4. Tạo truy vấn từng nguồn: từ khóa/model + thể loại + ngành hàng nếu bật. Nguồn Trung dùng từ khóa Trung và giữ model. Hiển thị truy vấn để kiểm tra.
5. Agent mở tìm kiếm của nguồn thật bằng đúng hồ sơ. Chỉ nhận video từ phản hồi của truy vấn hoặc chính đường dẫn được yêu cầu; không dùng luồng đề xuất thay cho kết quả tìm.
6. Nếu cần xác minh, giữ cửa sổ cho chủ. Sau khi chủ giải phải kiểm lại trang, trở về đúng truy vấn khi nền tảng chuyển hướng và tiếp tục thu kết quả; không dừng ở việc báo đã xác minh. Hết thời gian/không có dữ liệu phải nói rõ, không tự đổi sản phẩm.
7. Chuẩn hóa `(nguồn, mã video)` và URL; lọc video đã có trước khi đưa vào ứng viên. Sau đó đánh giá độ khớp, loại model khác, xếp theo độ khớp và dữ liệu tương tác đọc được.
8. Tách số nguồn trả về, số video đã có bị bỏ qua, số khác model và số ứng viên mới. Không biến “tất cả đã có” thành lỗi nguồn hoặc lượt tìm nhân đôi.

Chế độ bán hàng chưa có dữ liệu doanh số xác minh: chỉ gọi là video sản phẩm có tương tác cao. Hoa hồng/giỏ hàng cần dữ liệu và quyền thật; không suy ra từ việc tài khoản đăng ký nhà sáng tạo.

## 5. Thu thập tự động và chống trùng nhiều lớp

| Lớp | Khóa/bằng chứng | Hành vi cần giữ |
|---|---|---|
| Lô nguồn | `(platform, source_id)` và URL chuẩn | Không thêm job thứ hai khi quét hoặc tìm lại |
| Trước tải | Job tồn tại, trạng thái nhận tải, tài khoản ghim | Không tải lại video đã có; không chuyển sang tài khoản khác |
| Sau tải | SHA-256 tệp | Nội dung trùng không vào dựng |
| Trước dựng/đăng | Dấu vân tay hình, mô tả/hồ sơ đã đăng | Chặn nội dung hình gần giống và mô tả trùng theo luật hiện có; không chứng minh ý tưởng trùng |
| Sau xóa | Giữ job, nguồn, hash, thời điểm đã đăng | Không quên dấu chống trùng/hạn mức |

Lần quét đầu của luồng tạo baseline, không kéo video cũ vào xử lý hàng loạt. Lô cũ hơn lần trước hoặc không hợp lệ bị từ chối. Backlog và dung lượng đĩa giới hạn tải; không tải thêm chỉ để bù số kết quả bị lọc trùng.

## 6. Ứng viên và hàng chờ

- Ứng viên chưa có tệp: chọn đúng ID → nhận quyền tải một lần → tải và kiểm tệp → queued. Không gọi Gemini khi chưa có tệp hợp lệ.
- Bỏ ứng viên/khỏi hàng chờ là quyết định được lưu, không xóa dấu nhận biết nguồn. Video đang nhận tải/xử lý không bị thao tác bỏ làm hỏng.
- Xử lý riêng B chỉ nhận B, không rơi về A ở đầu hàng chờ nếu B bận hoặc đã đổi trạng thái.
- Lỗi tải an toàn trả về chờ tải với lý do; lỗi Gemini quá tải xếp lại, không đánh dấu video hỏng.

## 7. Dựng và duyệt

`queued → processing → ready/awaiting_approval/needs_review`. Worker nhận việc trong giao dịch và dùng lease để kết quả cũ không ghi đè lượt mới.

Phân tích nội dung/chủ đề/âm thanh → chọn giữ nguyên/Vietsub/thuyết minh → ffmpeg dựng → kiểm thời lượng/giải mã/phụ đề/âm thanh/dấu vân tay → tạo mô tả → duyệt theo cấu hình. Video nhạy cảm, khác chủ đề hoặc chưa chắc phải vào Cần xem. Không đổi các ngưỡng hoặc tham số Gemini khi chưa đo được lợi ích.

Ngoại lệ hiện có cần giữ khi sửa lỗi này: video tìm sản phẩm được miễn lọc chủ đề tài khoản và luôn chờ duyệt. Không coi chế độ bán hàng là quyền tự động bỏ bước duyệt.

## 8. Đăng và xác minh

1. Chọn video sẵn sàng và tài khoản đủ điều kiện; kiểm công tắc, phiên, giờ, hạn mức, giãn cách, bài chưa rõ và hash.
2. Nhận quyền một lần; agent kiểm danh tính rồi tải đúng tệp/điền đúng caption và chế độ hiển thị.
3. Xem thử dừng trước Đăng. Đăng thật chỉ trong phạm vi được chủ cho phép.
4. Đã bấm Đăng nhưng chưa có bằng chứng: publish_unknown, không đăng lại tự động. Có bằng chứng bài trên hồ sơ: published với URL/mã bài.
5. Đọc hiệu quả thật theo tài khoản; không gán chỉ số của bài khác.

Đăng tay hiện được miễn công tắc Tự đăng, giờ vàng, hạn mức và giãn cách; đây là hành vi đang có, không thay đổi ngầm trong lần sửa này. Xác minh tài khoản, hash, bài chưa rõ và quyền nhận việc vẫn được giữ.

## 9. Xóa bài TikTok

1. Xác nhận bài, URL, tài khoản; worker cấp quyền một lần gắn với cả ba.
2. Agent kiểm đúng tài khoản và bài. Trang xem có menu riêng thì dùng; Studio phải lọc còn đúng một video, kiểm exact ID/URL và truy vấn trước mọi bước xóa.
3. Chờ nút/hộp xác nhận tải xong; không coi menu đang mở là hộp xác nhận cuối. Chỉ bấm duy nhất nút xóa được xác định rõ.
4. Tự động ghi deleted chỉ khi có thông báo thành công rõ của TikTok, observer được gắn trước nút cuối và loại thông báo ẩn. Bài biến mất/404 không đủ bằng chứng.
5. Chưa rõ giữ unknown. Chủ kiểm đúng bài trong tài khoản sở hữu có thể xác nhận vẫn còn (failed rồi tạo quyền mới) hoặc đã xóa (deleted, lưu rõ bằng chứng do chủ kiểm). Chỉ nhận đúng URL/tài khoản/danh tính/job published và chỉ một lần. Quyền cũ không dùng lại, không tự xóa lại.
6. Giữ lịch sử đăng, hạn mức và chống trùng. Bài kiểm thử riêng 7693824713411317013 đã bấm xóa, chủ kiểm tra xác nhận đã xóa; cần chốt trạng thái ứng dụng qua bước xác nhận kết quả.

## 10. Lịch sử và giao diện

- Mỗi lượt có ID gốc, câu hỏi và các câu trả lời con. Xóa một lượt phải bỏ đúng phần hiển thị, không xóa dấu chống trùng, video hoặc tham chiếu cần cho tải.
- Cần tái hiện lỗi chủ báo trước khi quyết định sửa: phân biệt lỗi nút/hộp xác nhận, phản hồi máy chủ, lượt đang chạy và tin con xuất hiện lại. Không thay toàn bộ máy trạng thái chỉ để che một lỗi hiển thị.
- Lượt đang chạy: không âm thầm xóa tham chiếu; nếu chưa cho xóa phải báo ngay tại nút, nêu lý do rõ. Nếu hỗ trợ ẩn phải bảo đảm mọi kết quả đến muộn cùng lượt vẫn ẩn và tác vụ không bị mồ côi.
- Polling chỉ có một yêu cầu đang bay; không kéo người đang đọc xuống cuối, không mất draft chữ/tệp hoặc trạng thái tick.
- Dấu nhận `request_key` phải sống độc lập với việc xóa phần hiển thị lịch sử, tối thiểu 30 ngày. Gửi lại cùng mã trong thời hạn đó không tạo lượt mới/gọi Gemini lại, kể cả sau xóa lịch sử.
- Checkbox vẽ ô khoảng 20–24 px, vùng nhấn cả nhãn tối thiểu 44 px. Không dùng ô vuông 44 px để đạt chuẩn vùng nhấn. Tái sử dụng component, focus và select chung.

## 11. Đánh giá tối ưu trước sửa

Thiết kế hiện tại phù hợp hệ thống cục bộ một trình duyệt: SQLite giao dịch, worker quyết định một nơi, agent dùng phiên thật, n8n chỉ nối bước. Chưa có số đo để nói “tối ưu nhất”; thêm hàng đợi phân tán hoặc nhiều Chrome đồng thời sẽ tăng chi phí và rủi ro mà chưa có nhu cầu đo được.

Các điểm cần cải thiện có căn cứ từ mã/thử thật:

| Điểm | Căn cứ | Quyết định trước triển khai |
|---|---|---|
| Xóa lịch sử | Chủ báo không chạy; trước đó một số lượt lỗi xóa được | Tái hiện đúng màn hình/lượt, sửa nguyên nhân và regression; không xóa dữ liệu chống trùng |
| Tìm Douyin sau xác minh | Vòng chờ chỉ nhìn phản hồi, không chắc khôi phục truy vấn sau chuyển hướng | Thử bằng cửa sổ có chủ xác minh, theo dõi truy vấn thật; chỉ thêm khôi phục khi đo được hướng trang |
| Video cũ trong kết quả chat | videos_select chặn trùng nhưng videos_rank chưa lọc job cũ | Lọc batch theo ID/URL trước hiển thị; giữ kiểm giao dịch khi chọn để chặn race |
| Checkbox quá lớn | CSS sales đặt chính ô vuông 44×44 | Dùng checkbox nhỏ chung, nhãn chạm 44 px; kiểm Chrome/mobile |
| Xóa bài | Thử thật cho thấy Studio popup menu và dialog chuyển chậm | Chờ đúng nút xác nhận, đối chiếu ID, chỉ kết luận sau thông báo thật |
| Chi phí/độ trễ | Gemini/nguồn chặn là phần chờ chính | Không gọi lại Gemini khi retry tìm cùng sản phẩm; không vòng lặp tìm vô hạn, không đổi hàng loạt từ khóa |

Giới hạn khôi phục Douyin dự kiến: tối đa một lần điều hướng về đúng truy vấn trong một lượt chờ, chỉ sau khi không còn CAPTCHA và URL đã chuyển khỏi truy vấn. Không tự nạp lại khi chủ đang giải. Nếu lại bị chặn hoặc hết hạn thì báo rõ. Lọc video cũ chỉ áp dụng khi tạo danh sách mới; không xóa ứng viên đã chọn hoặc tham chiếu cần để thử tải lại.

## 12. Thứ tự sửa và nghiệm thu

1. Đối chiếu/rà độc lập tài liệu này và mã. Ghi bổ sung quy tắc thiết kế trước triển khai vào AGENTS.
2. Tái hiện xóa lịch sử trên bản đang chạy; sửa và thử thật từng lượt, toàn bộ lịch sử, lượt đang chạy, kết quả về muộn.
3. Thu nhỏ ô tick, giữ vùng nhấn; lọc video đã có, giữ tất cả lớp chống trùng và thử đồng thời hai lượt chọn cùng video.
4. Mở Douyin đúng truy vấn và hồ sơ để chủ xác minh. Sau xác minh tiếp tục tới khi lấy được video hoặc xác định chính xác điều kiện bên ngoài còn thiếu; không báo đạt khi chỉ mở được trang.
5. Tải một ứng viên thật mới phù hợp; xử lý đúng video đó; thử bỏ ứng viên/khỏi hàng chờ bằng dữ liệu thử riêng, không ảnh hưởng video cũ của chủ.
6. Xóa dứt điểm đúng bài kiểm thử đã đăng nếu có đủ bằng chứng và quyền; không đăng thêm bài thử mới.
7. Kiểm thử regression, Chrome bảy viewport, rà độc lập, cập nhật tài liệu/doctor và biên bản thật. Mỗi bước phân biệt triển khai, fixture đạt, thật đạt, bị chặn.

Thành công tìm Douyin bắt buộc có: truy vấn đã gửi, ID/URL video nguồn thật, bằng chứng model phù hợp, số video cũ bị loại, chọn/tải đúng ID và trạng thái hàng chờ. Nếu cần chủ đăng nhập/xác minh, mở đúng cửa sổ và báo rõ; chỉ chủ thực hiện bước đó.

### Chẩn đoán sau xác minh (18:40, trước khi bổ sung mã)

Chủ đã báo xác minh xong nhưng lượt chờ vẫn kết thúc không nhận video; sau khi mở lại chủ xác nhận thấy danh sách video ACE68. Cần đo bộ đọc phản hồi thay vì đổi truy vấn. Ý tưởng chụp toàn trang đã loại trước triển khai vì có thể lưu QR/OTP trong cửa sổ đăng nhập. Chỉ ghi số đếm và cấu trúc trường đã cho phép của phản hồi tìm kiếm: trạng thái HTTP, có/khớp keyword, số phần tử và số video bộ đọc nhận. Không ghi giá trị nội dung, URL đầy đủ, cookie, header hoặc payload mạng. Chẩn đoán không thay truy vấn, không né xác minh và không tự tìm lại vô hạn. Sau khi đọc bằng chứng mới sửa nguyên nhân cụ thể.

18:45: lượt 21 đã trả 16 video thật, không cần triển khai chẩn đoán phản hồi. Bằng chứng mới: ACE75 nhắc ACE68 và ACE68V2 sát chữ Trung bị coi là ứng viên khớp từ khóa. Trước khi tải, sửa ranh giới phiên bản theo chữ Latin/số (chữ Trung không được che `V2`), và chặn nhiều mã khác nhau trong cùng dòng model (`ACE75`/`ACE68`). Áp dụng cùng luật khi vẽ kết quả cũ và khi chọn ở máy chủ; không tin điểm khớp đã lưu từ phiên bản cũ. Thử lại bằng chính tiêu đề thật và giữ các ca đúng ACE68, thông số, Unicode và biến thể đã có.

Rà độc lập bổ sung: guard phải nhận cả `ACE-68`/`ACE-75`. Bỏ ứng viên chat hiện chỉ xóa thẻ nên tìm lại nhận lại được: trước khi sửa đã chốt lưu dấu `rejected` không tệp/tài khoản/lượt tìm cùng giao dịch bỏ thẻ. Nếu job nguồn/ID hoặc URL đã có thì giữ nguyên, không thay thế hoặc đổi trạng thái. Hai thứ tự chọn/bỏ đồng thời phải cho đúng một quyết định, không tải video bị bỏ hoặc ghi đè job đang xử lý.

Thử tải thật 7627431070878744296 đã vào queued, nhưng thẻ chat còn “chờ tải” tới khi tải lại. Trước sửa: bổ sung picked search_selected/candidate vào cờ polling, và cập nhật riêng vùng hàng chờ khi tác vụ kết thúc; không tải lại cả trang làm mất draft/tệp hoặc thay các form cài đặt. Chỉ lấy fragment hàng chờ lúc hoàn tất, tránh tăng truy vấn mỗi 2,5 giây. Nghiệm thu bằng Chrome chờ thấy queued trong cả chat và bảng mà không reload.

Rà độc lập: sau POST phải chờ GET/chat đang chạy kết thúc rồi lấy snapshot mới, không dùng lại snapshot trước POST. Cờ busy dựa vào task tải đang chạy, không dựa vào search_selected sau thất bại. Thử xóa bài riêng: Studio có ô tìm kiếm đã điền nhưng vẫn còn ba dòng, dừng trước thao tác Xóa. Bước kế tiếp chỉ gửi Enter như giao diện yêu cầu, giữ guard duy nhất bài và đọc lại kết quả; không hạ guard để ép xóa.

Gửi Enter với toàn caption vẫn còn ba dòng, chưa bấm Xóa. Bước thử tiếp theo dùng một từ dài có sẵn trong caption (bài thử: `TrendVN`) thay vì toàn câu/hashtag, gửi đúng một truy vấn. Vẫn bắt buộc duy nhất URL/mã bài đã xác nhận và query không đổi trước mọi thao tác; không thử chuỗi từ khóa liên tục hoặc nới điều kiện an toàn.

19:10: tìm `TrendVN` đã cô lập đúng bài thử, bấm Xóa và xác nhận; danh sách thành rỗng nhưng không bắt được toast. Trang công khai báo video không khả dụng. Không dùng hai dấu hiệu này để tự ghi deleted. Chủ đã tự kiểm tra tài khoản và xác nhận bài đã xóa: bổ sung bước chủ xác nhận kết quả deleted cho đúng bài unknown, giữ kiểm tài khoản/URL/mã, lịch sử/hạn mức và cấm xóa lại. Lưu rõ bằng chứng là chủ xác nhận, phân biệt thông báo nền tảng tự động. Đặt observer trước lần bấm cuối để giữ thông báo thành công thoáng qua theo text node; không mở rộng thành công sang “không tìm thấy”. Thử browser riêng thông báo ngắn/có nút đóng và trường hợp không có proof.

Full test 943 phát hiện test xoay thể loại phụ thuộc giờ máy: lượt đầu dùng giờ thật, lượt sau giả 10800 nên có lúc cùng vòng. Chỉ cố định cả hai mốc trong test (0 và 10800), không đổi logic thu thập đã có.

Rà độc lập cuối: thêm kiểm CSS visibility/opacity cả ancestor cho notice, không chỉ thuộc tính hidden; regression Chrome gồm toast thoáng qua có nút đóng và thông báo ẩn CSS. Chốt kết quả do chủ kiểm không gọi lại agent; kiểm job.account cùng account đã cấp quyền và nhật ký tiếng Việt.

Tự rà cuối observer: chỉ xét text node có parent hiện rõ, không xét textContent tổng của một container hiện rõ vì có thể gom chữ từ con visibility:hidden. Chrome thêm phản ví dụ notice chỉ chứa duy nhất chữ ẩn; không dùng kết quả rỗng làm proof.

## Thiết kế lại business và UI ngày 2026-10-07, sau phản hồi 19:20

Trước khi triển khai tiếp, đối chiếu toàn bộ hành trình, nguồn sự thật, phân vùng thông báo và cập nhật trực tiếp trong [BUSINESS-UX.md](BUSINESS-UX.md). Sửa trải nghiệm theo thiết kế này; giữ máy trạng thái, chống trùng, quyền đăng/xóa và lịch hiện có. Kiểm tra thật ban đầu: ACE68 đã awaiting_approval, không còn tác vụ xử lý đang chạy.
