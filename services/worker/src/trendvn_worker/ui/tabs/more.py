"""Adds: accounts, sources, settings, phone notifications, the event log and the manual-import box."""

import json

from ...domain.platforms import REGISTRY

from ..components import (
    PLAIN_INPUT,
    accordion,
    cell,
    chip,
    field,
    fieldset,
    number_input,
    select,
    switch_select,
    table,
    text_input,
)
from ..format import ago, escape as E, windows_text
from . import accounts
from ..labels import EVENT_LABELS, PLATFORM, STATE_LABELS, vi_reason


def sources(view):
    """One card per platform: when it was last scanned, what its jobs look like, what the collector last said."""
    d = view.d
    detail = d.get("discovery_detail") if isinstance(d.get("discovery_detail"), dict) else {}
    last_scan = {}
    for stream in d["streams"]:
        platform = stream["name"].split(":")[0]
        last_scan[platform] = max(last_scan.get(platform, 0), stream["last_scan"] or 0)
    cards = []
    for platform, (name, country) in PLATFORM.items():
        states = d["by_platform"].get(platform, {})
        info = detail.get(platform)
        text = info if isinstance(info, str) else (json.dumps(info, ensure_ascii=False) if info else "")
        skipped = isinstance(info, str) and "IP" in info
        tone = "warn" if skipped else ("good" if last_scan.get(platform) else "mute")
        label = "C\u1ea7n IP %s" % country if skipped else ("\u0110ang thu th\u1eadp" if last_scan.get(platform) else "Ch\u01b0a qu\u00e9t")
        counts = (
            " ".join("<span>%s <b>%d</b></span>" % (E(STATE_LABELS.get(k, k)), n) for k, n in sorted(states.items()))
            or "Ch\u01b0a c\u00f3 d\u1eef li\u1ec7u"
        )
        cards.append(
            '<div class="card src"><div class="row"><h3>%s</h3>%s</div><p class="muted">Qu\u00e9t g\u1ea7n nh\u1ea5t: <b>%s</b></p>'
            '<div class="mini">%s</div><small class="muted">%s</small><small>Tr\u1ecdng s\u1ed1 \u01b0u ti\u00ean: <b>%.2f</b></small></div>'
            % (E(name), chip(label, tone), ago(last_scan.get(platform), view.now), counts, E(text[:260]), d["weights"].get(platform, 1.0))
        )
    return '<div class="grid4">%s</div>' % "".join(cards)


