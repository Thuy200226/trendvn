#!/usr/bin/env bash
# Install TrendVN with one command for Linux and macOS (it's still safe to run multiple times):
#   ./trendvn install [--no-activate] [--no-service]
#   --no-activate loads workflow into n8n but does NOT enable automatic scheduling
#   --no-service does not install background services for the agent (run automatically: ./trendvn agent run)
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/lib.sh"

ACTIVATE=1; SERVICE=1
for a in "$@"; do case "$a" in
  --no-activate) ACTIVATE=0;; --no-service) SERVICE=0;;
  -h|--help) sed -n '2,5p' "$0"; exit 0;;
  *) echo "Tham s"$'\341\273\221'" l"$'\341\272\241'": $a"; exit 2;; esac; done

say "1/8 Ki"$'\341\273\203'"m tra "$'\304\221'"i"$'\341\273\201'"u ki"$'\341\273\207'"n ($OS)"
require_simple_path
check_prerequisites
df -Pk "$ROOT" | awk 'NR==2 && $4 < 4000000 {print "\033[1;33mC'$'\341\272\243''nh b'$'\303\241''o:\033[0m '$'\341\273\225'' '$'\304\221'''$'\304\251''a c'$'\303\262''n d'$'\306\260'''$'\341\273\233''i 4GB, image Docker c'$'\341\272\247''n kho'$'\341\272\243''ng 2GB."}'

say "2/8 T"$'\341\272\241'"o c"$'\341\272\245'"u h"$'\303\254'"nh v"$'\303\240'" b"$'\303\255'" m"$'\341\272\255'"t (kh"$'\303\264'"ng hi"$'\341\273\203'"n th"$'\341\273\213'")"
# A leftover n8n volume is encrypted with the key of the install that made it. A NEW random key would make n8n refuse to start, so
# refuse to invent one: the .env of that install (or a restore) has to come first.
if ! grep -qE '^N8N_ENCRYPTION_KEY=.' .env 2>/dev/null; then
  proj="${COMPOSE_PROJECT_NAME:-$(envval COMPOSE_PROJECT_NAME)}"; proj="${proj:-trendvn}"
  if docker volume inspect "${proj}_n8n_data" >/dev/null 2>&1; then
    fail "$(printf '%s\n' \
      ""$'\304\220'""$'\303\243'" c"$'\303\263'" volume n8n '${proj}_n8n_data' c"$'\341\273\247'"a m"$'\341\273\231'"t l"$'\341\272\247'"n c"$'\303\240'"i tr"$'\306\260'""$'\341\273\233'"c, nh"$'\306\260'"ng .env n"$'\303\240'"y ch"$'\306\260'"a c"$'\303\263'" N8N_ENCRYPTION_KEY. T"$'\341\272\241'"o kh"$'\303\263'"a m"$'\341\273\233'"i s"$'\341\272\275'" l"$'\303\240'"m n8n kh"$'\303\264'"ng "$'\304\221'""$'\341\273\215'"c "$'\304\221'""$'\306\260'""$'\341\273\243'"c d"$'\341\273\257'" li"$'\341\273\207'"u c"$'\305\251'"." \
      "  - Chuy"$'\341\273\203'"n t"$'\341\273\253'" b"$'\341\272\243'"n c"$'\305\251'": ch"$'\303\251'"p .env c"$'\341\273\247'"a b"$'\341\272\243'"n c"$'\305\251'" v"$'\303\240'"o "$'\304\221'""$'\303\242'"y r"$'\341\273\223'"i ch"$'\341\272\241'"y l"$'\341\272\241'"i (docs/DEPLOY.md, m"$'\341\273\245'"c 11)." \
      "  - C"$'\303\240'"i m"$'\341\273\233'"i ho"$'\303\240'"n to"$'\303\240'"n (B"$'\341\273\216'" d"$'\341\273\257'" li"$'\341\273\207'"u n8n c"$'\305\251'"): docker volume rm ${proj}_n8n_data"
    )"
  fi
fi
python3 scripts/setup_env.py

say "3/8 M"$'\303\264'"i tr"$'\306\260'""$'\341\273\235'"ng Python cho agent tr"$'\303\254'"nh duy"$'\341\273\207'"t"
bash scripts/agent.sh venv

say "4/8 Sinh workflow n8n t"$'\341\273\253'" m"$'\303\243'""
python3 n8n/build.py

say "5/8 D"$'\341\273\261'"ng v"$'\303\240'" ch"$'\341\272\241'"y container (n8n + worker)"
compose_up || fail "Container ch"$'\306\260'"a kh"$'\341\273\217'"e. Xem: ./trendvn logs"

say "6/8 N"$'\341\272\241'"p workflow v"$'\303\240'"o n8n"
python3 n8n/manage.py import

say "7/8 B"$'\341\272\255'"t l"$'\341\273\213'"ch t"$'\341\273\261'" "$'\304\221'""$'\341\273\231'"ng"
if [ "$ACTIVATE" = 1 ]; then
  python3 n8n/manage.py activate || echo "C"$'\303\263'" workflow ch"$'\306\260'"a b"$'\341\272\255'"t "$'\304\221'""$'\306\260'""$'\341\273\243'"c (xem tr"$'\303\252'"n). B"$'\341\272\255'"t tay trong giao di"$'\341\273\207'"n n8n."
