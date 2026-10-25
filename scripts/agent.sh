#!/usr/bin/env bash
# Browser agent on this machine (the Chrome that collects trends and posts to TikTok). One command for every OS:
#   ./trendvn agent install|uninstall|start|stop|restart|status|logs|run|venv|update
#
#   install    install it as a background service that starts by itself (systemd on Linux, launchd on macOS)
#   start/stop/restart/status   control that service (without systemd/launchd: a background process with a pid file)
#   logs [-f] [-n N]            the agent's own log (data/agent/agent.log)
#   run        run in this terminal (Ctrl+C to stop); useful for debugging
#   venv       create/refresh .venv (Python packages for the agent)
#   update     upgrade yt-dlp/playwright inside .venv and restart the agent
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"

UNIT="$HOME/.config/systemd/user/trendvn-agent.service"
PLIST="$HOME/Library/LaunchAgents/vn.trendvn.agent.plist"
LABEL="vn.trendvn.agent"
PIDFILE="$ROOT/data/agent/agent.pid"
LOGFILE="$ROOT/data/agent/agent.log"
PY="$ROOT/.venv/bin/python"

has_systemd() { have systemctl && systemctl --user show-environment >/dev/null 2>&1; }
# Which supervisor runs THIS checkout's agent. A unit/plist installed by another copy of the project (different folder) is not ours:
# never start, stop or restart somebody else's agent.
mode() {
  if [ "$OS" = Darwin ] && [ -f "$PLIST" ] && grep -qF "$ROOT/services/agent" "$PLIST"; then echo launchd
  elif [ "$OS" != Darwin ] && [ -f "$UNIT" ] && grep -qF "$ROOT/services/agent" "$UNIT" && has_systemd; then echo systemd
  else echo none; fi
}
foreign_service() { # warn before install replaces a service that points at a different folder
  local f="$UNIT"; [ "$OS" = Darwin ] && f="$PLIST"
  if [ -f "$f" ] && ! grep -qF "$ROOT/services/agent" "$f"; then
    warn ""$'\304\220'""$'\303\243'" c"$'\303\263'" d"$'\341\273\213'"ch v"$'\341\273\245'" agent c"$'\341\273\247'"a m"$'\341\273\231'"t b"$'\341\272\243'"n TrendVN kh"$'\303\241'"c ($(grep -oE '/[^ <=]*/services/agent/src|/[^ <=]*/agent/server.py' "$f" | head -1)). B"$'\341\272\243'"n c"$'\303\240'"i n"$'\303\240'"y s"$'\341\272\275'" thay th"$'\341\272\277'" n"$'\303\263'"."
  fi
}