def _automation_group(view):
    d, cfg = view.d, view.cfg
    return fieldset(
        "T\u1ef1 \u0111\u1ed9ng",
        "".join(
            (
                field(
                    "X\u1eed l\u00fd video b\u1eb1ng Gemini",
                    switch_select("processing_enabled", d["processing_enabled"], "B\u1eadt", "T\u1eaft"),
                ),
                field(
                    "T\u1ef1 \u0111\u0103ng l\u00ean TikTok",
                    switch_select("publisher_enabled", d["publisher_enabled"], "B\u1eadt", "T\u1eaft"),
                    "Lu\u00f4n ki\u1ec3m tra hash, tr\u00f9ng l\u1eb7p v\u00e0 gi\u1edbi h\u1ea1n ng\u00e0y.",
                ),
                field(
                    "Duy\u1ec7t tay tr\u01b0\u1edbc khi \u0111\u0103ng",
                    switch_select(
                        "require_approval",
                        cfg["require_approval"],
                        "B\u1eadt — ch\u1edd t\u00f4i duy\u1ec7t",
                        "T\u1eaft — ho\u00e0n to\u00e0n t\u1ef1 \u0111\u1ed9ng",
                    ),
                ),
                field(
                    "L\u1ed3ng ti\u1ebfng Vi\u1ec7t",
                    switch_select(
                        "voiceover_enabled",
                        cfg["voiceover_enabled"],
                        "B\u1eadt — \u01b0u ti\u00ean khi ph\u00f9 h\u1ee3p",
                        "T\u1eaft — ch\u1ec9 Vietsub",
                    ),
                    "H\u00e3y nghe th\u1eed gi\u1ecdng \u0111\u1ecdc tr\u01b0\u1edbc khi b\u1eadt.",
                ),
                field(
                    "L\u1ed3ng ti\u1ebfng cho",
                    select(
                        "voiceover_scope",
                        cfg["voiceover_scope"],
                        (
                            (
                                "monologue",
                                "Thuy\u1ebft minh v\u00e0 m\u1ed9t ng\u01b0\u1eddi n\u00f3i (khi thay gi\u1ecdng kh\u00f4ng m\u1ea5t g\u00ec)",
                            ),
                            ("narration", "Ch\u1ec9 video thuy\u1ebft minh"),
                        ),
                    ),
                    "H\u00e0i, k\u1ecbch, tranh c\u00e3i, nhi\u1ec1u ng\u01b0\u1eddi n\u00f3i lu\u00f4n gi\u1eef gi\u1ecdng g\u1ed1c k\u00e8m Vietsub.",
                ),
                field(
                    "L\u00e0m m\u1edd ph\u1ee5 \u0111\u1ec1 g\u1ed1c",
                    select(
                        "hard_sub_mask",
                        cfg["hard_sub_mask"],
                        (
                            (
                                "auto",
                                "T\u1ef1 \u0111\u1ed9ng: ch\u1ec9 khi ph\u1ee5 \u0111\u1ec1 Vi\u1ec7t s\u1ebd \u0111\u00e8 l\u00ean ch\u1eef g\u1ed1c",
                            ),
                            ("always", "Lu\u00f4n l\u00e0m m\u1edd khi c\u00f3 ph\u1ee5 \u0111\u1ec1 Vi\u1ec7t"),
                            ("off", "Kh\u00f4ng bao gi\u1edd l\u00e0m m\u1edd"),
                        ),
                    ),
                    "Ch\u1ec9 m\u1edd \u0111\u00fang l\u00fac ph\u1ee5 \u0111\u1ec1 Vi\u1ec7t hi\u1ec7n, kh\u00f4ng bao gi\u1edd c\u1ea3 video.",
                ),
            )
        ),
    )


def _schedule_group(view):
    cfg = view.cfg
    visibility = (
        ("public", "M\u1ecdi ng\u01b0\u1eddi (c\u00f4ng khai)"),
        ("friends", "B\u1ea1n b\u00e8"),
        ("self", "Ch\u1ec9 m\u00ecnh t\u00f4i (d\u00f9ng \u0111\u1ec3 ch\u1ea1y th\u1eed an to\u00e0n)"),
    )
    return fieldset(
        "L\u1ecbch \u0111\u0103ng",
        "".join(
            (
                field("S\u1ed1 b\u00e0i t\u1ed1i \u0111a m\u1ed7i ng\u00e0y", number_input("daily_limit", cfg["daily_limit"], 1, 10)),
                field(
                    "Gi\u00e3n c\u00e1ch t\u1ed1i thi\u1ec3u (gi\u1edd)",
                    number_input("gap_hours", round(cfg["min_publish_gap"] / 3600, 2), 0, 24, "0.25"),
                ),
                field(
                    "Gi\u1edd v\u00e0ng (gi\u1edd Vi\u1ec7t Nam)",
                    text_input("post_windows", windows_text(cfg["post_windows"]), 'placeholder="11-14, 19-23" inputmode="text"'),
                    "\u0110\u1ec3 tr\u1ed1ng n\u1ebfu mu\u1ed1n \u0111\u0103ng b\u1ea5t k\u1ef3 l\u00fac n\u00e0o.",
                ),
                field(
                    "T\u00e0i kho\u1ea3n TikTok m\u1eb7c \u0111\u1ecbnh",
                    text_input("target", cfg["target"], PLAIN_INPUT),
                    "Th\u00eam t\u00e0i kho\u1ea3n kh\u00e1c \u1edf m\u1ee5c T\u00e0i kho\u1ea3n TikTok v\u00e0 ch\u1ee7 \u0111\u1ec1.",
                ),
                field(
                    "Ch\u1ebf \u0111\u1ed9 hi\u1ec3n th\u1ecb b\u00e0i \u0111\u0103ng",
                    select("visibility", cfg["visibility"], visibility),
                    "\u00c1p d\u1ee5ng cho m\u1ecdi b\u00e0i s\u1eafp \u0111\u0103ng.",
                ),
            )
        ),
        False,
    )


