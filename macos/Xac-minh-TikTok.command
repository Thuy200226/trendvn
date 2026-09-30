#!/bin/bash
# Nhấp đúp: mở cửa sổ Chrome để bạn giải hình xác minh của TikTok (một lần). Không tải gì lên, không đăng gì.
cd "$(dirname "$0")/.." || exit 1
./trendvn tiktok trust 20
read -r -p "Nhấn Enter để đóng cửa sổ này."
