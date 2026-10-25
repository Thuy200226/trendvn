#!/usr/bin/env bash
# Move running system from OLD DIRECTORY (version 1.2) to this directory: ./trendvn migrate <old-folder> [--yes] [--no-service]
#
# What it does, in order (stop immediately if a check fails, before stopping anything else):
#   1. check the old directory, the job is running, this directory is empty (no .env yet)
#   2. backup using backup.sh of the old directory and test the backup
#   3. stop the agent and container of the old directory (keeping data and volume n8n intact)
#   4. Copy .env, data (runtime/ -> data/worker, agent_data/ -> data/agent, remove Chrome cache) here
#   5. ./trendvn install --no-activate (n8n calendar is still on, while off is still off; "Auto-post" remains the same)
#   6. Compare video numbers by status between old data and new system
# The old directory is REMAINED as a backup; don't run it at the same time (same Docker project name).
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"

YES=0; OLD=""; NOSERVICE=""
for a in "$@"; do case "$a" in --yes) YES=1;; --no-service) NOSERVICE="--no-service";; -h|--help) sed -n '2,12p' "$0"; exit 0;; -*) fail "Tham s"$'\341\273\221'" l"$'\341\272\241'": $a";; *) OLD="$a";; esac; done
[ -n "$OLD" ] && [ -d "$OLD" ] || { sed -n '2,3p' "$0"; exit 2; }
OLD="$(cd "$OLD" && pwd)"

# ---------------------------------------------------------------- 1. checks (nothing is stopped yet)
[ "$OLD" != "$ROOT" ] || fail "Th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'" v"$'\303\240'" th"$'\306\260'" m"$'\341\273\245'"c m"$'\341\273\233'"i l"$'\303\240'" m"$'\341\273\231'"t."
{ [ -f "$OLD/compose.yaml" ] && [ -f "$OLD/.env" ] && [ -d "$OLD/runtime" ]; } || fail "$OLD kh"$'\303\264'"ng gi"$'\341\273\221'"ng th"$'\306\260'" m"$'\341\273\245'"c TrendVN 1.2 (c"$'\341\272\247'"n compose.yaml, .env v"$'\303\240'" runtime/)."
[ ! -f "$ROOT/.env" ] || fail "Th"$'\306\260'" m"$'\341\273\245'"c n"$'\303\240'"y "$'\304\221'""$'\303\243'" c"$'\303\263'" .env ("$'\304\221'""$'\303\243'" c"$'\303\240'"i r"$'\341\273\223'"i). migrate ch"$'\341\273\211'" d"$'\303\271'"ng cho th"$'\306\260'" m"$'\341\273\245'"c m"$'\341\273\233'"i gi"$'\341\272\243'"i n"$'\303\251'"n, ch"$'\306\260'"a c"$'\303\240'"i."
[ ! -s "$ROOT/data/worker/trendvn.sqlite3" ] || fail "Th"$'\306\260'" m"$'\341\273\245'"c n"$'\303\240'"y "$'\304\221'""$'\303\243'" c"$'\303\263'" d"$'\341\273\257'" li"$'\341\273\207'"u (data/worker/trendvn.sqlite3)."
have rsync || fail "C"$'\341\272\247'"n rsync (Mac v"$'\303\240'" Linux "$'\304\221'""$'\341\273\201'"u c"$'\303\263'" s"$'\341\272\265'"n)."
require_simple_path
check_prerequisites        # everything install will need, checked now, while the old system is still running

OLDPROJ="$(cd "$OLD" && docker compose config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')" \
  || fail "Kh"$'\303\264'"ng "$'\304\221'""$'\341\273\215'"c "$'\304\221'""$'\306\260'""$'\341\273\243'"c c"$'\341\272\245'"u h"$'\303\254'"nh Docker c"$'\341\273\247'"a $OLD."
echo "Th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'" : $OLD  (project Docker '$OLDPROJ')"
echo "Th"$'\306\260'" m"$'\341\273\245'"c m"$'\341\273\233'"i: $ROOT"

# a task that is running right now (processing, posting...) must finish first
OLDINFO="$(python3 scripts/migrate_tools.py info "$OLD/.env")"
OLDTOKEN="${OLDINFO%% *}"; OLDPORT="${OLDINFO##* }"
RUNNING="$(python3 scripts/migrate_tools.py tasks "$OLDPORT" "$OLDTOKEN")"
case "$RUNNING" in
  0) echo "Worker c"$'\305\251'" "$'\304\221'"ang r"$'\341\272\243'"nh." ;;
  unreachable) warn "Worker c"$'\305\251'" kh"$'\303\264'"ng tr"$'\341\272\243'" l"$'\341\273\235'"i ("$'\304\221'"ang t"$'\341\272\257'"t?). V"$'\341\272\253'"n ti"$'\341\272\277'"p t"$'\341\273\245'"c n"$'\341\272\277'"u b"$'\341\272\241'"n "$'\304\221'""$'\341\273\223'"ng "$'\303\275'"." ;;
  *) fail "Worker c"$'\305\251'" "$'\304\221'"ang ch"$'\341\272\241'"y $RUNNING vi"$'\341\273\207'"c (x"$'\341\273\255'" l"$'\303\275'"/"$'\304\221'""$'\304\203'"ng...). "$'\304\220'""$'\341\273\243'"i ch"$'\303\272'"ng xong r"$'\341\273\223'"i ch"$'\341\272\241'"y l"$'\341\272\241'"i." ;;
