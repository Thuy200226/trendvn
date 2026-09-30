#!/bin/bash
# Nhấp đúp: mở cửa sổ Chrome để bạn tự đăng nhập TikTok (một lần). Hệ thống không nhập mật khẩu thay bạn.
cd "$(dirname "$0")/.." || exit 1
./trendvn tiktok login 15
read -r -p "Nhấn Enter để đóng cửa sổ này."
