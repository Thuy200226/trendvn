#!/usr/bin/env bash
# Test: ./trendvn test [lint|unit|container|e2e|all] (default: lint + unit)
#   lint workflow matches generated code, all Python/shell files have correct syntax, no hidden/inverted characters in code, compose is valid, shell script runs on macOS bash 3.2
#   unit unit/integrated test suite on this machine (some test media is automatically skipped if the machine does not have ffmpeg)
#   container reruns entire test suite IN worker Docker image (with ffmpeg) + tests real video rendering
#   e2e opens real Chrome, checks interface in 7 sizes and all button click flows (needs .venv of agent; TRENDVN_SAMPLE=<video.mp4> for real video)
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"

lint() {
  say "lint: workflow n8n kh"$'\341\273\233'"p m"$'\303\243'" sinh"
  python3 n8n/build.py --check
  say "lint: c"$'\303\272'" ph"$'\303\241'"p Python"
  python3 - <<'PY'
import sys
from pathlib import Path
bad = 0
import ast
for d in ('services', 'n8n', 'scripts', 'tests'):
    for f in sorted(Path(d).rglob('*.py')):
        try:
            text = f.read_text(encoding='utf-8')
            compile(text, str(f), 'exec')
            if d in ('n8n', 'scripts'):          # host tools run on the system python3: macOS ships 3.9
                ast.parse(text, filename=str(f), feature_version=(3, 9))
        except SyntaxError as e:
            bad += 1; print('%s:%s %s' % (f, e.lineno, e.msg))
sys.exit(1 if bad else 0)
PY
  say "lint: kh"$'\303\264'"ng c"$'\303\263'" k"$'\303\275'" t"$'\341\273\261'" "$'\341\272\251'"n ho"$'\341\272\267'"c "$'\304\221'""$'\341\272\243'"o chi"$'\341\273\201'"u trong m"$'\303\243'" (ki"$'\341\273\203'"u t"$'\341\272\245'"n c"$'\303\264'"ng Trojan Source)"
  python3 - <<'PY'
import subprocess, sys, unicodedata
from pathlib import Path
bad = 0
names = subprocess.run(['git', 'ls-files'], capture_output=True, text=True).stdout.split() if Path('.git').exists() else [str(f) for f in Path('.').rglob('*') if f.is_file()]
for name in names:
    path = Path(name)
    if path.suffix in ('.png', '.jpg', '.gz', '.sha256', '.skill', '.ico', '.wav', '.mp4', '.sqlite3', '.pyc') or '.venv' in path.parts or not path.is_file():
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        continue
    for number, line in enumerate(text.splitlines(), 1):
        hidden = sorted({'U+%04X' % ord(c) for c in line if unicodedata.category(c) in ('Cf', 'Cc', 'Zl', 'Zp') and c not in '\t\r' or c in '\u3164\u2800\u115f\u1160\u034f'})
        if hidden:
            bad += 1; print('%s:%d k\u00fd t\u1ef1 \u1ea9n %s (vi\u1ebft b\u1eb1ng \\uXXXX thay v\u00ec d\u00e1n tr\u1ef1c ti\u1ebfp)' % (name, number, ' '.join(hidden)))
sys.exit(1 if bad else 0)
PY
  say "lint: "$'\304\221'""$'\341\273\213'"nh d"$'\341\272\241'"ng v"$'\303\240'" l"$'\341\273\227'"i Python (ruff, black)"
  if have ruff || python3 -m ruff --version >/dev/null 2>&1; then
    (have ruff && ruff check --no-cache . || python3 -m ruff check --no-cache .) || fail "ruff b"$'\303\241'"o l"$'\341\273\227'"i (s"$'\341\273\255'"a t"$'\341\273\261'" "$'\304\221'""$'\341\273\231'"ng ph"$'\341\272\247'"n an to"$'\303\240'"n: ./trendvn fmt)"
  else info "(b"$'\341\273\217'" qua ruff: python3 -m pip install -r requirements-dev.txt)"; fi
  # black's style changes between releases, so only the version pinned in requirements-dev.txt is trusted to judge the format
  local black_pin black_have=""
  black_pin="$(sed -n 's/^black==\([0-9.]*\).*/\1/p' requirements-dev.txt)"
  if have black; then black_have="$(black --version | sed -n 's/^black, \([0-9.]*\).*/\1/p')"; fi
  if [ -n "$black_have" ] && [ "$black_have" = "$black_pin" ]; then
    black --check -q services scripts n8n tests || fail "code ch"$'\306\260'"a "$'\304\221'""$'\303\272'"ng "$'\304\221'""$'\341\273\213'"nh d"$'\341\272\241'"ng black (ch"$'\341\272\241'"y: ./trendvn fmt)"
  else info "(b"$'\341\273\217'" qua black: c"$'\341\272\247'"n "$'\304\221'""$'\303\272'"ng b"$'\341\272\243'"n ${black_pin}, "$'\304\221'"ang c"$'\303\263'" ${black_have:-kh$(printf '\303\264')ng c$(printf '\303\263')} — python3 -m pip install -r requirements-dev.txt)"; fi
  say "lint: c"$'\303\272'" ph"$'\303\241'"p shell v"$'\303\240'" t"$'\306\260'""$'\306\241'"ng th"$'\303\255'"ch bash 3.2 (macOS)"
  local f bad=0
  for f in trendvn scripts/*.sh macos/*.command; do
    bash -n "$f" || { echo "c"$'\303\272'" ph"$'\303\241'"p: $f"; bad=1; }
    case "$f" in scripts/test.sh) continue;; esac
    if grep -nE 'declare -A|mapfile|readarray|\$\{[A-Za-z_]+(,,|\^\^)\}|readlink -f|sed -i|&>>|\|&' "$f"; then echo "d"$'\303\271'"ng c"$'\303\272'" ph"$'\303\241'"p kh"$'\303\264'"ng c"$'\303\263'" tr"$'\303\252'"n bash 3.2/BSD: $f"; bad=1; fi
  done
  [ "$bad" = 0 ] || fail "lint shell th"$'\341\272\245'"t b"$'\341\272\241'"i"
  if have shellcheck; then shellcheck -S warning -x trendvn scripts/*.sh macos/*.command || fail "shellcheck b"$'\303\241'"o l"$'\341\273\227'"i"; else info "(b"$'\341\273\217'" qua shellcheck: ch"$'\306\260'"a c"$'\303\240'"i)"; fi
  say "lint: t"$'\303\240'"i li"$'\341\273\207'"u kh"$'\341\273\233'"p m"$'\303\243'" (l"$'\341\273\207'"nh, li"$'\303\252'"n k"$'\341\272\277'"t, "$'\304\221'""$'\306\260'""$'\341\273\235'"ng d"$'\341\272\253'"n)"
  python3 scripts/doclint.py
  say "lint: m"$'\341\272\253'"u d"$'\341\273\213'"ch v"$'\341\273\245'" n"$'\341\273\201'"n (systemd, launchd) tr"$'\341\273\217'" t"$'\341\273\233'"i file c"$'\303\263'" th"$'\341\272\255'"t"
  python3 - <<'PY'
import os, plistlib, re, subprocess, sys
from pathlib import Path
bad = 0
for f in sorted(Path('scripts/service').glob('*.in')):
    text = f.read_text()
    for rel in re.findall(r'@ROOT@/([^\s<"]+)', text):
        if rel.startswith(('.venv/', 'data/')):          # created at install time
            continue
        if not Path(rel).exists():
            bad += 1; print('%s tr\u1ecf t\u1edbi %s nh\u01b0ng file kh\u00f4ng t\u1ed3n t\u1ea1i' % (f, rel))
    out = subprocess.run([sys.executable, 'scripts/render_service.py', str(f), '/tmp/a b&c'], capture_output=True, text=True,
                         env=dict(os.environ, DISPLAY=':0', WAYLAND_DISPLAY='wayland-0')).stdout
    if '@' in out.replace('@', '', 0) and re.search(r'@[A-Z]+@', out):
        bad += 1; print('%s c\u00f2n ch\u1ed7 gi\u1eef ch\u1ed7 ch\u01b0a thay' % f)
    if f.name.endswith('.plist.in'):
        plistlib.loads(out.encode())                              # valid XML plist even with '&' and spaces in the path
sys.exit(1 if bad else 0)
PY
  say "lint: compose.yaml h"$'\341\273\243'"p l"$'\341\273\207'""
  N8N_ENCRYPTION_KEY=lint TRENDVN_TOKEN=lint docker compose config -q
  info "lint OK"
}

unit() { say "unit: test tr"$'\303\252'"n m"$'\303\241'"y n"$'\303\240'"y"; python3 -m unittest discover -s tests -t .; }

container() {
  need_docker
  say "container: build image worker"
  # building needs no secrets, but compose insists the variables exist: use placeholders so tests run before ./trendvn install
  N8N_ENCRYPTION_KEY="${N8N_ENCRYPTION_KEY:-test}" TRENDVN_TOKEN="${TRENDVN_TOKEN:-test}" compose build worker
  local img="trendvn/worker:$TRENDVN_VERSION"
  say "container: b"$'\341\273\231'" test "$'\304\221'""$'\341\272\247'"y "$'\304\221'""$'\341\273\247'" trong image (c"$'\303\263'" ffmpeg)"
  docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT:/p:ro" -w /p -e PYTHONDONTWRITEBYTECODE=1 "$img" python -m unittest discover -s tests -t .
  say "container: d"$'\341\273\261'"ng video th"$'\341\272\255'"t b"$'\341\272\261'"ng ffmpeg"
  docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT/tests/e2e:/t:ro" -e PYTHONDONTWRITEBYTECODE=1 "$img" python /t/render_check.py
}

e2e() {
  [ -x .venv/bin/python ] || fail "Ch"$'\306\260'"a c"$'\303\263'" .venv. Ch"$'\341\272\241'"y: ./trendvn agent venv"
  say "e2e: Chrome th"$'\341\272\255'"t"
  .venv/bin/python tests/e2e/ui_e2e.py "$@"
}

what="${1:-default}"; [ $# -gt 0 ] && shift
case "$what" in
  default) lint; unit ;;
  lint) lint ;; unit) unit ;; container) container ;; e2e) e2e "$@" ;;
  all) lint; unit; container; e2e ;;
  *) sed -n '2,7p' "$0"; exit 2 ;;
esac
