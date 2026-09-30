#!/usr/bin/env bash
# Chuyển hệ thống đang chạy từ THƯ MỤC CŨ (bản 1.2) sang thư mục này:   ./trendvn migrate <thư-mục-cũ> [--yes] [--no-service]
#
# Việc nó làm, theo thứ tự (dừng ngay nếu một bước kiểm tra không đạt, trước khi dừng bất cứ thứ gì):
#   1. kiểm tra thư mục cũ, việc đang chạy, thư mục này còn trống (chưa có .env)
#   2. sao lưu bằng backup.sh của thư mục cũ và kiểm tra bản sao lưu
#   3. dừng agent và container của thư mục cũ (giữ nguyên dữ liệu và volume n8n)
#   4. chép .env, dữ liệu (runtime/ -> data/worker, agent_data/ -> data/agent, bỏ bộ nhớ đệm Chrome) sang đây
#   5. ./trendvn install --no-activate  (lịch n8n đang bật vẫn bật, đang tắt vẫn tắt; "Tự đăng" giữ nguyên)
#   6. đối chiếu số video theo trạng thái giữa dữ liệu cũ và hệ thống mới
# Thư mục cũ được GIỮ NGUYÊN làm bản dự phòng; đừng chạy nó cùng lúc (cùng tên project Docker).
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"

YES=0; OLD=""; NOSERVICE=""
for a in "$@"; do case "$a" in --yes) YES=1;; --no-service) NOSERVICE="--no-service";; -h|--help) sed -n '2,12p' "$0"; exit 0;; -*) fail "Tham số lạ: $a";; *) OLD="$a";; esac; done
[ -n "$OLD" ] && [ -d "$OLD" ] || { sed -n '2,3p' "$0"; exit 2; }
OLD="$(cd "$OLD" && pwd)"

# ---------------------------------------------------------------- 1. checks (nothing is stopped yet)
[ "$OLD" != "$ROOT" ] || fail "Thư mục cũ và thư mục mới là một."
{ [ -f "$OLD/compose.yaml" ] && [ -f "$OLD/.env" ] && [ -d "$OLD/runtime" ]; } || fail "$OLD không giống thư mục TrendVN 1.2 (cần compose.yaml, .env và runtime/)."
[ ! -f "$ROOT/.env" ] || fail "Thư mục này đã có .env (đã cài rồi). migrate chỉ dùng cho thư mục mới giải nén, chưa cài."
[ ! -s "$ROOT/data/worker/trendvn.sqlite3" ] || fail "Thư mục này đã có dữ liệu (data/worker/trendvn.sqlite3)."
have rsync || fail "Cần rsync (Mac và Linux đều có sẵn)."
require_simple_path
check_prerequisites        # everything install will need, checked now, while the old system is still running

OLDPROJ="$(cd "$OLD" && docker compose config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')" \
  || fail "Không đọc được cấu hình Docker của $OLD."
echo "Thư mục cũ : $OLD  (project Docker '$OLDPROJ')"
echo "Thư mục mới: $ROOT"

# a task that is running right now (processing, posting...) must finish first
OLDINFO="$(python3 scripts/migrate_tools.py info "$OLD/.env")"
OLDTOKEN="${OLDINFO%% *}"; OLDPORT="${OLDINFO##* }"
RUNNING="$(python3 scripts/migrate_tools.py tasks "$OLDPORT" "$OLDTOKEN")"
case "$RUNNING" in
  0) echo "Worker cũ đang rảnh." ;;
  unreachable) warn "Worker cũ không trả lời (đang tắt?). Vẫn tiếp tục nếu bạn đồng ý." ;;
  *) fail "Worker cũ đang chạy $RUNNING việc (xử lý/đăng...). Đợi chúng xong rồi chạy lại." ;;
esac

if [ "$YES" != 1 ]; then
  echo
  echo "Sẽ: sao lưu, DỪNG agent và container ở thư mục cũ (mất dịch vụ vài phút), rồi cài lại từ thư mục này với cùng dữ liệu."
  echo "Lịch tự động và \"Tự đăng\" giữ nguyên trạng thái hiện tại. Thư mục cũ được giữ làm dự phòng."
  read -r -p "Gõ 'chuyen' để bắt đầu: " ans; [ "$ans" = "chuyen" ] || { echo "Đã hủy. Chưa thay đổi gì."; exit 1; }