esac

if [ "$YES" != 1 ]; then
  echo
  echo "S"$'\341\272\275'": sao l"$'\306\260'"u, D"$'\341\273\252'"NG agent v"$'\303\240'" container "$'\341\273\237'" th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'" (m"$'\341\272\245'"t d"$'\341\273\213'"ch v"$'\341\273\245'" v"$'\303\240'"i ph"$'\303\272'"t), r"$'\341\273\223'"i c"$'\303\240'"i l"$'\341\272\241'"i t"$'\341\273\253'" th"$'\306\260'" m"$'\341\273\245'"c n"$'\303\240'"y v"$'\341\273\233'"i c"$'\303\271'"ng d"$'\341\273\257'" li"$'\341\273\207'"u."
  echo "L"$'\341\273\213'"ch t"$'\341\273\261'" "$'\304\221'""$'\341\273\231'"ng v"$'\303\240'" \"T"$'\341\273\261'" "$'\304\221'""$'\304\203'"ng\" gi"$'\341\273\257'" nguy"$'\303\252'"n tr"$'\341\272\241'"ng th"$'\303\241'"i hi"$'\341\273\207'"n t"$'\341\272\241'"i. Th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'" "$'\304\221'""$'\306\260'""$'\341\273\243'"c gi"$'\341\273\257'" l"$'\303\240'"m d"$'\341\273\261'" ph"$'\303\262'"ng."
  read -r -p "G"$'\303\265'" 'chuyen' "$'\304\221'""$'\341\273\203'" b"$'\341\272\257'"t "$'\304\221'""$'\341\272\247'"u: " ans; [ "$ans" = "chuyen" ] || { echo ""$'\304\220'""$'\303\243'" h"$'\341\273\247'"y. Ch"$'\306\260'"a thay "$'\304\221'""$'\341\273\225'"i g"$'\303\254'"."; exit 1; }
fi

# ---------------------------------------------------------------- 2. backup
say "1/5 Sao l"$'\306\260'"u th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'""
if [ -x "$OLD/backup.sh" ]; then (cd "$OLD" && ./backup.sh); else warn "Kh"$'\303\264'"ng th"$'\341\272\245'"y backup.sh "$'\341\273\237'" th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'": b"$'\341\273\217'" qua sao l"$'\306\260'"u (d"$'\341\273\257'" li"$'\341\273\207'"u v"$'\341\272\253'"n c"$'\303\262'"n nguy"$'\303\252'"n "$'\341\273\237'" "$'\304\221'""$'\303\263'")."; fi
# names are ours (trendvn-YYYYMMDD-HHMMSS.tar.gz), so parsing ls is safe here
# shellcheck disable=SC2012
LATEST="$(ls -1t "$OLD"/backups/trendvn-*.tar.gz 2>/dev/null | head -1 || true)"
if [ -n "$LATEST" ]; then
  tar tzf "$LATEST" >/dev/null 2>&1 || fail "B"$'\341\272\243'"n sao l"$'\306\260'"u $LATEST kh"$'\303\264'"ng "$'\304\221'""$'\341\273\215'"c "$'\304\221'""$'\306\260'""$'\341\273\243'"c; d"$'\341\273\253'"ng, ch"$'\306\260'"a d"$'\341\273\253'"ng g"$'\303\254'"."
  echo "B"$'\341\272\243'"n sao l"$'\306\260'"u: $LATEST"
fi

# ---------------------------------------------------------------- 3. stop the old stack (from here on, print the way back if anything fails)
STOPPED=0
rollback_help() {
  local code=$?
  if [ "$STOPPED" = 1 ] && [ "$code" != 0 ]; then
    {
      printf '\n\033[1;31mChuy'$'\341\273\203''n ch'$'\306\260''a xong (m'$'\303\243'' %s).\033[0m '$'\304\220'''$'\306\260'''$'\341\273\235''ng lui v'$'\341\273\201'' th'$'\306\260'' m'$'\341\273\245''c c'$'\305\251'', d'$'\341\273\257'' li'$'\341\273\207''u '$'\341\273\237'' '$'\304\221'''$'\303\263'' v'$'\341\272\253''n nguy'$'\303\252''n:\n' "$code"
      echo "  cd \"$ROOT\" && ./trendvn down; ./trendvn agent stop"
      [ -f "$ROOT/data/backups/agent-service.before-migrate" ] && echo "  (Linux) cp \"$ROOT/data/backups/agent-service.before-migrate\" ~/.config/systemd/user/trendvn-agent.service && systemctl --user daemon-reload && systemctl --user start trendvn-agent"
      echo "  cd \"$OLD\" && docker compose up -d"
    } >&2
  fi
}
trap rollback_help EXIT

