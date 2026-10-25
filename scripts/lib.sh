# shellcheck shell=bash
# Shared helpers for TrendVN's shell scripts. Source it; do not run it.
# Compatible with macOS's stock bash 3.2 and BSD tools: the constructs to avoid are listed in scripts/test.sh (lint).

export PYTHONDONTWRITEBYTECODE=1      # running tests/tools must not scatter __pycache__ folders through the project
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"
cd "$ROOT" || exit 1

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '%s\n' "$*"; }
warn() { printf '\033[1;33mC'$'\341\272\243''nh b'$'\303\241''o:\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31mL'$'\341\273\227''i:\033[0m %s\n' "$*" >&2; exit 1; }
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
    *[[:space:]\&\|\\\<\>\"\'%]*) fail ""$'\304\220'""$'\306\260'""$'\341\273\235'"ng d"$'\341\272\253'"n th"$'\306\260'" m"$'\341\273\245'"c d"$'\341\273\261'" "$'\303\241'"n ($ROOT) c"$'\303\263'" d"$'\341\272\245'"u c"$'\303\241'"ch ho"$'\341\272\267'"c k"$'\303\275'" t"$'\341\273\261'" "$'\304\221'""$'\341\272\267'"c bi"$'\341\273\207'"t; d"$'\341\273\213'"ch v"$'\341\273\245'" n"$'\341\273\201'"n kh"$'\303\264'"ng x"$'\341\273\255'" l"$'\303\275'" "$'\304\221'""$'\306\260'""$'\341\273\243'"c. Chuy"$'\341\273\203'"n th"$'\306\260'" m"$'\341\273\245'"c v"$'\303\240'"o "$'\304\221'""$'\306\260'""$'\341\273\235'"ng d"$'\341\272\253'"n "$'\304\221'""$'\306\241'"n gi"$'\341\272\243'"n, v"$'\303\255'" d"$'\341\273\245'" ~/trendvn, r"$'\341\273\223'"i ch"$'\341\272\241'"y l"$'\341\272\241'"i." ;;
  esac
  if [ "$OS" = Darwin ] && [ "${TRENDVN_ALLOW_PROTECTED_DIR:-}" != 1 ]; then
    case "$ROOT" in
      "$HOME"/Documents/*|"$HOME"/Desktop/*|"$HOME"/Downloads/*)
        fail "macOS kh"$'\303\264'"ng cho d"$'\341\273\213'"ch v"$'\341\273\245'" n"$'\341\273\201'"n "$'\304\221'""$'\341\273\215'"c th"$'\306\260'" m"$'\341\273\245'"c Documents, Desktop hay Downloads ($ROOT). Chuy"$'\341\273\203'"n th"$'\306\260'" m"$'\341\273\245'"c d"$'\341\273\261'" "$'\303\241'"n v"$'\303\240'"o ~/trendvn r"$'\341\273\223'"i ch"$'\341\272\241'"y l"$'\341\272\241'"i (docs/MAC.md)." ;;
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

need_env() { [ -f "$ROOT/.env" ] || fail "Ch"$'\306\260'"a c"$'\303\240'"i "$'\304\221'""$'\341\272\267'"t. Ch"$'\341\272\241'"y: ./trendvn install"; }

need_docker() {
  have docker || fail "Ch"$'\306\260'"a c"$'\303\263'" Docker. C"$'\303\240'"i Docker Desktop (Mac) ho"$'\341\272\267'"c Docker Engine (Linux), xem docs/DEPLOY.md"
  docker info >/dev/null 2>&1 || {
    if [ "$OS" = Darwin ]; then fail "Docker Desktop ch"$'\306\260'"a ch"$'\341\272\241'"y. M"$'\341\273\237'" "$'\341\273\251'"ng d"$'\341\273\245'"ng Docker, "$'\304\221'""$'\341\273\243'"i bi"$'\341\273\203'"u t"$'\306\260'""$'\341\273\243'"ng c"$'\303\241'" voi "$'\304\221'""$'\341\273\251'"ng y"$'\303\252'"n r"$'\341\273\223'"i th"$'\341\273\255'" l"$'\341\272\241'"i."; fi
    fail "Docker ch"$'\306\260'"a ch"$'\341\272\241'"y ho"$'\341\272\267'"c user hi"$'\341\273\207'"n t"$'\341\272\241'"i ch"$'\306\260'"a c"$'\303\263'" quy"$'\341\273\201'"n (th"$'\341\273\255'": sudo usermod -aG docker \$USER, r"$'\341\273\223'"i "$'\304\221'""$'\304\203'"ng nh"$'\341\272\255'"p l"$'\341\272\241'"i)."; }
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
  if [ "$OS" = Darwin ]; then echo "C"$'\303\240'"i Python m"$'\341\273\233'"i: brew install python@3.12  (ho"$'\341\272\267'"c t"$'\341\272\243'"i b"$'\341\272\243'"n c"$'\303\240'"i t"$'\341\272\241'"i https://www.python.org/downloads/macos/), r"$'\341\273\223'"i ch"$'\341\272\241'"y l"$'\341\272\241'"i."
  else echo "C"$'\303\240'"i Python m"$'\341\273\233'"i, v"$'\303\255'" d"$'\341\273\245'" Ubuntu/Debian: sudo apt install python3.12 python3.12-venv, r"$'\341\273\223'"i ch"$'\341\272\241'"y l"$'\341\272\241'"i."; fi
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
    printf '\033[1;31mD'$'\341\273\253''ng l'$'\341\272\241''i:\033[0m project Docker "%s" '$'\304\221''ang ch'$'\341\272\241''y t'$'\341\273\253'' TH'$'\306\257'' M'$'\341\273\244''C KH'$'\303\201''C:\n  %s\n' "$proj" "$dirs"
    printf 'Ch'$'\341\272\241''y ti'$'\341\272\277''p s'$'\341\272\275'' d'$'\341\273\253''ng/thay th'$'\341\272\277'' container '$'\304\221'''$'\303\263'' v'$'\303\240'' c'$'\303\263'' th'$'\341\273\203'' ghi '$'\304\221'''$'\303\250'' volume n8n c'$'\341\273\247''a n'$'\303\263''.\n'
    printf '  - Mu'$'\341\273\221''n CHUY'$'\341\273\202''N h'$'\341\273\207'' th'$'\341\273\221''ng sang th'$'\306\260'' m'$'\341\273\245''c n'$'\303\240''y: v'$'\303\240''o th'$'\306\260'' m'$'\341\273\245''c kia ch'$'\341\272\241''y: docker compose down (gi'$'\341\273\257'' d'$'\341\273\257'' li'$'\341\273\207''u), r'$'\341\273\223''i ch'$'\341\272\241''y l'$'\341\272\241''i '$'\341\273\237'' '$'\304\221'''$'\303\242''y (docs/DEPLOY.md, m'$'\341\273\245''c 11).\n'
    printf '  - Mu'$'\341\273\221''n ch'$'\341\272\241''y SONG SONG: '$'\304\221'''$'\341\272\267''t COMPOSE_PROJECT_NAME v'$'\303\240'' c'$'\341\272\243'' ba c'$'\341\273\225''ng TRENDVN_N8N_PORT / TRENDVN_WORKER_PORT / TRENDVN_AGENT_PORT kh'$'\303\241''c trong .env c'$'\341\273\247''a th'$'\306\260'' m'$'\341\273\245''c n'$'\303\240''y, c'$'\303\240''i v'$'\341\273\233''i --no-service.\n'
    printf '  - Ch'$'\341\272\257''c ch'$'\341\272\257''n mu'$'\341\273\221''n thay th'$'\341\272\277'': TRENDVN_ALLOW_TAKEOVER=1 ./trendvn <l'$'\341\273\207''nh>\n'
  } >&2
  exit 1
}

need_project() { need_env; need_docker; guard_project; }

compose_up() { # build if needed, start, and wait until both containers are healthy
  need_project
  compose up -d --build --wait --wait-timeout 240 || {
    warn "C"$'\303\263'" container ch"$'\306\260'"a kh"$'\341\273\217'"e. Xem log: ./trendvn logs"
    return 1; }
}

# Everything ./trendvn install needs from the machine; migrate runs it BEFORE it stops anything.
check_prerequisites() {
  have docker || {
    [ "$OS" = Darwin ] && fail "Ch"$'\306\260'"a c"$'\303\263'" Docker. C"$'\303\240'"i Docker Desktop: https://www.docker.com/products/docker-desktop/  (ho"$'\341\272\267'"c d"$'\303\271'"ng Homebrew: brew install --cask docker-desktop), m"$'\341\273\237'" n"$'\303\263'" l"$'\303\252'"n m"$'\341\273\231'"t l"$'\341\272\247'"n r"$'\341\273\223'"i ch"$'\341\272\241'"y l"$'\341\272\241'"i."
    fail "Ch"$'\306\260'"a c"$'\303\263'" Docker. C"$'\303\240'"i: https://docs.docker.com/engine/install/"; }
  have python3 || {
    [ "$OS" = Darwin ] && fail "Ch"$'\306\260'"a c"$'\303\263'" python3. Ch"$'\341\272\241'"y: xcode-select --install  (r"$'\341\273\223'"i c"$'\303\240'"i th"$'\303\252'"m Python m"$'\341\273\233'"i, xem h"$'\306\260'""$'\341\273\233'"ng d"$'\341\272\253'"n k"$'\341\272\277'" ti"$'\341\272\277'"p)"
    fail "Ch"$'\306\260'"a c"$'\303\263'" python3."; }
  python3 -c 'import sys; sys.exit(sys.version_info < (3,9))' || fail "C"$'\341\272\247'"n Python 3.9 tr"$'\341\273\237'" l"$'\303\252'"n (hi"$'\341\273\207'"n $(python3 -V))."
  find_python >/dev/null || fail "C"$'\341\272\247'"n Python 3.10 tr"$'\341\273\237'" l"$'\303\252'"n, c"$'\303\263'" venv, cho agent tr"$'\303\254'"nh duy"$'\341\273\207'"t (hi"$'\341\273\207'"n ch"$'\341\273\211'" c"$'\303\263'" $(python3 -V 2>&1); macOS ch"$'\341\273\211'" k"$'\303\250'"m 3.9; Debian/Ubuntu c"$'\341\272\247'"n th"$'\303\252'"m g"$'\303\263'"i python3-venv). $(python_help)"
  docker compose version >/dev/null 2>&1 || fail "Ch"$'\306\260'"a c"$'\303\263'" 'docker compose' (v2). C"$'\341\272\255'"p nh"$'\341\272\255'"t Docker."
  local cv; cv="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
  python3 -c 'import sys; v = tuple(int(x) for x in sys.argv[1].split("-")[0].split(".")[:2]); sys.exit(v < (2, 20))' "${cv:-0.0}" \
    || fail "C"$'\341\272\247'"n docker compose 2.20 tr"$'\341\273\237'" l"$'\303\252'"n (hi"$'\341\273\207'"n ${cv:-kh$(printf '\303\264')ng r$(printf '\303\265')}); c"$'\341\272\247'"n cho l"$'\341\273\207'"nh ch"$'\341\273\235'" container kh"$'\341\273\217'"e. C"$'\341\272\255'"p nh"$'\341\272\255'"t Docker (Mac: Docker Desktop m"$'\341\273\233'"i nh"$'\341\272\245'"t)."
  need_docker
  # Playwright drives Google Chrome (channel "chrome"), which it looks for only in Chrome's standard install location.
  local chrome
  if [ "$OS" = Darwin ]; then
    chrome="/Applications/Google Chrome.app"
    [ -d "$chrome" ] || fail "Ch"$'\306\260'"a c"$'\303\263'" Google Chrome trong th"$'\306\260'" m"$'\341\273\245'"c /Applications. C"$'\303\240'"i: https://www.google.com/chrome/  (ho"$'\341\272\267'"c: brew install --cask google-chrome)"
  else
    chrome="$(command -v google-chrome || command -v google-chrome-stable || true)"
    [ -n "$chrome" ] || { [ -x /opt/google/chrome/chrome ] && chrome=/opt/google/chrome/chrome; }
    [ -n "$chrome" ] || fail "Ch"$'\306\260'"a c"$'\303\263'" Google Chrome (b"$'\341\272\243'"n c"$'\341\273\247'"a Google, kh"$'\303\264'"ng ph"$'\341\272\243'"i Chromium/snap): https://www.google.com/chrome/"
  fi
  echo "Docker OK · Python agent: $(find_python) · Chrome: $chrome"
}

