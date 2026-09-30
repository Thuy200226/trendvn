#!/usr/bin/env bash
# Gỡ TrendVN (Linux và macOS):  ./trendvn uninstall [--purge]
# Mặc định GIỮ dữ liệu (data/, volume n8n, .env). --purge xóa dữ liệu (không hoàn tác) nhưng GIỮ data/backups và .env.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
need_env; need_docker; guard_project
PURGE=0; [ "${1:-}" = "--purge" ] && PURGE=1
if [ "$PURGE" = 1 ]; then
  echo "Sẽ XÓA: video, hàng đợi, khóa Gemini, phiên TikTok (data/worker, data/agent), .venv và volume n8n của project '$(project_name)'."
  echo "Sẽ GIỮ: data/backups và .env."
  ls data/backups/*.tar.gz >/dev/null 2>&1 || echo "Cảnh báo: chưa có bản sao lưu nào. Nên chạy ./trendvn backup trước."
  read -r -p "Gõ 'xoa' để xác nhận: " ans
  [ "$ans" = "xoa" ] || { echo "Đã hủy. Chưa thay đổi gì."; exit 1; }
fi
bash scripts/agent.sh uninstall || true
if [ "$PURGE" = 1 ]; then
  compose down -v
  rm -rf data/worker data/agent .venv
  echo "Đã xóa dữ liệu. Còn lại: .env và data/backups (xóa tay nếu muốn)."
else
  compose down
  echo "Đã dừng. Dữ liệu còn nguyên; chạy ./trendvn install để dùng lại."
fi
