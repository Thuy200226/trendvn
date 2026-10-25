#!/usr/bin/env bash
# Uninstall TrendVN (Linux and macOS): ./trendvn uninstall [--purge]
# Default HOLD data (data/, volume n8n, .env). --purge deletes data (no undo) but KEEPS data/backups and .env.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
need_env; need_docker; guard_project
PURGE=0; [ "${1:-}" = "--purge" ] && PURGE=1
if [ "$PURGE" = 1 ]; then
  echo "S"$'\341\272\275'" X"$'\303\223'"A: video, h"$'\303\240'"ng "$'\304\221'""$'\341\273\243'"i, kh"$'\303\263'"a Gemini, phi"$'\303\252'"n TikTok (data/worker, data/agent), .venv v"$'\303\240'" volume n8n c"$'\341\273\247'"a project '$(project_name)'."
  echo "S"$'\341\272\275'" GI"$'\341\273\256'": data/backups v"$'\303\240'" .env."
  ls data/backups/*.tar.gz >/dev/null 2>&1 || echo "C"$'\341\272\243'"nh b"$'\303\241'"o: ch"$'\306\260'"a c"$'\303\263'" b"$'\341\272\243'"n sao l"$'\306\260'"u n"$'\303\240'"o. N"$'\303\252'"n ch"$'\341\272\241'"y ./trendvn backup tr"$'\306\260'""$'\341\273\233'"c."
  read -r -p "G"$'\303\265'" 'xoa' "$'\304\221'""$'\341\273\203'" x"$'\303\241'"c nh"$'\341\272\255'"n: " ans
  [ "$ans" = "xoa" ] || { echo ""$'\304\220'""$'\303\243'" h"$'\341\273\247'"y. Ch"$'\306\260'"a thay "$'\304\221'""$'\341\273\225'"i g"$'\303\254'"."; exit 1; }
fi
bash scripts/agent.sh uninstall || true
if [ "$PURGE" = 1 ]; then
  compose down -v
  rm -rf data/worker data/agent .venv
  echo ""$'\304\220'""$'\303\243'" x"$'\303\263'"a d"$'\341\273\257'" li"$'\341\273\207'"u. C"$'\303\262'"n l"$'\341\272\241'"i: .env v"$'\303\240'" data/backups (x"$'\303\263'"a tay n"$'\341\272\277'"u mu"$'\341\273\221'"n)."
else
  compose down
  echo ""$'\304\220'""$'\303\243'" d"$'\341\273\253'"ng. D"$'\341\273\257'" li"$'\341\273\207'"u c"$'\303\262'"n nguy"$'\303\252'"n; ch"$'\341\272\241'"y ./trendvn install "$'\304\221'""$'\341\273\203'" d"$'\303\271'"ng l"$'\341\272\241'"i."
fi
