#!/usr/bin/env bash
# Kiểm thử:  ./trendvn test [lint|unit|container|e2e|all]      (mặc định: lint + unit)
#   lint       workflow khớp mã sinh, mọi file Python/shell đúng cú pháp, không ký tự ẩn/đảo chiều trong mã, compose hợp lệ, script shell chạy được trên bash 3.2 của macOS
#   unit       bộ test đơn vị/tích hợp trên máy này (một số test media tự bỏ qua nếu máy không có ffmpeg)
#   container  chạy lại toàn bộ bộ test TRONG image Docker của worker (có ffmpeg) + kiểm tra dựng video thật
#   e2e        mở Chrome thật, kiểm tra giao diện ở 7 kích thước và mọi luồng bấm nút (cần .venv của agent; TRENDVN_SAMPLE=<video.mp4> để có video thật)
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"

lint() {
  say "lint: workflow n8n khớp mã sinh"
  python3 n8n/build.py --check
  say "lint: cú pháp Python"
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
  say "lint: không có ký tự ẩn hoặc đảo chiều trong mã (kiểu tấn công Trojan Source)"
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
            bad += 1; print('%s:%d ký tự ẩn %s (viết bằng \\uXXXX thay vì dán trực tiếp)' % (name, number, ' '.join(hidden)))
sys.exit(1 if bad else 0)
PY
  say "lint: định dạng và lỗi Python (ruff, black)"
  if have ruff || python3 -m ruff --version >/dev/null 2>&1; then
    (have ruff && ruff check --no-cache . || python3 -m ruff check --no-cache .) || fail "ruff báo lỗi (sửa tự động phần an toàn: ./trendvn fmt)"
  else info "(bỏ qua ruff: python3 -m pip install -r requirements-dev.txt)"; fi
  # black's style changes between releases, so only the version pinned in requirements-dev.txt is trusted to judge the format
  local black_pin black_have=""
  black_pin="$(sed -n 's/^black==\([0-9.]*\).*/\1/p' requirements-dev.txt)"
  if have black; then black_have="$(black --version | sed -n 's/^black, \([0-9.]*\).*/\1/p')"; fi
  if [ -n "$black_have" ] && [ "$black_have" = "$black_pin" ]; then
    black --check -q services scripts n8n tests || fail "code chưa đúng định dạng black (chạy: ./trendvn fmt)"
  else info "(bỏ qua black: cần đúng bản ${black_pin}, đang có ${black_have:-không có} — python3 -m pip install -r requirements-dev.txt)"; fi
  say "lint: cú pháp shell và tương thích bash 3.2 (macOS)"
  local f bad=0
  for f in trendvn scripts/*.sh macos/*.command; do
    bash -n "$f" || { echo "cú pháp: $f"; bad=1; }
    case "$f" in scripts/test.sh) continue;; esac
    if grep -nE 'declare -A|mapfile|readarray|\$\{[A-Za-z_]+(,,|\^\^)\}|readlink -f|sed -i|&>>|\|&' "$f"; then echo "dùng cú pháp không có trên bash 3.2/BSD: $f"; bad=1; fi
  done
  [ "$bad" = 0 ] || fail "lint shell thất bại"
  if have shellcheck; then shellcheck -S warning -x trendvn scripts/*.sh macos/*.command || fail "shellcheck báo lỗi"; else info "(bỏ qua shellcheck: chưa cài)"; fi
  say "lint: tài liệu khớp mã (lệnh, liên kết, đường dẫn)"
  python3 scripts/doclint.py
  say "lint: mẫu dịch vụ nền (systemd, launchd) trỏ tới file có thật"
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
            bad += 1; print('%s trỏ tới %s nhưng file không tồn tại' % (f, rel))
    out = subprocess.run([sys.executable, 'scripts/render_service.py', str(f), '/tmp/a b&c'], capture_output=True, text=True,
                         env=dict(os.environ, DISPLAY=':0', WAYLAND_DISPLAY='wayland-0')).stdout
    if '@' in out.replace('@', '', 0) and re.search(r'@[A-Z]+@', out):
        bad += 1; print('%s còn chỗ giữ chỗ chưa thay' % f)
    if f.name.endswith('.plist.in'):
        plistlib.loads(out.encode())                              # valid XML plist even with '&' and spaces in the path
sys.exit(1 if bad else 0)
PY
  say "lint: compose.yaml hợp lệ"
  N8N_ENCRYPTION_KEY=lint TRENDVN_TOKEN=lint docker compose config -q
  info "lint OK"
}

unit() { say "unit: test trên máy này"; python3 -m unittest discover -s tests -t .; }

container() {
  need_docker
  say "container: build image worker"
  # building needs no secrets, but compose insists the variables exist: use placeholders so tests run before ./trendvn install
  N8N_ENCRYPTION_KEY="${N8N_ENCRYPTION_KEY:-test}" TRENDVN_TOKEN="${TRENDVN_TOKEN:-test}" compose build worker
  local img="trendvn/worker:$TRENDVN_VERSION"
  say "container: bộ test đầy đủ trong image (có ffmpeg)"
  docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT:/p:ro" -w /p -e PYTHONDONTWRITEBYTECODE=1 "$img" python -m unittest discover -s tests -t .
  say "container: dựng video thật bằng ffmpeg"
  docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT/tests/e2e:/t:ro" -e PYTHONDONTWRITEBYTECODE=1 "$img" python /t/render_check.py
}

e2e() {
  [ -x .venv/bin/python ] || fail "Chưa có .venv. Chạy: ./trendvn agent venv"
  say "e2e: Chrome thật"
  .venv/bin/python tests/e2e/ui_e2e.py "$@"
}

what="${1:-default}"; [ $# -gt 0 ] && shift
case "$what" in
  default) lint; unit ;;
  lint) lint ;; unit) unit ;; container) container ;; e2e) e2e "$@" ;;
  all) lint; unit; container; e2e ;;
  *) sed -n '2,7p' "$0"; exit 2 ;;
esac
