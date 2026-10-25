#!/bin/bash
# Double click: opens a Chrome window to log yourself into TikTok (once). The system does not enter the password for you.
cd "$(dirname "$0")/.." || exit 1
./trendvn tiktok login 15
read -r -p "Nh"$'\341\272\245'"n Enter "$'\304\221'""$'\341\273\203'" "$'\304\221'""$'\303\263'"ng c"$'\341\273\255'"a s"$'\341\273\225'" n"$'\303\240'"y."
