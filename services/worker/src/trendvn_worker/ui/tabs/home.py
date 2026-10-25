"""Overview: state of the automation, the main buttons, the two switches, health, numbers and the setup checklist."""

from ..components import chip, component_chip, quick_switch, task_panel
from ..format import ago, escape as E, num, windows_text


def _accounts_text(d):
    """'@a' for one account, '3 accounts (@a, @b, @c)' for several."""
    names = ["@" + a["username"] for a in d["accounts"] if a["enabled"]]
    return names[0] if len(names) == 1 else "%d t\u00e0i kho\u1ea3n (%s)" % (len(names), ", ".join(names))


def _banner_problem(view):
    """Why the automation is not fully running by itself, in the owner's words, or '' when it is. Green means every part reports in."""
    d = view.d
    if view.key_rejected:
        return "Kh\u00f3a Gemini b\u1ecb Google t\u1eeb ch\u1ed1i: v\u00e0o Th\u00eam → C\u00e0i \u0111\u1eb7t \u0111\u1ed5i kh\u00f3a (c\u00e1c video v\u1eabn n\u1eb1m ch\u1edd, kh\u00f4ng m\u1ea5t)."
    if not (d["gemini_configured"] and d["processing_enabled"] and d["publisher_enabled"]):
        return "Ho\u00e0n t\u1ea5t danh s\u00e1ch thi\u1ebft l\u1eadp \u0111\u1ec3 b\u1eadt t\u1ef1 \u0111\u1ed9ng."
    if view.attention:
        return "C\u00f3 %d vi\u1ec7c c\u1ea7n b\u1ea1n xem \u1edf tab C\u1ea7n xem." % view.attention
    waiting = view.counts.get("awaiting_approval", 0)
    if waiting:  # (also after the approval switch was turned off: the scheduler posts only videos that were released)
        return (
            "C\u00f3 %d video \u0111ang ch\u1edd b\u1ea1n duy\u1ec7t \u1edf tab \u0110\u0103ng b\u00e0i; ch\u01b0a duy\u1ec7t th\u00ec ch\u01b0a \u0111\u0103ng."
            % waiting
        )
    parts = (("B\u1ed9 thu th\u1eadp", d["discovery"]), ("Tr\u00ecnh \u0111\u0103ng TikTok", d["publisher"]))
    erred = [name for name, state in parts if state == "error"]
    if erred:
        return (
            "%s \u0111ang b\u00e1o l\u1ed7i: xem d\u00f2ng T\u00ecnh tr\u1ea1ng b\u00ean d\u01b0\u1edbi ho\u1eb7c ch\u1ea1y ./trendvn doctor."
            % ", ".join(erred)
        )
    silent = [name for name, state in parts if state != "connected"]
    if silent:
        return (
            "%s ch\u01b0a b\u00e1o c\u00e1o g\u1ea7n \u0111\u00e2y: l\u1ecbch t\u1ef1 \u0111\u1ed9ng c\u00f3 th\u1ec3 \u0111\u00e3 t\u1eaft (ch\u1ea1y ./trendvn n8n activate) ho\u1eb7c agent kh\u00f4ng ch\u1ea1y (./trendvn doctor)."
            % ", ".join(silent)
        )
    return ""


def banner(view):
    problem = _banner_problem(view)
    if not problem:
        return '<div class="banner good"><b>\u0110ang t\u1ef1 \u0111\u1ed9ng ho\u00e0n to\u00e0n.</b> Thu th\u1eadp, x\u1eed l\u00fd v\u00e0 \u0111\u0103ng ch\u1ea1y theo l\u1ecbch.</div>'
    return '<div class="banner warn"><b>Ch\u01b0a t\u1ef1 \u0111\u1ed9ng ho\u00e0n to\u00e0n.</b> %s</div>' % E(problem)


def control(view):
    """The 'start now' buttons. They are an addition: the n8n schedule keeps running on its own."""
    hint = (
        "Thu th\u1eadp video m\u1edbi → x\u1eed l\u00fd (Vietsub/l\u1ed3ng ti\u1ebfng) → s\u1eb5n s\u00e0ng \u0111\u0103ng. "
        if view.d["processing_enabled"]
        else 'X\u1eed l\u00fd video \u0111ang T\u1eaeT n\u00ean n\u00fat n\u00e0y ch\u1ec9 thu th\u1eadp; b\u1eadt c\u00f4ng t\u1eafc "X\u1eed l\u00fd video" \u0111\u1ec3 \u0111i tr\u1ecdn v\u00f2ng. '
    )
    return (
        '<div class="card stack" id="control"><h2>\u0110i\u1ec1u khi\u1ec3n</h2>%s<p class="hint">%sL\u1ecbch t\u1ef1 \u0111\u1ed9ng v\u1eabn ch\u1ea1y song song nh\u01b0 c\u0169.</p>'
        '<div class="btngrid">%s%s</div>%s</div>'
    ) % (
        view.action(
            "update",
            "▶ B\u1eaft \u0111\u1ea7u: c\u1eadp nh\u1eadt &amp; chu\u1ea9n b\u1ecb \u0111\u0103ng",
            "go xl",
            view.busy_browser or view.busy_process,
            "home",
        ),
        E(hint),
        view.action("collect", "🔎 Thu th\u1eadp video m\u1edbi", "ghost", view.busy_browser, "queue"),
        view.action("process", "⚙️ X\u1eed l\u00fd video ch\u1edd (%d)" % view.waiting, "ghost", view.busy_process, "queue"),
        task_panel(view.tasks, view.now),
    )


