#!/bin/bash
# Double click: opens the TrendVN dashboard in the browser.
cd "$(dirname "$0")/.." || exit 1
./trendvn open