def _selection_group(view):
    cfg = view.cfg
    return fieldset(
        "Ch\u1ecdn video",
        "".join(
            (
                field(
                    "Video m\u1edbi trong (ng\u00e0y)",
                    number_input("max_age_days", cfg["max_age_days"], 1, 60),
                    "Ch\u1ec9 l\u1ea5y video \u0111\u01b0\u1ee3c \u0111\u0103ng g\u1ea7n \u0111\u00e2y.",
                ),
                field("\u0110\u1ed9 d\u00e0i t\u1ed1i \u0111a (gi\u00e2y)", number_input("max_duration", cfg["max_duration"], 10, 600)),
                field(
                    "T\u1ea3i t\u1ed1i \u0111a m\u1ed7i l\u1ea7n qu\u00e9t",
                    number_input("max_candidates_per_scan", cfg["max_candidates_per_scan"], 1, 10),
                ),
                field(
                    "H\u00e0ng ch\u1edd t\u1ed1i \u0111a",
                    number_input("max_backlog", cfg["max_backlog"], 1, 20),
                    "\u0110\u1ee7 s\u1ed1 n\u00e0y th\u00ec t\u1ea1m ng\u1eebng t\u1ea3i th\u00eam.",
                ),
                field(
                    "\u0110\u1ed9 ch\u1eafc ch\u1eafn t\u1ed1i thi\u1ec3u c\u1ee7a Gemini",
                    number_input("audio_confidence", cfg["audio_confidence"], 0.5, 0.99, "0.01"),
                ),
            )
        ),
        False,
    )


def _threshold_group(view):
    min_views, min_likes = view.cfg["min_views"], view.cfg["min_likes"]
    return fieldset(
        "Ng\u01b0\u1ee1ng th\u1ecbnh h\u00e0nh",
        "".join(
            (
                field("Douyin: tim t\u1ed1i thi\u1ec3u", number_input("likes_douyin", min_likes.get("douyin", 0), 0, 10**9)),
                *(  # one views threshold per registered platform (domain/platforms.py)
                    field(
                        "%s: l\u01b0\u1ee3t xem t\u1ed1i thi\u1ec3u" % platform.name,
                        number_input("views_" + platform.id, min_views.get(platform.id, 0), 0, 10**10),
                    )
                    for platform in REGISTRY
                ),
            )
        ),
        False,
    )


