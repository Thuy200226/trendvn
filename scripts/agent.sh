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
  if [ "$OS" = Darwin ] && [ -f "$PLIST" ] && grep -qF "$ROOT/services/agent/server.py" "$PLIST"; then echo launchd
  elif [ "$OS" != Darwin ] && [ -f "$UNIT" ] && grep -qF "$ROOT/services/agent/server.py" "$UNIT" && has_systemd; then echo systemd
  else echo none; fi
}
foreign_service() { # warn before install replaces a service that points at a different folder
  local f="$UNIT"; [ "$OS" = Darwin ] && f="$PLIST"
  if [ -f "$f" ] && ! grep -qF "$ROOT/services/agent/server.py" "$f"; then
    warn "Đã có dịch vụ agent của một bản TrendVN khác ($(grep -oE '/[^ <]*/services/agent/server.py|/[^ <]*/agent/server.py' "$f" | head -1)). Bản cài này sẽ thay thế nó."
  fi
}

cmd_venv() {
  local py
  py="$(find_python)" || fail "Cần Python 3.10 trở lên cho agent (máy này: $(python3 -V 2>&1 || echo 'không có python3')). $(python_help)"
  "$py" -c 'import venv, ensurepip' 2>/dev/null || fail "Thiếu gói venv của $py (Debian/Ubuntu: sudo apt install python3-venv)."
  # rebuild a .venv that is unusable (interpreter gone after an upgrade) or too old (built with macOS's 3.9 by an earlier attempt)
  if [ ! -x "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then "$py" -m venv --clear "$ROOT/.venv"; fi
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r "$ROOT/services/agent/requirements.txt"
  info "Môi trường Python cho agent sẵn sàng (.venv, $("$PY" -V 2>&1))."
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
    info "Agent chạy dưới launchd: tự chạy khi bạn đăng nhập máy Mac."
    info "Lưu ý: Mac phải bật và không ngủ thì lịch mới chạy (caffeinate đã được dùng; gập màn hình laptop vẫn làm máy ngủ)."
  elif has_systemd; then
    mkdir -p "$(dirname "$UNIT")"
    python3 "$ROOT/scripts/render_service.py" "$ROOT/scripts/service/trendvn-agent.service.in" "$ROOT" > "$UNIT.tmp" && mv "$UNIT.tmp" "$UNIT"
    systemctl --user daemon-reload
    systemctl --user enable trendvn-agent.service
    systemctl --user restart trendvn-agent.service        # enable --now would leave an already-running old process alone
    info "Agent chạy dưới systemd (người dùng). Để tự chạy sau khi khởi động máy mà chưa đăng nhập: sudo loginctl enable-linger $USER"
  else
    warn "Máy này không có systemd người dùng hoặc launchd. Dùng: ./trendvn agent start (tiến trình nền) hoặc ./trendvn agent run (trong terminal)."
    return 0
  fi
}

cmd_uninstall() {
  case "$(mode)" in    # only ever remove the service that belongs to this folder
    launchd) launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true; rm -f "$PLIST" ;;
    systemd) systemctl --user disable --now trendvn-agent.service 2>/dev/null || true; rm -f "$UNIT"; systemctl --user daemon-reload 2>/dev/null || true ;;
  esac
  cmd_stop_pid
  info "Đã gỡ dịch vụ agent."
}

# The pid file survives reboots, and the number may since belong to an unrelated process: only trust it if that process is our agent.
pid_is_agent() { # pid_is_agent PID
  [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null && ps -p "$1" -o command= 2>/dev/null | grep -qF "services/agent/server.py"
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
      if pid_running; then info "Agent đã chạy (pid $(cat "$PIDFILE"))."; return 0; fi
      mkdir -p "$ROOT/data/agent"
      nohup "$PY" "$ROOT/services/agent/server.py" >>"$ROOT/data/agent/agent.out" 2>&1 &
      echo $! > "$PIDFILE"
      sleep 1
      if ! pid_running; then rm -f "$PIDFILE"; tail -n 8 "$ROOT/data/agent/agent.out" 2>/dev/null || true; fail "Agent tắt ngay sau khi chạy (xem các dòng trên). Chạy ./trendvn agent run để thấy lỗi đầy đủ."; fi
      info "Đã chạy agent nền (pid $(cat "$PIDFILE")). Để tự chạy lại sau khi khởi động máy: ./trendvn agent install" ;;
  esac
}

cmd_stop() {
  case "$(mode)" in
    systemd) systemctl --user stop trendvn-agent.service ;;
    launchd) launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true ;;
    none) cmd_stop_pid ;;
  esac
  info "Đã dừng agent."
}