def switches(view):
    """Processing and auto-post, one tap each (the auto-post switch doubles as the emergency stop)."""
    d, cfg = view.d, view.cfg
    visibility = {"public": "c\u00f4ng khai", "friends": "b\u1ea1n b\u00e8", "self": "ch\u1ec9 m\u00ecnh t\u00f4i"}.get(
        cfg["visibility"], cfg["visibility"]
    )
    return '<div class="quick">%s%s</div>' % (
        quick_switch(
            view.csrf,
            "processing_enabled",
            "X\u1eed l\u00fd video",
            d["processing_enabled"],
            "\u0110ANG B\u1eacT",
            "\u0110ANG T\u1eaeT",
            confirm="B\u1eadt x\u1eed l\u00fd video? Video s\u1ebd \u0111\u01b0\u1ee3c g\u1eedi t\u1edbi Google Gemini \u0111\u1ec3 ph\u00e2n t\u00edch.",
        ),
        quick_switch(
            view.csrf,
            "publisher_enabled",
            "T\u1ef1 \u0111\u0103ng TikTok",
            d["publisher_enabled"],
            "\u0110ANG B\u1eacT · ch\u1ea1m \u0111\u1ec3 d\u1eebng",
            "\u0110ANG T\u1eaeT",
            danger=True,
            confirm="B\u1eadt t\u1ef1 \u0111\u0103ng? H\u1ec7 th\u1ed1ng s\u1ebd t\u1ef1 \u0111\u0103ng l\u00ean %s theo l\u1ecbch (t\u1ed1i \u0111a %d b\u00e0i/ng\u00e0y, ch\u1ebf \u0111\u1ed9 %s)."
            % (_accounts_text(d), d["daily_limit"], visibility),
        ),
    )


def health(view):
    """Three rows: collector, publisher, golden hour."""
    d = view.d

    def row(label, state_html):
        return '<div class="pill"><span>%s</span>%s</div>' % (E(label), state_html)

    window = chip(
        "\u0110ang m\u1edf" if d["in_window"] else "M\u1edf l\u00fac " + (d["next_window"] or "—"), "good" if d["in_window"] else "mute"
    )
    rows = (
        row("Thu th\u1eadp video", component_chip(d["discovery"]))
        + row("\u0110\u0103ng TikTok", component_chip(d["publisher"]))
        + row("Gi\u1edd v\u00e0ng", window)
        + row("\u1ed4 \u0111\u0129a", _disk_chip(d.get("disk_free_mb")))
    )
    return '<div class="card pills"><h3>T\u00ecnh tr\u1ea1ng</h3>%s</div>' % rows


def _disk_chip(free_mb):
    """Free disk space: a full disk stops everything, so it is on the front page. Under 1 GB downloads pause, under 512 MB so does rendering."""
    if free_mb is None:
        return chip("Kh\u00f4ng r\u00f5", "mute")
    text = "%.1f GB tr\u1ed1ng" % (free_mb / 1024) if free_mb >= 1024 else "%d MB tr\u1ed1ng" % free_mb
    return chip(text, "good" if free_mb >= 2048 else ("warn" if free_mb >= 1024 else "bad"))


def numbers(view):
    d = view.d
    read = [
        p["views"] for p in d["performance"] if p["views"] is not None
    ]  # None = never read from TikTok, which is not the same as 0 views
    total_views = sum(read)
    tiles = (
        ("\u0110\u0103ng h\u00f4m nay", "%d / %d" % (d["published_today"], d["daily_limit"])),
        ("Ch\u1edd x\u1eed l\u00fd", view.waiting),
        ("S\u1eb5n s\u00e0ng \u0111\u0103ng", view.ready_total),
        ("C\u1ea7n xem", view.attention),
        ("T\u1ed5ng \u0111\u00e3 \u0111\u0103ng", view.counts.get("published", 0)),
        ("L\u01b0\u1ee3t xem (30 b\u00e0i g\u1ea7n nh\u1ea5t)", num(total_views) if read else "—"),
    )
    return '<div class="kpis">%s</div>' % "".join('<div class="kpi"><small>%s</small><b>%s</b></div>' % (E(a), E(str(b))) for a, b in tiles)


