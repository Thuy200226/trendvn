"""The password page shown to hosts other than this machine (only when TRENDVN_UI_PASSWORD is set)."""

from .format import escape as E
from .controls import input_control, button

LOGIN_PAGE = (
    '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrendVN · Đăng nhập</title>'
    "<style>body{font:16px system-ui;background:#0e1522;color:#e6ecf7;display:grid;place-items:center;min-height:100vh;margin:0}"
    "form{width:min(92vw,360px);background:#162033;padding:24px;border-radius:16px}"
    "input,button{width:100%;padding:12px;margin-top:12px;border-radius:10px;border:1px solid #2a3850;font:inherit;box-sizing:border-box}"
    "button{background:#5fd6bd;color:#08231d;font-weight:700;border:0}p{color:#ff8a80}</style>"
    '<form method="post" action="/login"><h2>TrendVN</h2><p>{message}</p>'
    + input_control("password", type="password", placeholder="Mật khẩu bảng điều khiển", autofocus=True, autocomplete="current-password")
    + button("Đăng nhập")
    + "</form></html>"
)


def login_page(message=""):
    return LOGIN_PAGE.replace("{message}", E(message))