fi

# ---------------------------------------------------------------- 2. backup
say "1/5 Sao lưu thư mục cũ"
if [ -x "$OLD/backup.sh" ]; then (cd "$OLD" && ./backup.sh); else warn "Không thấy backup.sh ở thư mục cũ: bỏ qua sao lưu (dữ liệu vẫn còn nguyên ở đó)."; fi
# names are ours (trendvn-YYYYMMDD-HHMMSS.tar.gz), so parsing ls is safe here
# shellcheck disable=SC2012
LATEST="$(ls -1t "$OLD"/backups/trendvn-*.tar.gz 2>/dev/null | head -1 || true)"
if [ -n "$LATEST" ]; then
  tar tzf "$LATEST" >/dev/null 2>&1 || fail "Bản sao lưu $LATEST không đọc được; dừng, chưa dừng gì."
  echo "Bản sao lưu: $LATEST"
fi

# ---------------------------------------------------------------- 3. stop the old stack (from here on, print the way back if anything fails)
STOPPED=0
rollback_help() {
  local code=$?
  if [ "$STOPPED" = 1 ] && [ "$code" != 0 ]; then
    {
      printf '\n\033[1;31mChuyển chưa xong (mã %s).\033[0m Đường lui về thư mục cũ, dữ liệu ở đó vẫn nguyên:\n' "$code"
      echo "  cd \"$ROOT\" && ./trendvn down; ./trendvn agent stop"
      [ -f "$ROOT/data/backups/agent-service.before-migrate" ] && echo "  (Linux) cp \"$ROOT/data/backups/agent-service.before-migrate\" ~/.config/systemd/user/trendvn-agent.service && systemctl --user daemon-reload && systemctl --user start trendvn-agent"
      echo "  cd \"$OLD\" && docker compose up -d"
    } >&2
  fi
}
trap rollback_help EXIT

say "2/5 Dừng agent và container của thư mục cũ"
mkdir -p "$ROOT/data/backups"
# only the service that runs THIS old folder: match its working directory exactly
UNIT="$HOME/.config/systemd/user/trendvn-agent.service"; PLIST="$HOME/Library/LaunchAgents/vn.trendvn.agent.plist"
if [ "$OS" = Darwin ]; then
  if [ -f "$PLIST" ] && grep -qF "<string>$OLD</string>" "$PLIST"; then
    cp "$PLIST" "$ROOT/data/backups/agent-service.before-migrate"; STOPPED=1
    launchctl bootout "gui/$(id -u)/vn.trendvn.agent" >/dev/null 2>&1 || true; echo "Đã dừng agent cũ (launchd)."
  fi
elif [ -f "$UNIT" ] && grep -qxF "WorkingDirectory=$OLD" "$UNIT"; then
  cp "$UNIT" "$ROOT/data/backups/agent-service.before-migrate"; STOPPED=1
  systemctl --user stop trendvn-agent.service && echo "Đã dừng agent cũ (systemd)."
fi
STOPPED=1
(cd "$OLD" && docker compose down)

# ---------------------------------------------------------------- 4. copy config and data
say "3/5 Chép cấu hình và dữ liệu"
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
echo "Đã chép: $(du -sh data/worker | cut -f1) dữ liệu worker, $(du -sh data/agent | cut -f1) hồ sơ trình duyệt."

# ---------------------------------------------------------------- 5. install here
say "4/5 Cài đặt từ thư mục này"
# NOSERVICE is empty or a single flag, so word splitting is intended
# shellcheck disable=SC2086
TRENDVN_MIGRATING=1 bash scripts/install.sh --no-activate $NOSERVICE

# ---------------------------------------------------------------- 6. compare
say "5/5 Đối chiếu dữ liệu"
python3 scripts/migrate_tools.py compare "$ROOT" "$(worker_port)" "$(envval TRENDVN_TOKEN)"
STOPPED=0
echo
echo "Xong. Hệ thống chạy từ: $ROOT"
echo "Thư mục cũ ($OLD) được giữ làm dự phòng. KHÔNG chạy nó cùng lúc (cùng tên project Docker). Khi đã chắc chắn, xóa hoặc nén nó lại."
echo "Kiểm tra: ./trendvn status · ./trendvn doctor"
