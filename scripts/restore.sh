#!/usr/bin/env bash
# Restore from backup: ./trendvn restore data/backups/trendvn-XXXX.tar.gz [--yes]
# Run on the installed project folder (or just unpacked on a new machine, after ./trendvn install); overwrite existing data. Linux and macOS.
# Can also read backups created by versions before 1.3.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
[ -f "${1:-}" ] || { echo "D"$'\303\271'"ng: ./trendvn restore <file.tar.gz> [--yes]"; exit 2; }
ARCHIVE="$1"
need_project
PROJ="$(project_name)"
if [ "${2:-}" != "--yes" ]; then
  echo "S"$'\341\272\275'" GHI "$'\304\220'""$'\303\210'" d"$'\341\273\257'" li"$'\341\273\207'"u c"$'\341\273\247'"a project Docker '$PROJ' trong th"$'\306\260'" m"$'\341\273\245'"c n"$'\303\240'"y:"
  echo "  - data/worker (h"$'\303\240'"ng "$'\304\221'""$'\341\273\243'"i SQLite, kh"$'\303\263'"a Gemini, th"$'\303\264'"ng b"$'\303\241'"o)   - volume ${PROJ}_n8n_data   - kh"$'\303\263'"a trong .env"
  read -r -p "G"$'\303\265'" 'khoiphuc' "$'\304\221'""$'\341\273\203'" ti"$'\341\272\277'"p t"$'\341\273\245'"c: " ans; [ "$ans" = "khoiphuc" ] || exit 1
fi
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
tar xzf "$ARCHIVE" -C "$TMP"
# Check the archive BEFORE changing anything: a corrupt n8n copy would otherwise leave the volume empty or .env with the wrong key.
if [ -f "$TMP/n8n_data.tgz" ] && ! tar tzf "$TMP/n8n_data.tgz" >/dev/null 2>&1; then fail "Ph"$'\341\272\247'"n d"$'\341\273\257'" li"$'\341\273\207'"u n8n trong b"$'\341\272\243'"n sao l"$'\306\260'"u b"$'\341\273\213'" h"$'\341\273\217'"ng; ch"$'\306\260'"a thay "$'\304\221'""$'\341\273\225'"i g"$'\303\254'"."; fi
if [ -f "$TMP/tiktok_session.tgz" ] && ! tar tzf "$TMP/tiktok_session.tgz" >/dev/null 2>&1; then fail "Ph"$'\341\272\247'"n phi"$'\303\252'"n TikTok trong b"$'\341\272\243'"n sao l"$'\306\260'"u b"$'\341\273\213'" h"$'\341\273\217'"ng; ch"$'\306\260'"a thay "$'\304\221'""$'\341\273\225'"i g"$'\303\254'"."; fi
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
Path(sys.argv[2]).write_text('# \u0110\u00e3 g\u1ed9p t\u1eeb b\u1ea3n sao l\u01b0u (gi\u1eef gi\u00e1 tr\u1ecb c\u1ee7a m\u00e1y n\u00e0y; kh\u00f3a b\u00ed m\u1eadt l\u1ea5y t\u1eeb b\u1ea3n sao l\u01b0u khi c\u00f3 d\u1eef li\u1ec7u n8n). Xem .env.example.\n'
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
    || warn "kh"$'\303\264'"ng t"$'\341\272\257'"t "$'\304\221'""$'\306\260'""$'\341\273\243'"c l"$'\341\273\213'"ch trong d"$'\341\273\257'" li"$'\341\273\207'"u n8n "$'\304\221'""$'\303\243'" kh"$'\303\264'"i ph"$'\341\273\245'"c: ki"$'\341\273\203'"m tra ./trendvn n8n status v"$'\303\240'" t"$'\341\272\257'"t b"$'\341\272\261'"ng ./trendvn n8n deactivate tr"$'\306\260'""$'\341\273\233'"c khi "$'\304\221'""$'\341\273\203'" m"$'\303\241'"y c"$'\305\251'" ch"$'\341\272\241'"y ti"$'\341\272\277'"p."
fi
compose_up
bash scripts/agent.sh restart >/dev/null 2>&1 || true      # the token may have changed: the agent must reload .env
echo ""$'\304\220'""$'\303\243'" kh"$'\303\264'"i ph"$'\341\273\245'"c. L"$'\341\273\213'"ch t"$'\341\273\261'" "$'\304\221'""$'\341\273\231'"ng "$'\304\221'"ang T"$'\341\272\256'"T (tr"$'\303\241'"nh "$'\304\221'""$'\304\203'"ng tr"$'\303\271'"ng v"$'\341\273\233'"i m"$'\303\241'"y c"$'\305\251'"). Ki"$'\341\273\203'"m tra: ./trendvn doctor, r"$'\341\273\223'"i b"$'\341\272\255'"t: ./trendvn n8n activate"