def _gemini_group(view):
    cfg = view.cfg
    return fieldset(
        "Gemini",
        "".join(
            (
                field(
                    "Ch\u1ecdn gi\u1ecdng \u0111\u1ecdc",
                    select(
                        "voice_mode",
                        cfg["voice_mode"],
                        (
                            ("auto", "T\u1ef1 \u0111\u1ed9ng theo ng\u01b0\u1eddi n\u00f3i (nam/n\u1eef, s\u1eafc th\u00e1i)"),
                            ("fixed", "Lu\u00f4n d\u00f9ng gi\u1ecdng b\u00ean d\u01b0\u1edbi"),
                        ),
                    ),
                ),
                field(
                    "Gi\u1ecdng c\u1ed1 \u0111\u1ecbnh",
                    text_input("voice", cfg["voice"], PLAIN_INPUT),
                    "T\u00ean gi\u1ecdng Gemini, v\u00ed d\u1ee5 Kore, Puck, Charon.",
                ),
                field(
                    "H\u1ea1n m\u1ee9c g\u1ecdi Gemini / 24 gi\u1edd",
                    number_input("gemini_daily_limit", cfg["gemini_daily_limit"], 1, 500),
                    "T\u0103ng n\u1ebfu t\u00e0i kho\u1ea3n Gemini c\u1ee7a b\u1ea1n cho ph\u00e9p.",
                ),
                field(
                    "Model ph\u00e2n t\u00edch",
                    text_input("model", cfg["model"], PLAIN_INPUT),
                    "Google c\u00f3 th\u1ec3 ng\u1eebng model c\u0169; h\u1ec7 th\u1ed1ng t\u1ef1 chuy\u1ec3n sang model m\u1edbi h\u01a1n khi g\u1eb7p l\u1ed7i 404.",
                ),
                field("Model gi\u1ecdng \u0111\u1ecdc", text_input("tts_model", cfg["tts_model"], PLAIN_INPUT)),
                field(
                    "Ki\u1ec3u m\u00f4 t\u1ea3 b\u00e0i \u0111\u0103ng",
                    select(
                        "caption_style",
                        cfg["caption_style"],
                        (
                            ("hook", "Gi\u1eadt t\u00edt, k\u00edch th\u00edch t\u00f2 m\u00f2"),
                            ("factual", "\u0110i\u1ec1m \u0111\u1ea1m, m\u00f4 t\u1ea3 \u0111\u00fang n\u1ed9i dung"),
                        ),
                    ),
                    "Gi\u1eadt t\u00edt v\u1eabn b\u00e1m \u0111\u00fang \u0111i\u1ec1u c\u00f3 trong video, kh\u00f4ng b\u1ecba s\u1ef1 ki\u1ec7n hay l\u1eddi c\u1ee7a ng\u01b0\u1eddi th\u1eadt.",
                ),
            )
        ),
        False,
    )


def settings_form(view):
    groups = (_automation_group(view), _schedule_group(view), _selection_group(view), _threshold_group(view), _gemini_group(view))
    return (
        '<form method="post" action="/settings" class="settings stack"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="settings">%s'
        '<div class="btns"><button class="go">L\u01b0u c\u00e0i \u0111\u1eb7t</button></div></form>'
    ) % (view.csrf, "".join(groups))


def gemini_key_form(view):
    d = view.d
    audio = '<audio controls preload="none" src="/media/voice-sample"></audio>' if d.get("voice_sample") else ""
    return (
        '<form method="post" action="/setup" class="stack"><input type="hidden" name="csrf" value="%s">'
        '<p class="muted">Kh\u00f3a \u0111\u01b0\u1ee3c l\u01b0u trong <code>data/worker/gemini.key</code>, kh\u00f4ng g\u1eedi v\u00e0o n8n hay nh\u1eadt k\u00fd. %s</p>'
        '%s<div class="btns"><button class="go">L\u01b0u kh\u00f3a</button></div></form>'
        '<form method="post" action="/voice-test"><input type="hidden" name="csrf" value="%s"><div class="btns">'
        '<button class="ghost" title="D\u00f9ng 1 l\u01b0\u1ee3t g\u1ecdi Gemini">🔊 Nghe th\u1eed gi\u1ecdng \u0111\u1ecdc</button></div></form>%s'
    ) % (
        view.csrf,
        "\u0110\u00e3 c\u00f3 kh\u00f3a." if d["gemini_configured"] else "Ch\u01b0a c\u00f3 kh\u00f3a.",
        field(
            "Gemini API key (\u0111\u1ec3 tr\u1ed1ng \u0111\u1ec3 gi\u1eef kh\u00f3a hi\u1ec7n t\u1ea1i)",
            '<input type="password" name="key" autocomplete="off">',
        ),
        view.csrf,
        audio,
    )


