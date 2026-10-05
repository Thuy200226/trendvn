#!/usr/bin/env bash
# Sao lưu TrendVN vào data/backups/trendvn-YYYYMMDD-HHMMSS.tar.gz (quyền 0600). Linux và macOS.
#   ./trendvn backup [--with-session] [--keep N]
# Gồm: hàng đợi SQLite, khóa Gemini, cấu hình thông báo, .env, dữ liệu n8n.
#   --with-session  kèm phiên đăng nhập TikTok (để chuyển máy khỏi phải đăng nhập lại; coi như mật khẩu)
#   --keep N        chỉ giữ N bản mới nhất
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
need_project

WITH_SESSION=0; KEEP=0
while [ $# -gt 0 ]; do case "$1" in
  --with-session) WITH_SESSION=1;;
  --keep) shift; KEEP="${1:-}"; case "$KEEP" in ''|*[!0-9]*) fail "--keep cần một số nguyên (số bản sao lưu giữ lại)";; esac;;
  *) fail "Tham số lạ: $1";; esac; shift; done

STAMP="$(date +%Y%m%d-%H%M%S)"; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p data/backups && chmod 700 data/backups
PROJ="$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"

# Take the consistent copy of the live database INSIDE the worker container: reading a WAL database across Docker Desktop's file sharing
# (macOS) is not safe. Falls back to the host only when the worker is not running.
if compose exec -T worker python - <<'PY' 2>/dev/null
import sqlite3
src = sqlite3.connect('/data/trendvn.sqlite3'); dst = sqlite3.connect('/data/_backup.sqlite3')
with dst: src.backup(dst)
PY
then
  cp data/worker/_backup.sqlite3 "$TMP/trendvn.sqlite3" || fail "Không chép được bản sao cơ sở dữ liệu; sao lưu bị hủy."
  rm -f data/worker/_backup.sqlite3
elif [ -f data/worker/trendvn.sqlite3 ]; then
  python3 - "$TMP/trendvn.sqlite3" <<'PY'
import sqlite3, sys
src = sqlite3.connect('data/worker/trendvn.sqlite3'); dst = sqlite3.connect(sys.argv[1])
with dst: src.backup(dst)
PY
else
  warn "Chưa có cơ sở dữ liệu để sao lưu (worker chưa từng chạy?)."
fi
cp .env "$TMP/env"
for f in gemini.key notify.json; do if [ -f "data/worker/$f" ]; then cp "data/worker/$f" "$TMP/$f"; fi; done
IMG="$(compose config --images | grep n8n | head -1)"
# n8n keeps its data in SQLite: copy it while n8n is stopped (a few seconds) so the copy is consistent. It is always started again.
N8N_WAS_UP=0
if [ -n "$(compose ps -q --status running n8n 2>/dev/null)" ]; then N8N_WAS_UP=1; compose stop n8n >/dev/null 2>&1 || true; fi
restart_n8n() { if [ "$N8N_WAS_UP" = 1 ]; then compose start n8n >/dev/null 2>&1 || warn "n8n chưa khởi động lại được: chạy ./trendvn up"; N8N_WAS_UP=0; fi; }
trap 'restart_n8n; rm -rf "$TMP"' EXIT
if docker run --rm --user 0 --entrypoint tar -v "${PROJ}_n8n_data":/d:ro -v "$TMP":/out "$IMG" czf /out/n8n_data.tgz -C /d . 2>/dev/null; then :
else rm -f "$TMP/n8n_data.tgz"; warn "không sao lưu được volume n8n (n8n chưa từng chạy?); bản sao lưu này KHÔNG có dữ liệu n8n"; fi
restart_n8n
# one Chrome profile per TikTok account: `publisher` (the main account) and `publisher-<id>` (the others)
if [ "$WITH_SESSION" = 1 ]; then
  pack_rc=0; pack_profiles "$TMP/tiktok_session.tgz" data/agent/profiles || pack_rc=$?
  case "$pack_rc" in
    0) ;;
    10) warn "Chưa có hồ sơ TikTok nào để sao lưu (chưa đăng nhập lần nào?)." ;;
    *) fail "Không đóng gói được hồ sơ TikTok (tar mã $pack_rc); sao lưu bị hủy để khỏi lưu một bản thiếu cookie." ;;
  esac
fi
OUT="data/backups/trendvn-$STAMP.tar.gz"
tar czf "$OUT" -C "$TMP" .
chmod 600 "$OUT"
echo "Đã sao lưu: $OUT ($(du -h "$OUT" | cut -f1)) — chứa bí mật, cất ở nơi an toàn."
if [ "$KEEP" -gt 0 ] 2>/dev/null; then
  # oldest first; delete everything beyond the newest $KEEP
  # file names are ours (trendvn-YYYYMMDD-HHMMSS.tar.gz), so parsing ls is safe here
  # shellcheck disable=SC2012
  ls -1t data/backups/trendvn-*.tar.gz | awk -v k="$KEEP" 'NR>k' | while read -r old; do rm -f "$old"; echo "Đã xóa bản cũ: $old"; done
fi