cmd_venv() {
  local py
  py="$(find_python)" || fail "C"$'\341\272\247'"n Python 3.10 tr"$'\341\273\237'" l"$'\303\252'"n cho agent (m"$'\303\241'"y n"$'\303\240'"y: $(python3 -V 2>&1 || echo 'kh'$'\303\264''ng c'$'\303\263'' python3')). $(python_help)"
  "$py" -c 'import venv, ensurepip' 2>/dev/null || fail "Thi"$'\341\272\277'"u g"$'\303\263'"i venv c"$'\341\273\247'"a $py (Debian/Ubuntu: sudo apt install python3-venv)."
  # rebuild a .venv that is unusable (interpreter gone after an upgrade) or too old (built with macOS's 3.9 by an earlier attempt)
  if [ ! -x "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then "$py" -m venv --clear "$ROOT/.venv"; fi
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r "$ROOT/services/agent/requirements.txt"
  info "M"$'\303\264'"i tr"$'\306\260'""$'\341\273\235'"ng Python cho agent s"$'\341\272\265'"n s"$'\303\240'"ng (.venv, $("$PY" -V 2>&1))."
}

cmd_install() {
  need_env
  require_simple_path
  foreign_service
  [ -x "$PY" ] || cmd_venv
  mkdir -p "$ROOT/data/agent"
  if [ "$OS" = Darwin ]; then
    mkdir -p "$(dirname "$PLIST")"
    python3 "$ROOT/scripts/render_service.py" "$ROOT/scripts/service/vn.trendvn.agent.plist.in" "$ROOT" > "$PLIST.tmp" && mv "$PLIST.tmp" "$PLIST"
    launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
    sleep 2     # let the old instance finish exiting; bootstrap right after bootout can fail with I/O error 5
    launchctl bootstrap "gui/$(id -u)" "$PLIST" || launchctl kickstart -k "gui/$(id -u)/$LABEL"
    info "Agent ch"$'\341\272\241'"y d"$'\306\260'""$'\341\273\233'"i launchd: t"$'\341\273\261'" ch"$'\341\272\241'"y khi b"$'\341\272\241'"n "$'\304\221'""$'\304\203'"ng nh"$'\341\272\255'"p m"$'\303\241'"y Mac."
    info "L"$'\306\260'"u "$'\303\275'": Mac ph"$'\341\272\243'"i b"$'\341\272\255'"t v"$'\303\240'" kh"$'\303\264'"ng ng"$'\341\273\247'" th"$'\303\254'" l"$'\341\273\213'"ch m"$'\341\273\233'"i ch"$'\341\272\241'"y (caffeinate "$'\304\221'""$'\303\243'" "$'\304\221'""$'\306\260'""$'\341\273\243'"c d"$'\303\271'"ng; g"$'\341\272\255'"p m"$'\303\240'"n h"$'\303\254'"nh laptop v"$'\341\272\253'"n l"$'\303\240'"m m"$'\303\241'"y ng"$'\341\273\247'")."
  elif has_systemd; then
    mkdir -p "$(dirname "$UNIT")"
    python3 "$ROOT/scripts/render_service.py" "$ROOT/scripts/service/trendvn-agent.service.in" "$ROOT" > "$UNIT.tmp" && mv "$UNIT.tmp" "$UNIT"
    systemctl --user daemon-reload
    systemctl --user enable trendvn-agent.service
    systemctl --user restart trendvn-agent.service        # enable --now would leave an already-running old process alone
    info "Agent ch"$'\341\272\241'"y d"$'\306\260'""$'\341\273\233'"i systemd (ng"$'\306\260'""$'\341\273\235'"i d"$'\303\271'"ng). "$'\304\220'""$'\341\273\203'" t"$'\341\273\261'" ch"$'\341\272\241'"y sau khi kh"$'\341\273\237'"i "$'\304\221'""$'\341\273\231'"ng m"$'\303\241'"y m"$'\303\240'" ch"$'\306\260'"a "$'\304\221'""$'\304\203'"ng nh"$'\341\272\255'"p: sudo loginctl enable-linger $USER"
  else
    warn "M"$'\303\241'"y n"$'\303\240'"y kh"$'\303\264'"ng c"$'\303\263'" systemd ng"$'\306\260'""$'\341\273\235'"i d"$'\303\271'"ng ho"$'\341\272\267'"c launchd. D"$'\303\271'"ng: ./trendvn agent start (ti"$'\341\272\277'"n tr"$'\303\254'"nh n"$'\341\273\201'"n) ho"$'\341\272\267'"c ./trendvn agent run (trong terminal)."
    return 0
  fi
}

cmd_uninstall() {
  case "$(mode)" in    # only ever remove the service that belongs to this folder
    launchd) launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true; rm -f "$PLIST" ;;
    systemd) systemctl --user disable --now trendvn-agent.service 2>/dev/null || true; rm -f "$UNIT"; systemctl --user daemon-reload 2>/dev/null || true ;;
  esac
  cmd_stop_pid
  info ""$'\304\220'""$'\303\243'" g"$'\341\273\241'" d"$'\341\273\213'"ch v"$'\341\273\245'" agent."
}

# The pid file survives reboots, and the number may since belong to an unrelated process: only trust it if that process is our agent
# (also the pre-1.4 layout's server.py, so an upgrade can stop the agent it is replacing).
pid_is_agent() { # pid_is_agent PID
  [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null && ps -p "$1" -o command= 2>/dev/null | grep -qE "trendvn_agent|services/agent/server\.py"
}
pid_running() { [ -f "$PIDFILE" ] && pid_is_agent "$(cat "$PIDFILE" 2>/dev/null || true)"; }
cmd_stop_pid() {
  if [ -f "$PIDFILE" ]; then
    local pid; pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if pid_is_agent "$pid"; then kill "$pid" 2>/dev/null || true; fi
    rm -f "$PIDFILE"
  fi
}

cmd_start() {
  need_env
  case "$(mode)" in
    systemd) systemctl --user start trendvn-agent.service ;;
    launchd) launchctl kickstart "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$PLIST" ;;
    none)
      [ -x "$PY" ] || cmd_venv
      if pid_running; then info "Agent "$'\304\221'""$'\303\243'" ch"$'\341\272\241'"y (pid $(cat "$PIDFILE"))."; return 0; fi
      mkdir -p "$ROOT/data/agent"
      PYTHONPATH="$ROOT/services/agent/src" nohup "$PY" -m trendvn_agent >>"$ROOT/data/agent/agent.out" 2>&1 &
      echo $! > "$PIDFILE"
      sleep 1
      if ! pid_running; then rm -f "$PIDFILE"; tail -n 8 "$ROOT/data/agent/agent.out" 2>/dev/null || true; fail "Agent t"$'\341\272\257'"t ngay sau khi ch"$'\341\272\241'"y (xem c"$'\303\241'"c d"$'\303\262'"ng tr"$'\303\252'"n). Ch"$'\341\272\241'"y ./trendvn agent run "$'\304\221'""$'\341\273\203'" th"$'\341\272\245'"y l"$'\341\273\227'"i "$'\304\221'""$'\341\272\247'"y "$'\304\221'""$'\341\273\247'"."; fi
      info ""$'\304\220'""$'\303\243'" ch"$'\341\272\241'"y agent n"$'\341\273\201'"n (pid $(cat "$PIDFILE")). "$'\304\220'""$'\341\273\203'" t"$'\341\273\261'" ch"$'\341\272\241'"y l"$'\341\272\241'"i sau khi kh"$'\341\273\237'"i "$'\304\221'""$'\341\273\231'"ng m"$'\303\241'"y: ./trendvn agent install" ;;
  esac
}

