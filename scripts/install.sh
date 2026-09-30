#!/usr/bin/env bash
# Cài đặt TrendVN một lệnh cho Linux và macOS (chạy lại nhiều lần vẫn an toàn):
#   ./trendvn install [--no-activate] [--no-service]
#   --no-activate  nạp workflow vào n8n nhưng KHÔNG bật lịch tự động
#   --no-service   không cài dịch vụ nền cho agent (tự chạy: ./trendvn agent run)
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"

ACTIVATE=1; SERVICE=1
for a in "$@"; do case "$a" in
  --no-activate) ACTIVATE=0;; --no-service) SERVICE=0;;
  -h|--help) sed -n '2,5p' "$0"; exit 0;;
  *) echo "Tham số lạ: $a"; exit 2;; esac; done

say "1/8 Kiểm tra điều kiện ($OS)"
require_simple_path
check_prerequisites
df -Pk "$ROOT" | awk 'NR==2 && $4 < 4000000 {print "\033[1;33mCảnh báo:\033[0m ổ đĩa còn dưới 4GB, image Docker cần khoảng 2GB."}'

say "2/8 Tạo cấu hình và bí mật (không hiển thị)"
# A leftover n8n volume is encrypted with the key of the install that made it. A NEW random key would make n8n refuse to start, so
# refuse to invent one: the .env of that install (or a restore) has to come first.
if ! grep -qE '^N8N_ENCRYPTION_KEY=.' .env 2>/dev/null; then
  proj="${COMPOSE_PROJECT_NAME:-$(envval COMPOSE_PROJECT_NAME)}"; proj="${proj:-trendvn}"
  if docker volume inspect "${proj}_n8n_data" >/dev/null 2>&1; then
    fail "Đã có volume n8n '${proj}_n8n_data' của một lần cài trước, nhưng .env này chưa có N8N_ENCRYPTION_KEY. Tạo khóa mới sẽ làm n8n không đọc được dữ liệu cũ.
  - Chuyển từ bản cũ: chép .env của bản cũ vào đây rồi chạy lại (docs/DEPLOY.md, mục 11).
  - Cài mới hoàn toàn (BỎ dữ liệu n8n cũ): docker volume rm ${proj}_n8n_data"
  fi
fi
python3 scripts/setup_env.py

say "3/8 Môi trường Python cho agent trình duyệt"
bash scripts/agent.sh venv

say "4/8 Sinh workflow n8n từ mã"
python3 n8n/build.py

say "5/8 Dựng và chạy container (n8n + worker)"
compose_up || fail "Container chưa khỏe. Xem: ./trendvn logs"

say "6/8 Nạp workflow vào n8n"
python3 n8n/manage.py import

say "7/8 Bật lịch tự động"
if [ "$ACTIVATE" = 1 ]; then
  python3 n8n/manage.py activate || echo "Có workflow chưa bật được (xem trên). Bật tay trong giao diện n8n."
else
  echo "Bỏ qua (--no-activate). Bật sau bằng: ./trendvn n8n activate"
fi

say "8/8 Dịch vụ nền cho agent trình duyệt"
if [ "$SERVICE" = 1 ]; then bash scripts/agent.sh install
else echo "Không cài dịch vụ nền. Chạy tay trong một terminal riêng:  ./trendvn agent run"; fi

sleep 4
python3 scripts/doctor.py || true
[ "${TRENDVN_MIGRATING:-}" = 1 ] && exit 0       # ./trendvn migrate prints its own ending: an already configured system has no "5 things left"
cat <<MSG

Xong. 5 việc còn lại, chỉ bạn làm được:
  1. Mở bảng điều khiển  http://localhost:$(worker_port)  (./trendvn open) → Thêm → Cài đặt: nhập khóa Gemini (https://aistudio.google.com/apikey), bật "Xử lý video".
  2. Đăng nhập TikTok một lần (cửa sổ Chrome hiện ra, bạn tự nhập):  ./trendvn tiktok login
  3. Cài đặt → Lịch đăng: đặt "Tài khoản TikTok đích" đúng kênh vừa đăng nhập.
  4. Bấm "Bắt đầu" ở Tổng quan (lần quét đầu chỉ ghi mốc; bấm lại sau vài giờ) tới khi tab Đăng bài có video, rồi chạy thử không đăng thật:
     ./trendvn tiktok dry-run   (ảnh chụp: data/worker/exports/; "idle" nghĩa là chưa có video dựng xong)
  5. Bật "Tự đăng" trên bảng điều khiển khi đã hài lòng.
n8n: http://localhost:$(n8n_port) (lần đầu tạo tài khoản chủ). Muốn có TikTok/Instagram Mỹ: đặt TRENDVN_US_PROXY trong .env (docs/DEPLOY.md).
Mọi lệnh: ./trendvn help · Chẩn đoán: ./trendvn doctor · Xem log: ./trendvn logs -f
MSG
