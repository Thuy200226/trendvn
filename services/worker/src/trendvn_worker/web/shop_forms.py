"""Locally entered creator API credentials; stored with restrictive permissions and never echoed into the page."""

import json
import os
import re

from .forms import Redirect


def connect(app, form, app_only=False):
    account = app.store.account(form.get("account", [""])[0])
    if not account:
        raise ValueError("Không có tài khoản này")
    credentials = {
        key: form.get(key, [""])[0].strip()
        for key in (("app_key", "app_secret") if app_only else ("app_key", "app_secret", "access_token"))
    }
    if any(not 5 <= len(v) <= 4096 or re.search(r"\s", v) for v in credentials.values()):
        raise ValueError("Nhập đủ App key, App secret và token nhà sáng tạo hợp lệ")
    folder = app.store.root / "creator_credentials"
    folder.mkdir(exist_ok=True, mode=0o700)
    path = folder / (account["id"] + ".json")
    # Create restrictive from the first byte, not chmod after a world-readable write.
    fd = os.open(path.with_suffix(".part"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(credentials, f)
    path.with_suffix(".part").replace(path)
    app.tasks.start("shop_authorize" if app_only else "shop_sync", account["id"])
    return Redirect("shop_saved", anchor="#search")


def sync(app, form):
    account = form.get("account", [""])[0]
    if not app.store.account(account):
        raise ValueError("Không có tài khoản này")
    app.tasks.start("shop_sync", account)
    return Redirect("started", anchor="#search")


def save_app(app, form):
    return connect(app, form, app_only=True)


def authorize(app, form):
    account = form.get("account", [""])[0]
    if not app.store.account(account):
        raise ValueError("Không có tài khoản này")
    app.tasks.start("shop_authorize", account)
    return Redirect("started", anchor="#search")
