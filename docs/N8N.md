# Hệ thống n8n: cách được build ra

n8n ở đây là **một n8n riêng của dự án**, chạy trong Docker cùng worker, không dùng chung với n8n nào khác và không cần tài khoản
n8n trên mạng. Toàn bộ nội dung của nó (6 workflow + 1 credential) **được sinh ra từ mã**, nên dựng lại trên máy nào cũng cho kết quả giống hệt.

```
n8n/build.py  ──sinh──►  n8n/workflows/*.json  ──n8n import──►  n8n (Docker)  ──lịch──►  worker / agent
   (nguồn chuẩn)          (kết quả, có trong repo)      manage.py                    HTTP, có token
```

## Thành phần

| File | Vai trò |
|---|---|
| `n8n/build.py` | **Nguồn chuẩn.** Mỗi workflow là vài dòng mô tả node và cạnh nối. Đọc `.env` để lấy cổng agent và múi giờ. Id node suy ra từ tên nên sinh lại cho file y hệt; `--check` báo lỗi nếu JSON trong repo lệch mã |
| `n8n/workflows/*.json` | Kết quả sinh ra, **không chứa bí mật**. Compose gắn thư mục này vào container n8n (`/import`, chỉ đọc) |
| `n8n/manage.py` | Nạp / bật / tắt / liệt kê / xuất qua CLI chính thức của n8n (`docker compose exec n8n n8n …`) |
| credential `TrendVN · Worker riêng` | Tạo lúc nạp từ `TRENDVN_TOKEN` trong `.env`; nằm trong volume n8n (mã hóa bằng `N8N_ENCRYPTION_KEY`), không nằm trong workflow |

## Sáu workflow

| Id | Tên | Kích hoạt | Làm gì |
|---|---|---|---|
| `trendvn01daily` | 01 · Thu thập và xử lý | mỗi 3 giờ | kiểm tra phiên TikTok → đối chiếu bài chưa xác nhận → thu thập 4 nguồn → dọn tác vụ gián đoạn → xử lý (Vietsub/lồng tiếng) |
| `trendvn02publish` | 02 · Đăng theo giờ vàng | mỗi 30 phút | hỏi worker có được đăng không (công tắc, giờ vàng, giới hạn ngày, giãn cách) rồi để agent đăng |
| `trendvn03daily` | 03 · Chốt ngày | 23:30 | đọc lượt xem để học nguồn nào hiệu quả, gửi tóm tắt |
| `trendvn00status` | 00 · Kiểm tra kết nối và mức sẵn sàng | bấm tay | đọc trạng thái thật của worker và agent |
| `trendvn10inbox` | 10 · Nhận quan sát | webhook có xác thực | nhập danh sách video từ công cụ ngoài |
| `trendvn20process` | 20 · Xử lý video và phụ đề Việt | bấm tay | chạy riêng bước xử lý |

Chỉ **01, 02, 03** là lịch tự động; `./trendvn n8n activate` bật ba cái này. Các nút trên bảng điều khiển là phần bổ sung, dùng chung khóa với lịch nên không bao giờ chạy chồng lên nhau.

## Quy trình làm việc

```bash
# Thay đổi hệ thống n8n: sửa n8n/build.py, rồi
./trendvn n8n build            # sinh lại JSON
./trendvn n8n import           # nạp vào n8n đang chạy (lịch đang bật vẫn bật)
./trendvn test lint            # bảo đảm JSON trong repo khớp mã

# Bạn sửa trực tiếp trong giao diện n8n và muốn giữ lại?
./trendvn n8n export           # lưu ra n8n/exported/*.json, rồi chuyển phần cần giữ vào n8n/build.py

# Bật / tắt lịch, xem trạng thái
./trendvn n8n activate         # 01, 02, 03
./trendvn n8n deactivate
./trendvn n8n status
```

`./trendvn install` và `./trendvn update` đã gọi sẵn `build` + `import` (+ `activate`), bạn không cần chạy tay trong lần cài đầu.

## Đăng nhập n8n từ máy khác

Không cần đóng gói tài khoản: mỗi máy có n8n của riêng mình, lần đầu mở `http://localhost:5680` bạn tạo tài khoản chủ.
Workflow gọi `http://worker:8080` và `http://trendvn-agent:<cổng>`, hai tên chỉ tồn tại trong mạng Docker của dự án, nên **đừng** đưa workflow này vào một n8n khác
(nó sẽ không tìm thấy worker). Muốn xem n8n của máy ở nhà từ xa: dùng đường hầm SSH hoặc VPN (xem [DEPLOY.md](DEPLOY.md)).

## Nâng phiên bản n8n

Phiên bản được ghim trong `compose.yaml` (`docker.n8n.io/n8nio/n8n:<phiên bản>`), vì workflow được sinh và kiểm thử cho đúng phiên bản đó.
Để nâng: đổi số phiên bản, `./trendvn backup`, `./trendvn up`, `./trendvn n8n import`, `./trendvn n8n status`, rồi chờ một chu kỳ lịch và xem Executions.
