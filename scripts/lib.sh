# shellcheck shell=bash
# Shared helpers for TrendVN's shell scripts. Source it; do not run it.
# Compatible with macOS's stock bash 3.2 and BSD tools: the constructs to avoid are listed in scripts/test.sh (lint).

export PYTHONDONTWRITEBYTECODE=1      # running tests/tools must not scatter __pycache__ folders through the project
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"
cd "$ROOT" || exit 1

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '%s\n' "$*"; }
warn() { printf '\033[1;33mCảnh báo:\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31mLỗi:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Value of KEY in .env (last one wins), empty if absent.
envval() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2- | sed -E "s/[[:space:]]+#.*$//; s/^[\"'](.*)[\"']$/\1/" || true; }

# Give compose the version so the worker image is tagged and labelled with it.
TRENDVN_VERSION="$(cat "$ROOT/VERSION")"
export TRENDVN_VERSION

compose() { docker compose "$@"; }

# The background service is written into a unit/plist that cannot carry spaces or shell-special characters in a path safely,
# and macOS (TCC) forbids launchd jobs from reading ~/Documents, ~/Desktop and ~/Downloads without extra permissions.
require_simple_path() {
  case "$ROOT" in
    *[[:space:]\&\|\\\<\>\"\'%]*) fail "Đường dẫn thư mục dự án ($ROOT) có dấu cách hoặc ký tự đặc biệt; dịch vụ nền không xử lý được. Chuyển thư mục vào đường dẫn đơn giản, ví dụ ~/trendvn, rồi chạy lại." ;;
  esac
  if [ "$OS" = Darwin ] && [ "${TRENDVN_ALLOW_PROTECTED_DIR:-}" != 1 ]; then
    case "$ROOT" in
      "$HOME"/Documents/*|"$HOME"/Desktop/*|"$HOME"/Downloads/*)
        fail "macOS không cho dịch vụ nền đọc thư mục Documents, Desktop hay Downloads ($ROOT). Chuyển thư mục dự án vào ~/trendvn rồi chạy lại (docs/MAC.md)." ;;
    esac
  fi
}

# The Chrome profiles of the TikTok accounts (`publisher` for the main one, `publisher-<id>` for the others) packed into $1 from the
# profiles folder $2. Caches and the Singleton* lock files stay out: Chrome rebuilds the first, and a stale lock can keep Chrome from
# opening the profile on the machine it is restored to. Returns 0 when packed, 10 when there is no profile (not an error), and tar's own
# code when packing failed (a profile without its cookies must never pass for a backup). tar's 1 means "a file changed while it was read"
# (Chrome is running): the archive is still good.
pack_profiles() {
  local out="$1" dir="${2:-data/agent/profiles}" d names=() rc=0
  for d in "$dir"/publisher "$dir"/publisher-*; do
    if [ -d "$d" ]; then names+=("$(basename "$d")"); fi
  done
  [ "${#names[@]}" -gt 0 ] || return 10
  tar czf "$out" --exclude='Cache' --exclude='Code Cache' --exclude='GPUCache' --exclude='GrShaderCache' --exclude='ShaderCache' \
    --exclude='DawnCache' --exclude='component_crx_cache' --exclude='Service Worker/CacheStorage' --exclude='Crashpad' \
    --exclude='Singleton*' -C "$dir" "${names[@]}" || rc=$?
  [ "$rc" -le 1 ] || return "$rc"
  return 0
}

need_env() { [ -f "$ROOT/.env" ] || fail "Chưa cài đặt. Chạy: ./trendvn install"; }

need_docker() {
  have docker || fail "Chưa có Docker. Cài Docker Desktop (Mac) hoặc Docker Engine (Linux), xem docs/DEPLOY.md"
  docker info >/dev/null 2>&1 || {
    if [ "$OS" = Darwin ]; then fail "Docker Desktop chưa chạy. Mở ứng dụng Docker, đợi biểu tượng cá voi đứng yên rồi thử lại."; fi
    fail "Docker chưa chạy hoặc user hiện tại chưa có quyền (thử: sudo usermod -aG docker \$USER, rồi đăng nhập lại)."; }
}

# The agent's packages (playwright, yt-dlp) need Python 3.10+, newer than the 3.9 that macOS ships. Pick the newest interpreter installed.
# (The rest of the tooling - this CLI's Python helpers - only needs the system python3, 3.9 is fine.)
find_python() {
  local pass name dir c
  for pass in system conda; do        # a conda env can be deleted or renamed, breaking the .venv built on it: use one only if nothing else works
    for name in python3.13 python3.12 python3.11 python3.10 python3; do            # newest first
      for dir in /opt/homebrew/bin /usr/local/bin /usr/bin $(printf '%s' "$PATH" | tr ':' ' '); do   # system/Homebrew locations first, then PATH
        c="$dir/$name"
        [ -x "$c" ] || continue
        case "$c" in *conda*) [ "$pass" = conda ] || continue;; esac
        # must be new enough AND able to create a venv (Debian/Ubuntu ship python3 without the venv module)
        if "$c" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then printf '%s\n' "$c"; return 0; fi
      done
    done
  done
  return 1
}
python_help() {
  if [ "$OS" = Darwin ]; then echo "Cài Python mới: brew install python@3.12  (hoặc tải bản cài tại https://www.python.org/downloads/macos/), rồi chạy lại."
  else echo "Cài Python mới, ví dụ Ubuntu/Debian: sudo apt install python3.12 python3.12-venv, rồi chạy lại."; fi
}

agent_host() { local h; h="$(envval TRENDVN_AGENT_BIND)"; [ -n "$h" ] || h="$(envval TRENDVN_GATEWAY)"; printf '%s' "${h:-172.20.0.1}"; }
agent_port() { local p; p="$(envval TRENDVN_AGENT_PORT)"; printf '%s' "${p:-5682}"; }
worker_port() { local p; p="$(envval TRENDVN_WORKER_PORT)"; printf '%s' "${p:-5681}"; }
n8n_port() { local p; p="$(envval TRENDVN_N8N_PORT)"; printf '%s' "${p:-5680}"; }

# HTTP GET without depending on curl being present (macOS and most Linux have it; python3 is required anyway).
http_ok() { python3 - "$1" <<'PY' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=5)
PY
}

project_name() { compose config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])'; }

# Docker identifies a stack by its PROJECT NAME (default "trendvn"), not by folder. Two copies of this project on one machine share that
# name, so `down`, `up` or a restore in one would tear down or overwrite the other's containers and n8n volume. Refuse unless the
# containers of this project belong to THIS folder (or nothing runs yet).
guard_project() {
  [ "${TRENDVN_ALLOW_TAKEOVER:-}" = 1 ] && return 0
  local proj dirs physical
  proj="$(project_name)" || return 0
  [ -n "$proj" ] || return 0
  physical="$(cd "$ROOT" && pwd -P)"
  dirs="$(docker ps -a --filter "label=com.docker.compose.project=$proj" --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null \
          | sort -u | sed '/^$/d' | grep -v -x -F -e "$ROOT" -e "$physical" || true)"
  [ -z "$dirs" ] && return 0
  {
    printf '\033[1;31mDừng lại:\033[0m project Docker "%s" đang chạy từ THƯ MỤC KHÁC:\n  %s\n' "$proj" "$dirs"
    printf 'Chạy tiếp sẽ dừng/thay thế container đó và có thể ghi đè volume n8n của nó.\n'
    printf '  - Muốn CHUYỂN hệ thống sang thư mục này: vào thư mục kia chạy: docker compose down (giữ dữ liệu), rồi chạy lại ở đây (docs/DEPLOY.md, mục 11).\n'
    printf '  - Muốn chạy SONG SONG: đặt COMPOSE_PROJECT_NAME và cả ba cổng TRENDVN_N8N_PORT / TRENDVN_WORKER_PORT / TRENDVN_AGENT_PORT khác trong .env của thư mục này, cài với --no-service.\n'
    printf '  - Chắc chắn muốn thay thế: TRENDVN_ALLOW_TAKEOVER=1 ./trendvn <lệnh>\n'
  } >&2
  exit 1
}

need_project() { need_env; need_docker; guard_project; }

compose_up() { # build if needed, start, and wait until both containers are healthy
  need_project
  compose up -d --build --wait --wait-timeout 240 || {
    warn "Có container chưa khỏe. Xem log: ./trendvn logs"
    return 1; }
}

# Everything ./trendvn install needs from the machine; migrate runs it BEFORE it stops anything.
check_prerequisites() {
  have docker || {
    [ "$OS" = Darwin ] && fail "Chưa có Docker. Cài Docker Desktop: https://www.docker.com/products/docker-desktop/  (hoặc dùng Homebrew: brew install --cask docker-desktop), mở nó lên một lần rồi chạy lại."
    fail "Chưa có Docker. Cài: https://docs.docker.com/engine/install/"; }
  have python3 || {
    [ "$OS" = Darwin ] && fail "Chưa có python3. Chạy: xcode-select --install  (rồi cài thêm Python mới, xem hướng dẫn kế tiếp)"
    fail "Chưa có python3."; }
  python3 -c 'import sys; sys.exit(sys.version_info < (3,9))' || fail "Cần Python 3.9 trở lên (hiện $(python3 -V))."
  find_python >/dev/null || fail "Cần Python 3.10 trở lên, có venv, cho agent trình duyệt (hiện chỉ có $(python3 -V 2>&1); macOS chỉ kèm 3.9; Debian/Ubuntu cần thêm gói python3-venv). $(python_help)"
  docker compose version >/dev/null 2>&1 || fail "Chưa có 'docker compose' (v2). Cập nhật Docker."
  local cv; cv="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
  python3 -c 'import sys; v = tuple(int(x) for x in sys.argv[1].split("-")[0].split(".")[:2]); sys.exit(v < (2, 20))' "${cv:-0.0}" \
    || fail "Cần docker compose 2.20 trở lên (hiện ${cv:-không rõ}); cần cho lệnh chờ container khỏe. Cập nhật Docker (Mac: Docker Desktop mới nhất)."
  need_docker
  # Playwright drives Google Chrome (channel "chrome"), which it looks for only in Chrome's standard install location.
  local chrome
  if [ "$OS" = Darwin ]; then
    chrome="/Applications/Google Chrome.app"
    [ -d "$chrome" ] || fail "Chưa có Google Chrome trong thư mục /Applications. Cài: https://www.google.com/chrome/  (hoặc: brew install --cask google-chrome)"
  else
    chrome="$(command -v google-chrome || command -v google-chrome-stable || true)"
    [ -n "$chrome" ] || { [ -x /opt/google/chrome/chrome ] && chrome=/opt/google/chrome/chrome; }
    [ -n "$chrome" ] || fail "Chưa có Google Chrome (bản của Google, không phải Chromium/snap): https://www.google.com/chrome/"
  fi
  echo "Docker OK · Python agent: $(find_python) · Chrome: $chrome"
}

