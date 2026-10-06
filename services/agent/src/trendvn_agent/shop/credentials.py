"""Restricted atomic storage for creator app credentials and single-use authorization sessions."""

import json
import os
import re

from ..config import RUNTIME


def path_for(account, folder="creator_credentials"):
    if not isinstance(account, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,23}", account):
        raise ValueError("Mã tài khoản không hợp lệ")
    return RUNTIME / folder / (account + ".json")


def read(account, folder="creator_credentials"):
    path = path_for(account, folder)
    if not path.is_file() or path.is_symlink():
        raise ValueError("Chưa cấu hình kết nối nhà sáng tạo cho tài khoản này")
    if path.stat().st_mode & 0o077:
        raise ValueError("Tệp kết nối chưa được bảo vệ quyền đọc")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        raise ValueError("Tệp kết nối không hợp lệ; hãy kết nối lại") from None
    if not isinstance(data, dict):
        raise ValueError("Tệp kết nối không hợp lệ")
    return data


def write(account, data, folder="creator_credentials"):
    path = path_for(account, folder)
    path.parent.mkdir(exist_ok=True, mode=0o700)
    fd = os.open(path.with_suffix(".part"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle)
    path.with_suffix(".part").replace(path)