def notify_form(view):
    telegram = field(
        "Bot token",
        '<input type="password" name="telegram_token" autocomplete="off" placeholder="\u0111\u1ec3 tr\u1ed1ng \u0111\u1ec3 gi\u1eef nguy\u00ean">',
    ) + field("Chat id", '<input name="telegram_chat" autocomplete="off" inputmode="text" placeholder="-100123456 ho\u1eb7c @kenh">')
    return (
        '<p class="muted">K\u00eanh \u0111ang d\u00f9ng: <b>%s</b>. Th\u00f4ng b\u00e1o g\u1eedi khi c\u00f3 video c\u1ea7n duy\u1ec7t, \u0111\u0103ng xong, l\u1ed7i ho\u1eb7c b\u00e0i ch\u01b0a x\u00e1c nh\u1eadn.</p>'
        '<form method="post" action="/notify-save" class="stack"><input type="hidden" name="csrf" value="%s">%s%s%s'
        '<div class="btns"><button class="go">L\u01b0u k\u00eanh th\u00f4ng b\u00e1o</button></div></form>'
        '<div class="btns two"><form method="post" action="/notify-test"><input type="hidden" name="csrf" value="%s"><button class="ghost">G\u1eedi tin th\u1eed</button></form>'
        '<form method="post" action="/notify-clear"><input type="hidden" name="csrf" value="%s"><button class="ghost">X\u00f3a c\u00e1c k\u00eanh</button></form></div>'
    ) % (
        E(", ".join(view.d["notify_channels"]) or "ch\u01b0a c\u1ea5u h\u00ecnh"),
        view.csrf,
        fieldset("Telegram", telegram),
        fieldset(
            "Discord / Slack (webhook https)",
            field("\u0110\u1ecba ch\u1ec9 webhook", '<input type="password" name="webhook" autocomplete="off" placeholder="https://...">'),
            False,
        ),
        fieldset(
            "ntfy (https)",
            field(
                "\u0110\u1ecba ch\u1ec9 ch\u1ee7 \u0111\u1ec1",
                '<input type="password" name="ntfy" autocomplete="off" placeholder="https://ntfy.sh/ten-rieng">',
            ),
            False,
        ),
        view.csrf,
        view.csrf,
    )


def event_log(view):
    rows = [
        "<tr>%s%s%s%s</tr>"
        % (
            cell("L\u00fac", ago(e["at"], view.now)),
            cell("S\u1ef1 ki\u1ec7n", E(EVENT_LABELS.get(e["event"], e["event"]))),
            cell("Video", E((e["title"] or "")[:70]), "t"),
            cell("Chi ti\u1ebft", E(vi_reason(e["detail"] or "")[:120])),
        )
        for e in view.d["events"]
    ]
    return table(("L\u00fac", "S\u1ef1 ki\u1ec7n", "Video", "Chi ti\u1ebft"), rows, "Ch\u01b0a c\u00f3 s\u1ef1 ki\u1ec7n.")


def manual_import(view):
    return (
        '<form method="post" action="/ingest-form" class="stack"><input type="hidden" name="csrf" value="%s">'
        '<textarea name="batch" rows="5" placeholder=\'{"platform":"douyin","stream":"hot_music","observed_at":0,"items":[]}\'></textarea>'
        '<div class="btns"><button class="ghost">Ki\u1ec3m tra v\u00e0 nh\u1eadp</button></div></form>'
    ) % view.csrf


def render(view):
    return "".join(
        (
            '<h2 class="desk">Ngu\u1ed3n, c\u00e0i \u0111\u1eb7t, th\u00f4ng b\u00e1o, nh\u1eadt k\u00fd</h2>',
            accordion("accounts", "T\u00e0i kho\u1ea3n TikTok v\u00e0 ch\u1ee7 \u0111\u1ec1", accounts.render(view)),
            accordion("sources", "Ngu\u1ed3n thu th\u1eadp", sources(view)),
            accordion(
                "settings",
                "C\u00e0i \u0111\u1eb7t",
                settings_form(view) + '<h3 class="sub">Kh\u00f3a Gemini v\u00e0 gi\u1ecdng \u0111\u1ecdc</h3>' + gemini_key_form(view),
            ),
            accordion("notify", "Th\u00f4ng b\u00e1o \u0111i\u1ec7n tho\u1ea1i", notify_form(view)),
            accordion("log", "Nh\u1eadt k\u00fd", event_log(view)),
            accordion("advanced", "N\u00e2ng cao: nh\u1eadp quan s\u00e1t b\u1eb1ng tay", manual_import(view)),
        )
    )