else
  echo "B"$'\341\273\217'" qua (--no-activate). B"$'\341\272\255'"t sau b"$'\341\272\261'"ng: ./trendvn n8n activate"
fi

say "8/8 D"$'\341\273\213'"ch v"$'\341\273\245'" n"$'\341\273\201'"n cho agent tr"$'\303\254'"nh duy"$'\341\273\207'"t"
if [ "$SERVICE" = 1 ]; then bash scripts/agent.sh install
else echo "Kh"$'\303\264'"ng c"$'\303\240'"i d"$'\341\273\213'"ch v"$'\341\273\245'" n"$'\341\273\201'"n. Ch"$'\341\272\241'"y tay trong m"$'\341\273\231'"t terminal ri"$'\303\252'"ng:  ./trendvn agent run"; fi

sleep 4
python3 scripts/doctor.py || true
[ "${TRENDVN_MIGRATING:-}" = 1 ] && exit 0       # ./trendvn migrate prints its own ending: an already configured system has no "5 things left"
printf '%b\n' "$(cat <<MSG

Xong. 5 vi\0341\0273\0207c c\0303\0262n l\0341\0272\0241i, ch\0341\0273\0211 b\0341\0272\0241n l\0303\0240m \0304\0221\0306\0260\0341\0273\0243c:
  1. M\0341\0273\0237 b\0341\0272\0243ng \0304\0221i\0341\0273\0201u khi\0341\0273\0203n  http://localhost:$(worker_port)  (./trendvn open) → Th\0303\0252m → C\0303\0240i \0304\0221\0341\0272\0267t: nh\0341\0272\0255p kh\0303\0263a Gemini (https://aistudio.google.com/apikey), b\0341\0272\0255t "X\0341\0273\0255 l\0303\0275 video".
  2. C\0303\0240i \0304\0221\0341\0272\0267t → L\0341\0273\0213ch \0304\0221\0304\0203ng: \0304\0221\0341\0272\0267t "T\0303\0240i kho\0341\0272\0243n TikTok m\0341\0272\0267c \0304\0221\0341\0273\0213nh" l\0303\0240 k\0303\0252nh c\0341\0273\0247a b\0341\0272\0241n (l\0303\0272c m\0341\0273\0233i c\0303\0240i l\0303\0240 t\0303\0240i kho\0341\0272\0243n m\0341\0272\0253u; l\0303\0240m tr\0306\0260\0341\0273\0233c khi \0304\0221\0304\0203ng nh\0341\0272\0255p).
  3. \0304\0220\0304\0203ng nh\0341\0272\0255p TikTok m\0341\0273\0231t l\0341\0272\0247n (c\0341\0273\0255a s\0341\0273\0225 Chrome hi\0341\0273\0207n ra, b\0341\0272\0241n t\0341\0273\0261 nh\0341\0272\0255p):  ./trendvn tiktok login
  4. B\0341\0272\0245m "B\0341\0272\0257t \0304\0221\0341\0272\0247u" \0341\0273\0237 T\0341\0273\0225ng quan (l\0341\0272\0247n qu\0303\0251t \0304\0221\0341\0272\0247u ch\0341\0273\0211 ghi m\0341\0273\0221c; b\0341\0272\0245m l\0341\0272\0241i sau v\0303\0240i gi\0341\0273\0235) t\0341\0273\0233i khi tab \0304\0220\0304\0203ng b\0303\0240i c\0303\0263 video, r\0341\0273\0223i ch\0341\0272\0241y th\0341\0273\0255 kh\0303\0264ng \0304\0221\0304\0203ng th\0341\0272\0255t:
     ./trendvn tiktok dry-run   (\0341\0272\0243nh ch\0341\0273\0245p: data/worker/exports/; "idle" ngh\0304\0251a l\0303\0240 ch\0306\0260a c\0303\0263 video d\0341\0273\0261ng xong)
  5. B\0341\0272\0255t "T\0341\0273\0261 \0304\0221\0304\0203ng" tr\0303\0252n b\0341\0272\0243ng \0304\0221i\0341\0273\0201u khi\0341\0273\0203n khi \0304\0221\0303\0243 h\0303\0240i l\0303\0262ng.
n8n: http://localhost:$(n8n_port) (l\0341\0272\0247n \0304\0221\0341\0272\0247u t\0341\0272\0241o t\0303\0240i kho\0341\0272\0243n ch\0341\0273\0247). Mu\0341\0273\0221n c\0303\0263 TikTok/Instagram M\0341\0273\0271: \0304\0221\0341\0272\0267t TRENDVN_US_PROXY trong .env (docs/DEPLOY.md).
M\0341\0273\0215i l\0341\0273\0207nh: ./trendvn help · Ch\0341\0272\0251n \0304\0221o\0303\0241n: ./trendvn doctor · Xem log: ./trendvn logs -f
MSG
)"