cmd_stop() {
  case "$(mode)" in
    systemd) systemctl --user stop trendvn-agent.service ;;
    launchd) launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true ;;
    none) cmd_stop_pid ;;
  esac
  info ""$'\304\220'""$'\303\243'" d"$'\341\273\253'"ng agent."
}

cmd_restart() {
  case "$(mode)" in
    systemd) systemctl --user restart trendvn-agent.service ;;
    launchd) launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null || { launchctl bootstrap "gui/$(id -u)" "$PLIST"; } ;;
    none) cmd_stop_pid; cmd_start; return ;;
  esac
  info ""$'\304\220'""$'\303\243'" kh"$'\341\273\237'"i "$'\304\221'""$'\341\273\231'"ng l"$'\341\272\241'"i agent."
}

cmd_status() {
  need_env
  local m; m="$(mode)"
  info "Ch"$'\341\272\277'" "$'\304\221'""$'\341\273\231'" ch"$'\341\272\241'"y: $m"
  case "$m" in
    systemd) systemctl --user --no-pager status trendvn-agent.service 2>&1 | sed -n 1,6p || true ;;
    launchd) launchctl print "gui/$(id -u)/$LABEL" 2>&1 | grep -E "state|pid|last exit" | head -4 || true ;;
    none) if pid_running; then info "ti"$'\341\272\277'"n tr"$'\303\254'"nh n"$'\341\273\201'"n pid $(cat "$PIDFILE")"; else info "kh"$'\303\264'"ng ch"$'\341\272\241'"y n"$'\341\273\201'"n"; fi ;;
  esac
  if http_ok "http://$(agent_host):$(agent_port)/health"; then info "Agent tr"$'\341\272\243'" l"$'\341\273\235'"i: OK (http://$(agent_host):$(agent_port))"
  else info "Agent KH"$'\303\224'"NG tr"$'\341\272\243'" l"$'\341\273\235'"i t"$'\341\272\241'"i http://$(agent_host):$(agent_port). Th"$'\341\273\255'": ./trendvn agent restart, r"$'\341\273\223'"i ./trendvn agent logs"; return 1; fi
}

cmd_logs() {
  local follow="" lines=100 f files=""
  while [ $# -gt 0 ]; do case "$1" in -f|--follow) follow="-f";; -n|--tail) shift; lines="${1:-100}";; *) fail "Tham s"$'\341\273\221'" l"$'\341\272\241'": $1";; esac; shift; done
  case "$lines" in ''|*[!0-9]*) fail "-n c"$'\341\272\247'"n m"$'\341\273\231'"t s"$'\341\273\221'"" ;; esac
  # Under systemd the journal holds everything, including start-up crashes that happen before our own log file exists.
  if [ "$(mode)" = systemd ] && have journalctl; then exec journalctl --user -u trendvn-agent.service -n "$lines" --no-pager $follow; fi
  # Otherwise show every file that exists: agent.log (the agent's own log), launchd.log (macOS) and agent.out (background mode) also
  # carry Python tracebacks from crashes at start-up.
  for f in "$LOGFILE" "$ROOT/data/agent/launchd.log" "$ROOT/data/agent/agent.out"; do [ -s "$f" ] && files="$files $f"; done
  [ -n "$files" ] || fail "Ch"$'\306\260'"a c"$'\303\263'" log agent. Agent ch"$'\306\260'"a t"$'\341\273\253'"ng ch"$'\341\272\241'"y? Th"$'\341\273\255'": ./trendvn agent start"
  # paths contain no spaces (require_simple_path), so word splitting here is intended
  # shellcheck disable=SC2086
  tail -n "$lines" $follow $files
}

# After an upgrade the installed unit/plist may be written for an older layout: rewrite it (and restart) when this folder has one,
# otherwise just restart the background process.
cmd_refresh() {
  if [ "$(mode)" != none ]; then cmd_install; else cmd_restart; fi
}

cmd_run() { need_env; [ -x "$PY" ] || cmd_venv; exec env PYTHONPATH="$ROOT/services/agent/src" "$PY" -m trendvn_agent; }

cmd_update() {
  [ -x "$PY" ] || cmd_venv
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q --upgrade -r "$ROOT/services/agent/requirements.txt" yt-dlp
  info ""$'\304\220'""$'\303\243'" c"$'\341\272\255'"p nh"$'\341\272\255'"t yt-dlp/playwright."
  if [ "$(mode)" != none ]; then cmd_refresh; fi
}

sub="${1:-status}"; [ $# -gt 0 ] && shift
case "$sub" in
  install) cmd_install ;; uninstall) cmd_uninstall ;; start) cmd_start ;; stop) cmd_stop ;; restart) cmd_restart ;;
  status) cmd_status ;; logs) cmd_logs "$@" ;; run) cmd_run ;; venv) cmd_venv ;; update) cmd_update ;; refresh) cmd_refresh ;;
  *) sed -n '2,11p' "$0"; exit 2 ;;
esac
