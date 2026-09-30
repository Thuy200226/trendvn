#!/bin/bash
# Nhấp đúp file này trong Finder để cài TrendVN trên máy Mac (mở Terminal và chạy ./trendvn install).
cd "$(dirname "$0")/.." || exit 1
./trendvn install "$@"
echo
read -r -p "Xong. Nhấn Enter để đóng cửa sổ này."
