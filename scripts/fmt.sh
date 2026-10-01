#!/usr/bin/env bash
# Định dạng lại mã Python (black) và sửa lỗi lint an toàn (ruff):  ./trendvn fmt
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
run() { if have "$1"; then "$@"; else python3 -m "$@"; fi; }
{ have black || python3 -m black --version >/dev/null 2>&1; } || fail "Chưa có black/ruff: python3 -m pip install -r requirements-dev.txt"
run black -q services scripts n8n tests
run ruff check --fix --no-cache -q . || true
info "Đã định dạng. Kiểm tra: ./trendvn test lint"