def schedule(view):
    cfg = view.cfg
    last_scan = view.d.get("discovery_at")
    return (
        '<div class="card stack"><h2>L\u1ecbch t\u1ef1 \u0111\u1ed9ng</h2><ul class="plain"><li><b>Thu th\u1eadp v\u00e0 x\u1eed l\u00fd:</b> m\u1ed7i 3 gi\u1edd (n8n)%s</li>'
        "<li><b>\u0110\u0103ng:</b> ki\u1ec3m tra m\u1ed7i 30 ph\u00fat, ch\u1ec9 \u0111\u0103ng trong gi\u1edd v\u00e0ng %s, t\u1ed1i \u0111a %d b\u00e0i/ng\u00e0y%s, c\u00e1ch nhau ≥ %s gi\u1edd</li>"
        "<li><b>Ch\u1ed1t ng\u00e0y:</b> 23:30, \u0111\u1ecdc l\u01b0\u1ee3t xem v\u00e0 g\u1eedi t\u00f3m t\u1eaft</li></ul>"
        '<p class="muted small">C\u00e1c n\u00fat \u1edf tr\u00ean ch\u1ec9 l\u00e0 b\u1ed5 sung; kh\u00f4ng thay th\u1ebf v\u00e0 kh\u00f4ng l\u00e0m gi\u00e1n \u0111o\u1ea1n l\u1ecbch.</p></div>'
    ) % (
        (" · l\u1ea7n g\u1ea7n nh\u1ea5t %s" % ago(last_scan, view.now)) if last_scan else "",
        E(windows_text(cfg["post_windows"]) or "m\u1ecdi l\u00fac"),
        view.d["daily_limit"],
        (
            " (t\u1ed5ng c\u00e1c t\u00e0i kho\u1ea3n; m\u1ed7i t\u00e0i kho\u1ea3n c\u00f3 gi\u1edbi h\u1ea1n ri\u00eang)"
            if len(view.takers(None)) > 1
            else ""
        ),
        E("%g" % round(cfg["min_publish_gap"] / 3600, 2)),
    )


def checklist(view):
    """(done, total, rows html): what is still needed for the system to run by itself."""
    d = view.d
    items = [
        (
            d["gemini_configured"],
            "Kh\u00f3a Gemini API",
            "Nh\u1eadp kh\u00f3a \u1edf m\u1ee5c C\u00e0i \u0111\u1eb7t b\u00ean d\u01b0\u1edbi.",
        ),
        (
            d["processing_enabled"],
            "B\u1eadt x\u1eed l\u00fd video",
            "Video s\u1ebd \u0111\u01b0\u1ee3c g\u1eedi t\u1edbi Google Gemini \u0111\u1ec3 ph\u00e2n t\u00edch khi b\u1ea1n b\u1eadt.",
        ),
        (
            d["discovery"] == "connected",
            "B\u1ed9 thu th\u1eadp ch\u1ea1y \u0111\u01b0\u1ee3c",
            "C\u1ea7n agent tr\u00ean m\u00e1y v\u00e0 workflow n8n 01 \u0111\u00e3 b\u1eadt.",
        ),
        (d["publisher"] == "connected", "\u0110\u00e3 \u0111\u0103ng nh\u1eadp TikTok", "Ch\u1ea1y: ./trendvn tiktok login"),
        (
            d["publisher_enabled"],
            "B\u1eadt t\u1ef1 \u0111\u0103ng",
            "N\u00ean ch\u1ea1y th\u1eed dry-run v\u00e0 xem \u1ea3nh ch\u1ee5p tr\u01b0\u1edbc khi b\u1eadt.",
        ),
        (
            bool(d["notify_channels"]),
            "Nh\u1eadn th\u00f4ng b\u00e1o \u0111i\u1ec7n tho\u1ea1i",
            "T\u00f9y ch\u1ecdn: Telegram, ntfy ho\u1eb7c webhook (m\u1ee5c Th\u00f4ng b\u00e1o).",
        ),
    ]
    rows = "".join(
        '<li class="%s"><span class="tick">%s</span><div><b>%s</b><small>%s</small></div></li>'
        % ("ok" if ok else "todo", "✓" if ok else "○", E(title), "" if ok else E(hint))
        for ok, title, hint in items
    )
    return sum(1 for ok, _, _ in items if ok), len(items), rows


def setup_card(view):
    done, total, rows = checklist(view)
    return '<div class="card"><h2>Thi\u1ebft l\u1eadp <small>%d/%d ho\u00e0n t\u1ea5t</small></h2><ul class="check">%s</ul></div>' % (
        done,
        total,
        rows,
    )


def flow_card(view):
    return (
        '<div class="card stack"><h2>Lu\u1ed3ng x\u1eed l\u00fd</h2>%s<p class="muted small">Ch\u1ea1m v\u00e0o t\u1eebng b\u01b0\u1edbc \u0111\u1ec3 xem chi ti\u1ebft. '
        "M\u1ed1c ban \u0111\u1ea7u (%d) ch\u1ec9 \u0111\u1ec3 nh\u1eadn di\u1ec7n video m\u1edbi, kh\u00f4ng bao gi\u1edd \u0111\u0103ng.</p></div>"
    ) % (view.funnel(), view.counts.get("baseline", 0))


def render(view):
    return "".join(
        (banner(view), control(view), switches(view), health(view), numbers(view), schedule(view), setup_card(view), flow_card(view))
    )