cmd_restart() {
  case "$(mode)" in
    systemd) systemctl --user restart trendvn-agent.service ;;
    launchd) launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null || { launchctl bootstrap "gui/$(id -u)" "$PLIST"; } ;;
    none) cmd_stop_pid; cmd_start; return ;;
  esac
  info "Đã khởi động lại agent."
}

cmd_status() {
  need_env
  local m; m="$(mode)"
  info "Chế độ chạy: $m"
  case "$m" in
    systemd) systemctl --user --no-pager status trendvn-agent.service 2>&1 | sed -n 1,6p || true ;;
    launchd) launchctl print "gui/$(id -u)/$LABEL" 2>&1 | grep -E "state|pid|last exit" | head -4 || true ;;
    none) if pid_running; then info "tiến trình nền pid $(cat "$PIDFILE")"; else info "không chạy nền"; fi ;;
  esac
  if http_ok "http://$(agent_host):$(agent_port)/health"; then info "Agent trả lời: OK (http://$(agent_host):$(agent_port))"
  else info "Agent KHÔNG trả lời tại http://$(agent_host):$(agent_port). Thử: ./trendvn agent restart, rồi ./trendvn agent logs"; return 1; fi
}

cmd_logs() {
  local follow="" lines=100 f files=""
  while [ $# -gt 0 ]; do case "$1" in -f|--follow) follow="-f";; -n|--tail) shift; lines="${1:-100}";; *) fail "Tham số lạ: $1";; esac; shift; done
  case "$lines" in ''|*[!0-9]*) fail "-n cần một số" ;; esac
  # Under systemd the journal holds everything, including start-up crashes that happen before our own log file exists.
  if [ "$(mode)" = systemd ] && have journalctl; then exec journalctl --user -u trendvn-agent.service -n "$lines" --no-pager $follow; fi
  # Otherwise show every file that exists: agent.log (the agent's own log), launchd.log (macOS) and agent.out (background mode) also
  # carry Python tracebacks from crashes at start-up.
  for f in "$LOGFILE" "$ROOT/data/agent/launchd.log" "$ROOT/data/agent/agent.out"; do [ -s "$f" ] && files="$files $f"; done
  [ -n "$files" ] || fail "Chưa có log agent. Agent chưa từng chạy? Thử: ./trendvn agent start"
  # paths contain no spaces (require_simple_path), so word splitting here is intended
  # shellcheck disable=SC2086
  tail -n "$lines" $follow $files
}

cmd_run() { need_env; [ -x "$PY" ] || cmd_venv; exec "$PY" "$ROOT/services/agent/server.py"; }

cmd_update() {
  [ -x "$PY" ] || cmd_venv
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q --upgrade -r "$ROOT/services/agent/requirements.txt" yt-dlp
  info "Đã cập nhật yt-dlp/playwright."
  if [ "$(mode)" != none ]; then cmd_restart; fi
}

sub="${1:-status}"; [ $# -gt 0 ] && shift
case "$sub" in
  install) cmd_install ;; uninstall) cmd_uninstall ;; start) cmd_start ;; stop) cmd_stop ;; restart) cmd_restart ;;
  status) cmd_status ;; logs) cmd_logs "$@" ;; run) cmd_run ;; venv) cmd_venv ;; update) cmd_update ;;
  *) sed -n '2,11p' "$0"; exit 2 ;;
esac
