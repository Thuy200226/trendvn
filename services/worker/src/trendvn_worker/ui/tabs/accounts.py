"""TikTok accounts: which topics each account takes, its own limits, and how to sign in to it."""

from ...domain import topics
from ..components import chip, field, number_input, select, text_input
from ..format import escape as E, windows_text

NO_OVERRIDE = (
    ("", "D\u00f9ng c\u00e0i \u0111\u1eb7t chung"),
    ("public", "M\u1ecdi ng\u01b0\u1eddi (c\u00f4ng khai)"),
    ("friends", "B\u1ea1n b\u00e8"),
    ("self", "Ch\u1ec9 m\u00ecnh t\u00f4i"),
)


def _toggles(chosen):
    """One big tap target per topic: a checkbox stretched over its label."""
    return '<div class="toggles">%s</div>' % "".join(
        '<label class="tg"><input type="checkbox" name="topic" value="%s"%s><span>%s</span></label>'
        % (t.id, " checked" if t.id in chosen else "", E(t.vi))
        for t in topics.TOPICS
    )


def _login_chip(account):
    state = account["logged_in"]
    if state is True:
        return chip("\u0111\u00e3 \u0111\u0103ng nh\u1eadp TikTok", "good")
    if state is False:
        return chip("ch\u01b0a \u0111\u0103ng nh\u1eadp TikTok", "warn")
    return chip("ch\u01b0a ki\u1ec3m tra \u0111\u0103ng nh\u1eadp", "mute")


def _login_hint(account):
    command = "./trendvn tiktok login" + ("" if account["id"] == "main" else " --account " + account["id"])
    return (
        '<p class="small muted">\u0110\u0103ng nh\u1eadp m\u1ed9t l\u1ea7n: ch\u1ea1y <code>%s</code> r\u1ed3i t\u1ef1 \u0111\u0103ng nh\u1eadp trong c\u1eeda s\u1ed5 Chrome hi\u1ec7n ra.</p>'
        % E(command)
    )


def _overrides(account):
    own = account["own"]
    return "".join(
        (
            field(
                "S\u1ed1 b\u00e0i t\u1ed1i \u0111a m\u1ed7i ng\u00e0y",
                number_input("daily_limit", own["daily_limit"] if own["daily_limit"] is not None else "", 1, 10),
                "\u0110\u1ec3 tr\u1ed1ng = d\u00f9ng s\u1ed1 chung (%d)." % account["daily_limit"] if own["daily_limit"] is None else "",
            ),
            field(
                "Gi\u00e3n c\u00e1ch t\u1ed1i thi\u1ec3u (gi\u1edd)",
                number_input("gap_hours", round(own["min_gap"] / 3600, 2) if own["min_gap"] is not None else "", 0, 24, "0.25"),
            ),
            field(
                "Gi\u1edd v\u00e0ng (gi\u1edd Vi\u1ec7t Nam)",
                text_input(
                    "post_windows", windows_text(own["windows"]) if own["windows"] is not None else "", 'placeholder="11-14, 19-23"'
                ),
                "\u0110\u1ec3 tr\u1ed1ng = d\u00f9ng gi\u1edd v\u00e0ng chung.",
            ),
            field("Ch\u1ebf \u0111\u1ed9 hi\u1ec3n th\u1ecb", select("visibility", own["visibility"] or "", NO_OVERRIDE)),
        )
    )


def _card(view, account):
    state = chip("\u0111ang b\u1eadt", "good") if account["enabled"] else chip("\u0111ang t\u1eaft", "mute")
    today = chip("h\u00f4m nay %d/%d" % (account["published_today"], account["daily_limit"]), "info")
    enabled = select("enabled", "true" if account["enabled"] else "false", (("true", "B\u1eadt"), ("false", "T\u1eaft")))
    return (
        '<form method="post" action="/account-save" class="card stack acct"><input type="hidden" name="csrf" value="%(csrf)s">'
        '<input type="hidden" name="id" value="%(id)s">'
        '<div class="row"><h3>@%(user)s</h3><div class="facts">%(state)s%(login)s%(today)s</div></div>'
        '<p class="small muted">Nh\u1eadn c\u00e1c ch\u1ee7 \u0111\u1ec1:</p>%(toggles)s%(hint)s'
        '<details class="fs"><summary>T\u00ean g\u1ecdi, b\u1eadt/t\u1eaft v\u00e0 gi\u1edbi h\u1ea1n ri\u00eang</summary><div class="fsbody">%(label)s%(enabled)s%(overrides)s</div></details>'
        '<div class="btns two"><button class="go">L\u01b0u t\u00e0i kho\u1ea3n</button>'
        '<button class="ghost danger" formaction="/account-delete" data-confirm="X\u00f3a @%(user)s kh\u1ecfi danh s\u00e1ch? C\u00e1c b\u00e0i \u0111\u00e3 \u0111\u0103ng v\u1eabn gi\u1eef nguy\u00ean.">X\u00f3a</button></div></form>'
    ) % {
        "csrf": view.csrf,
        "id": E(account["id"]),
        "user": E(account["username"]),
        "state": state,
        "login": _login_chip(account),
        "today": today,
        "toggles": _toggles(account["topics"]),
        "hint": _login_hint(account),
        "label": field(
            "T\u00ean g\u1ecdi (ch\u1ec9 \u0111\u1ec3 b\u1ea1n nh\u00ecn)", text_input("label", account["label"] or "", 'maxlength="40"')
        ),
        "enabled": field("Tr\u1ea1ng th\u00e1i", enabled),
        "overrides": _overrides(account),
    }


def _add_form(view):
    return (
        '<form method="post" action="/account-add" class="card stack"><input type="hidden" name="csrf" value="%s"><h3>Th\u00eam t\u00e0i kho\u1ea3n</h3>%s'
        '<p class="small muted">Ch\u1ecdn c\u00e1c ch\u1ee7 \u0111\u1ec1 t\u00e0i kho\u1ea3n n\u00e0y nh\u1eadn:</p>%s<div class="btns"><button class="go">Th\u00eam t\u00e0i kho\u1ea3n</button></div></form>'
    ) % (
        view.csrf,
        field(
            "T\u00ean ng\u01b0\u1eddi d\u00f9ng TikTok",
            text_input("username", "", 'placeholder="ten_kenh" autocomplete="off" autocapitalize="off"'),
        ),
        _toggles(()),
    )


def render(view):
    accounts = view.d["accounts"]
    wanted = [topics.label(t) for t in view.d["wanted_topics"]]
    intro = (
        '<p class="hint">M\u1ed7i t\u00e0i kho\u1ea3n nh\u1eadn m\u1ed9t s\u1ed1 ch\u1ee7 \u0111\u1ec1. H\u1ec7 th\u1ed1ng ch\u1ec9 t\u00ecm video thu\u1ed9c ch\u1ee7 \u0111\u1ec1 c\u00f3 t\u00e0i kho\u1ea3n nh\u1eadn (%s) v\u00e0 \u0111\u0103ng m\u1ed7i video l\u00ean '
        "\u0111\u00fang t\u00e0i kho\u1ea3n nh\u1eadn ch\u1ee7 \u0111\u1ec1 \u0111\u00f3, theo gi\u1edbi h\u1ea1n ng\u00e0y, gi\u00e3n c\u00e1ch v\u00e0 gi\u1edd v\u00e0ng c\u1ee7a ch\u00ednh t\u00e0i kho\u1ea3n.</p>"
    ) % E(", ".join(wanted) or "ch\u01b0a c\u00f3")
    return intro + "".join(_card(view, a) for a in accounts) + _add_form(view)
