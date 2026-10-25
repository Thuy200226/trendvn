#!/usr/bin/env bash
# Reformat Python code (black) and fix safe lint (ruff): ./trendvn fmt
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"
run() { if have "$1"; then "$@"; else python3 -m "$@"; fi; }
{ have black || python3 -m black --version >/dev/null 2>&1; } || fail "Ch"$'\306\260'"a c"$'\303\263'" black/ruff: python3 -m pip install -r requirements-dev.txt"
run black -q services scripts n8n tests
run ruff check --fix --no-cache -q . || true
info ""$'\304\220'""$'\303\243'" "$'\304\221'""$'\341\273\213'"nh d"$'\341\272\241'"ng. Ki"$'\341\273\203'"m tra: ./trendvn test lint"
