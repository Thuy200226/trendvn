#!/usr/bin/env bash
# Khôi phục từ bản sao lưu:  ./trendvn restore data/backups/trendvn-XXXX.tar.gz [--yes]
# Chạy trên thư mục dự án đã cài (hoặc vừa giải nén trên máy mới, sau ./trendvn install); ghi đè dữ liệu hiện có. Linux và macOS.
# Đọc được cả bản sao lưu tạo bởi các bản trước 1.3.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
[ -f "${1:-}" ] || { echo "Dùng: ./trendvn restore <file.tar.gz> [--yes]"; exit 2; }
ARCHIVE="$1"
need_project
PROJ="$(project_name)"
if [ "${2:-}" != "--yes" ]; then
  echo "Sẽ GHI ĐÈ dữ liệu của project Docker '$PROJ' trong thư mục này:"
  echo "  - data/worker (hàng đợi SQLite, khóa Gemini, thông báo)   - volume ${PROJ}_n8n_data   - khóa trong .env"
  read -r -p "Gõ 'khoiphuc' để tiếp tục: " ans; [ "$ans" = "khoiphuc" ] || exit 1
fi
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
tar xzf "$ARCHIVE" -C "$TMP"
# Check the archive BEFORE changing anything: a corrupt n8n copy would otherwise leave the volume empty or .env with the wrong key.
if [ -f "$TMP/n8n_data.tgz" ] && ! tar tzf "$TMP/n8n_data.tgz" >/dev/null 2>&1; then fail "Phần dữ liệu n8n trong bản sao lưu bị hỏng; chưa thay đổi gì."; fi
if [ -f "$TMP/tiktok_session.tgz" ] && ! tar tzf "$TMP/tiktok_session.tgz" >/dev/null 2>&1; then fail "Phần phiên TikTok trong bản sao lưu bị hỏng; chưa thay đổi gì."; fi
# Merge, never replace. THIS machine's .env keeps every value it already has (project name, ports, subnet, uid, proxy, password...).
# The backup contributes (a) the two secrets that MUST match the restored data - but only when the archive really carries the n8n data
# they open (N8N_ENCRYPTION_KEY opens the restored n8n data, TRENDVN_TOKEN is stored inside the restored n8n credential) - and
# (b) options this machine does not set yet. Network/uid keys of the machine that made the backup are never imported: a Linux bridge
# address is wrong on a Mac.
if [ -f "$TMP/env" ]; then
  [ -f .env ] && cp .env ".env.before-restore"
  HAS_N8N=0; [ -f "$TMP/n8n_data.tgz" ] && HAS_N8N=1
  python3 - "$TMP/env" .env "$HAS_N8N" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from envfile import format_line, parse
MACHINE = ('TRENDVN_SUBNET', 'TRENDVN_GATEWAY', 'TRENDVN_AGENT_BIND', 'TRENDVN_AGENT_HOSTREF', 'TRENDVN_UID', 'TRENDVN_GID', 'COMPOSE_PROJECT_NAME')
FROM_BACKUP = ('N8N_ENCRYPTION_KEY', 'TRENDVN_TOKEN')
backup = {k: v for k, v in parse(sys.argv[1]).items() if v}
mine = {k: v for k, v in parse(sys.argv[2]).items() if v}
merged = {k: v for k, v in backup.items() if k not in MACHINE}
merged.update(mine)
if sys.argv[3] == '1':
    merged.update({k: backup[k] for k in FROM_BACKUP if k in backup})
Path(sys.argv[2]).write_text('# Đã gộp từ bản sao lưu (giữ giá trị của máy này; khóa bí mật lấy từ bản sao lưu khi có dữ liệu n8n). Xem .env.example.\n'
                             + ''.join(format_line(k, v) + '\n' for k, v in merged.items()))
PY
  chmod 600 .env
  python3 scripts/setup_env.py >/dev/null      # adds whatever this machine still needs (secrets, subnet, uid...)
fi
PROJ="$(project_name)"
compose down
mkdir -p data/worker
if [ -f "$TMP/trendvn.sqlite3" ]; then cp "$TMP/trendvn.sqlite3" data/worker/trendvn.sqlite3; rm -f data/worker/trendvn.sqlite3-wal data/worker/trendvn.sqlite3-shm; fi
for f in gemini.key notify.json; do if [ -f "$TMP/$f" ]; then cp "$TMP/$f" "data/worker/$f"; chmod 600 "data/worker/$f"; fi; done
if [ -f "$TMP/n8n_data.tgz" ]; then
  IMG="$(compose config --images | grep n8n | head -1)"
  docker volume create "${PROJ}_n8n_data" >/dev/null
  docker run --rm --user 0 --entrypoint sh -v "${PROJ}_n8n_data":/d -v "$TMP":/in "$IMG" -c 'rm -rf /d/* /d/.[!.]* 2>/dev/null; tar xzf /in/n8n_data.tgz -C /d && chown -R 1000:1000 /d'
fi
if [ -f "$TMP/tiktok_session.tgz" ]; then
  bash scripts/agent.sh stop >/dev/null 2>&1 || true
  mkdir -p data/agent/profiles; rm -rf data/agent/profiles/publisher data/agent/profiles/publisher-*   # replace, do not mix with the current Chrome profiles
  tar xzf "$TMP/tiktok_session.tgz" -C data/agent/profiles
fi
# The restored n8n data remembers which schedules were ON. If the machine that made the backup still runs, two machines would post to
# one channel. Switch the schedules off in the restored data BEFORE n8n starts; turning them on again is a deliberate step.
if [ -f "$TMP/n8n_data.tgz" ]; then
  compose run --rm --no-deps -e N8N_RUNNERS_BROKER_PORT=5690 n8n unpublish:workflow --all >/dev/null 2>&1 \
    || warn "không tắt được lịch trong dữ liệu n8n đã khôi phục: kiểm tra ./trendvn n8n status và tắt bằng ./trendvn n8n deactivate trước khi để máy cũ chạy tiếp."
fi
compose_up
bash scripts/agent.sh restart >/dev/null 2>&1 || true      # the token may have changed: the agent must reload .env
echo "Đã khôi phục. Lịch tự động đang TẮT (tránh đăng trùng với máy cũ). Kiểm tra: ./trendvn doctor, rồi bật: ./trendvn n8n activate"