say "2/5 D"$'\341\273\253'"ng agent v"$'\303\240'" container c"$'\341\273\247'"a th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'""
mkdir -p "$ROOT/data/backups"
# only the service that runs THIS old folder: match its working directory exactly
UNIT="$HOME/.config/systemd/user/trendvn-agent.service"; PLIST="$HOME/Library/LaunchAgents/vn.trendvn.agent.plist"
if [ "$OS" = Darwin ]; then
  if [ -f "$PLIST" ] && grep -qF "<string>$OLD</string>" "$PLIST"; then
    cp "$PLIST" "$ROOT/data/backups/agent-service.before-migrate"; STOPPED=1
    launchctl bootout "gui/$(id -u)/vn.trendvn.agent" >/dev/null 2>&1 || true; echo ""$'\304\220'""$'\303\243'" d"$'\341\273\253'"ng agent c"$'\305\251'" (launchd)."
  fi
elif [ -f "$UNIT" ] && grep -qxF "WorkingDirectory=$OLD" "$UNIT"; then
  cp "$UNIT" "$ROOT/data/backups/agent-service.before-migrate"; STOPPED=1
  systemctl --user stop trendvn-agent.service && echo ""$'\304\220'""$'\303\243'" d"$'\341\273\253'"ng agent c"$'\305\251'" (systemd)."
fi
STOPPED=1
(cd "$OLD" && docker compose down)

# ---------------------------------------------------------------- 4. copy config and data
say "3/5 Ch"$'\303\251'"p c"$'\341\272\245'"u h"$'\303\254'"nh v"$'\303\240'" d"$'\341\273\257'" li"$'\341\273\207'"u"
cp "$OLD/.env" "$ROOT/.env"; chmod 600 "$ROOT/.env"
mkdir -p data/worker data/agent
rsync -a "$OLD/runtime/" data/worker/
if [ -d "$OLD/agent_data" ]; then
  # keep the TikTok/Chrome profiles (login sessions), skip the browser caches: hundreds of MB that Chrome rebuilds by itself
  rsync -a --exclude='Cache' --exclude='Code Cache' --exclude='GPUCache' --exclude='GrShaderCache' --exclude='ShaderCache' --exclude='DawnCache' \
        --exclude='component_crx_cache' --exclude='Service Worker/CacheStorage' --exclude='Crashpad' "$OLD/agent_data/" data/agent/
fi
if ls "$OLD"/backups/trendvn-*.tar.gz >/dev/null 2>&1; then cp -p "$OLD"/backups/trendvn-*.tar.gz data/backups/; fi
chmod 700 data data/worker data/agent data/backups 2>/dev/null || true
echo ""$'\304\220'""$'\303\243'" ch"$'\303\251'"p: $(du -sh data/worker | cut -f1) d"$'\341\273\257'" li"$'\341\273\207'"u worker, $(du -sh data/agent | cut -f1) h"$'\341\273\223'" s"$'\306\241'" tr"$'\303\254'"nh duy"$'\341\273\207'"t."

# ---------------------------------------------------------------- 5. install here
say "4/5 C"$'\303\240'"i "$'\304\221'""$'\341\272\267'"t t"$'\341\273\253'" th"$'\306\260'" m"$'\341\273\245'"c n"$'\303\240'"y"
# NOSERVICE is empty or a single flag, so word splitting is intended
# shellcheck disable=SC2086
TRENDVN_MIGRATING=1 bash scripts/install.sh --no-activate $NOSERVICE

# ---------------------------------------------------------------- 6. compare
say "5/5 "$'\304\220'""$'\341\273\221'"i chi"$'\341\272\277'"u d"$'\341\273\257'" li"$'\341\273\207'"u"
python3 scripts/migrate_tools.py compare "$ROOT" "$(worker_port)" "$(envval TRENDVN_TOKEN)"
STOPPED=0
echo
echo "Xong. H"$'\341\273\207'" th"$'\341\273\221'"ng ch"$'\341\272\241'"y t"$'\341\273\253'": $ROOT"
echo "Th"$'\306\260'" m"$'\341\273\245'"c c"$'\305\251'" ($OLD) "$'\304\221'""$'\306\260'""$'\341\273\243'"c gi"$'\341\273\257'" l"$'\303\240'"m d"$'\341\273\261'" ph"$'\303\262'"ng. KH"$'\303\224'"NG ch"$'\341\272\241'"y n"$'\303\263'" c"$'\303\271'"ng l"$'\303\272'"c (c"$'\303\271'"ng t"$'\303\252'"n project Docker). Khi "$'\304\221'""$'\303\243'" ch"$'\341\272\257'"c ch"$'\341\272\257'"n, x"$'\303\263'"a ho"$'\341\272\267'"c n"$'\303\251'"n n"$'\303\263'" l"$'\341\272\241'"i."
echo "Ki"$'\341\273\203'"m tra: ./trendvn status · ./trendvn doctor"
