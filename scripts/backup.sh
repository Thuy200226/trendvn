#!/usr/bin/env bash
# Backup TrendVN to data/backups/trendvn-YYYYMMDD-HHMMSS.tar.gz (permission 0600). Linux and macOS.
#   ./trendvn backup [--with-session] [--keep N]
# Includes: SQLite queue, Gemini key, notification configuration, .env, n8n data.
#   --with-session with TikTok login session (to switch devices without having to log in again; treated as password)
#   --keep N keeps only the latest N versions
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
need_project

WITH_SESSION=0; KEEP=0
while [ $# -gt 0 ]; do case "$1" in
  --with-session) WITH_SESSION=1;;
  --keep) shift; KEEP="${1:-}"; case "$KEEP" in ''|*[!0-9]*) fail "--keep c"$'\341\272\247'"n m"$'\341\273\231'"t s"$'\341\273\221'" nguy"$'\303\252'"n (s"$'\341\273\221'" b"$'\341\272\243'"n sao l"$'\306\260'"u gi"$'\341\273\257'" l"$'\341\272\241'"i)";; esac;;
  *) fail "Tham s"$'\341\273\221'" l"$'\341\272\241'": $1";; esac; shift; done

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
  cp data/worker/_backup.sqlite3 "$TMP/trendvn.sqlite3" || fail "Kh"$'\303\264'"ng ch"$'\303\251'"p "$'\304\221'""$'\306\260'""$'\341\273\243'"c b"$'\341\272\243'"n sao c"$'\306\241'" s"$'\341\273\237'" d"$'\341\273\257'" li"$'\341\273\207'"u; sao l"$'\306\260'"u b"$'\341\273\213'" h"$'\341\273\247'"y."
  rm -f data/worker/_backup.sqlite3
elif [ -f data/worker/trendvn.sqlite3 ]; then
  python3 - "$TMP/trendvn.sqlite3" <<'PY'
import sqlite3, sys
src = sqlite3.connect('data/worker/trendvn.sqlite3'); dst = sqlite3.connect(sys.argv[1])
with dst: src.backup(dst)
PY
else
  warn "Ch"$'\306\260'"a c"$'\303\263'" c"$'\306\241'" s"$'\341\273\237'" d"$'\341\273\257'" li"$'\341\273\207'"u "$'\304\221'""$'\341\273\203'" sao l"$'\306\260'"u (worker ch"$'\306\260'"a t"$'\341\273\253'"ng ch"$'\341\272\241'"y?)."
fi
cp .env "$TMP/env"
for f in gemini.key notify.json; do if [ -f "data/worker/$f" ]; then cp "data/worker/$f" "$TMP/$f"; fi; done
IMG="$(compose config --images | grep n8n | head -1)"
# n8n keeps its data in SQLite: copy it while n8n is stopped (a few seconds) so the copy is consistent. It is always started again.
N8N_WAS_UP=0
if [ -n "$(compose ps -q --status running n8n 2>/dev/null)" ]; then N8N_WAS_UP=1; compose stop n8n >/dev/null 2>&1 || true; fi
restart_n8n() { if [ "$N8N_WAS_UP" = 1 ]; then compose start n8n >/dev/null 2>&1 || warn "n8n ch"$'\306\260'"a kh"$'\341\273\237'"i "$'\304\221'""$'\341\273\231'"ng l"$'\341\272\241'"i "$'\304\221'""$'\306\260'""$'\341\273\243'"c: ch"$'\341\272\241'"y ./trendvn up"; N8N_WAS_UP=0; fi; }
trap 'restart_n8n; rm -rf "$TMP"' EXIT
if docker run --rm --user 0 --entrypoint tar -v "${PROJ}_n8n_data":/d:ro -v "$TMP":/out "$IMG" czf /out/n8n_data.tgz -C /d . 2>/dev/null; then :
else rm -f "$TMP/n8n_data.tgz"; warn "kh"$'\303\264'"ng sao l"$'\306\260'"u "$'\304\221'""$'\306\260'""$'\341\273\243'"c volume n8n (n8n ch"$'\306\260'"a t"$'\341\273\253'"ng ch"$'\341\272\241'"y?); b"$'\341\272\243'"n sao l"$'\306\260'"u n"$'\303\240'"y KH"$'\303\224'"NG c"$'\303\263'" d"$'\341\273\257'" li"$'\341\273\207'"u n8n"; fi
restart_n8n
# one Chrome profile per TikTok account: `publisher` (the main account) and `publisher-<id>` (the others)
if [ "$WITH_SESSION" = 1 ]; then
  pack_rc=0; pack_profiles "$TMP/tiktok_session.tgz" data/agent/profiles || pack_rc=$?
  case "$pack_rc" in
    0) ;;
    10) warn "Ch"$'\306\260'"a c"$'\303\263'" h"$'\341\273\223'" s"$'\306\241'" TikTok n"$'\303\240'"o "$'\304\221'""$'\341\273\203'" sao l"$'\306\260'"u (ch"$'\306\260'"a "$'\304\221'""$'\304\203'"ng nh"$'\341\272\255'"p l"$'\341\272\247'"n n"$'\303\240'"o?)." ;;
    *) fail "Kh"$'\303\264'"ng "$'\304\221'""$'\303\263'"ng g"$'\303\263'"i "$'\304\221'""$'\306\260'""$'\341\273\243'"c h"$'\341\273\223'" s"$'\306\241'" TikTok (tar m"$'\303\243'" $pack_rc); sao l"$'\306\260'"u b"$'\341\273\213'" h"$'\341\273\247'"y "$'\304\221'""$'\341\273\203'" kh"$'\341\273\217'"i l"$'\306\260'"u m"$'\341\273\231'"t b"$'\341\272\243'"n thi"$'\341\272\277'"u cookie." ;;
  esac
fi
OUT="data/backups/trendvn-$STAMP.tar.gz"
tar czf "$OUT" -C "$TMP" .
chmod 600 "$OUT"
echo ""$'\304\220'""$'\303\243'" sao l"$'\306\260'"u: $OUT ($(du -h "$OUT" | cut -f1)) — ch"$'\341\273\251'"a b"$'\303\255'" m"$'\341\272\255'"t, c"$'\341\272\245'"t "$'\341\273\237'" n"$'\306\241'"i an to"$'\303\240'"n."
if [ "$KEEP" -gt 0 ] 2>/dev/null; then
  # oldest first; delete everything beyond the newest $KEEP
  # file names are ours (trendvn-YYYYMMDD-HHMMSS.tar.gz), so parsing ls is safe here
  # shellcheck disable=SC2012
  ls -1t data/backups/trendvn-*.tar.gz | awk -v k="$KEEP" 'NR>k' | while read -r old; do rm -f "$old"; echo ""$'\304\220'""$'\303\243'" x"$'\303\263'"a b"$'\341\272\243'"n c"$'\305\251'": $old"; done
fi
