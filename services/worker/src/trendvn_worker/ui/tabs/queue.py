"""Queue: videos waiting to be processed (in the order they will be), and candidates not yet downloaded."""

from ...domain import topics
from ..components import accordion, cell, platform_badge, state_chip, table, task_panel
from ..format import ago, escape as E, headline, meta_of, num, shown_of


def _topic_cell(job):
    """The topic Gemini decided on, or the collector's guess (marked with ~) while the video is still unprocessed."""
    if job.get("topic"):
        return E(topics.label(job["topic"]))
    return ("~" + E(topics.label(job["topic_hint"]))) if job.get("topic_hint") else "—"


def _video_table(items, now, empty):
    rows = [
        "<tr>%s%s%s%s%s%s</tr>"
        % (
            cell("Ngu\u1ed3n", platform_badge(j["platform"])),
            cell("Video", headline(j, 90), "t"),
            cell("Ch\u1ee7 \u0111\u1ec1", _topic_cell(j)),
            cell("Tr\u1ea1ng th\u00e1i", state_chip(j["state"])),
            cell("\u0110i\u1ec3m", E(num(meta_of(j).get("score"))) if meta_of(j).get("score") else "—"),
            cell("T\u00ecm th\u1ea5y", ago(j["first_seen"], now)),
        )
        for j in items
    ]
    return table(
        ("Ngu\u1ed3n", "Video", "Ch\u1ee7 \u0111\u1ec1", "Tr\u1ea1ng th\u00e1i", "\u0110i\u1ec3m", "T\u00ecm th\u1ea5y"), rows, empty
    )


def processing_card(view):
    """Either how to switch processing on, or the buttons that run it now."""
    waiting = view.waiting
    if not view.d["processing_enabled"]:
        backlog = (
            ("<b>%d video</b> \u0111ang n\u1eb1m ch\u1edd. " % waiting) if waiting else "s\u1ebd n\u1eb1m ch\u1edd \u1edf \u0111\u00e2y. "
        )
        return (
            '<div class="card stack alert-soft"><h3>X\u1eed l\u00fd video \u0111ang T\u1eaeT</h3><p>Video v\u1eabn \u0111\u01b0\u1ee3c thu th\u1eadp nh\u01b0ng ch\u01b0a \u0111\u01b0\u1ee3c d\u1ef1ng, n\u00ean %s'
            "B\u1eadt l\u00ean \u0111\u1ec3 Gemini l\u00e0m Vietsub ho\u1eb7c l\u1ed3ng ti\u1ebfng.</p>%s</div>"
        ) % (backlog, view.enable_processing("queue"))
    status = (
        (
            "\u0110ang c\u00f3 <b>%d video</b> ch\u1edd Gemini l\u00e0m Vietsub/l\u1ed3ng ti\u1ebfng. Video xong s\u1ebd chuy\u1ec3n sang tab \u0110\u0103ng b\u00e0i."
            % waiting
        )
        if waiting
        else "Kh\u00f4ng c\u00f3 video n\u00e0o ch\u1edd x\u1eed l\u00fd. B\u1ea5m <b>Thu th\u1eadp</b> \u0111\u1ec3 t\u00ecm video m\u1edbi."
    )
    process_label = "⚙️ X\u1eed l\u00fd %d video ch\u1edd" % waiting if waiting else "⚙️ Kh\u00f4ng c\u00f3 video ch\u1edd"
    return '<div class="card stack"><h3>X\u1eed l\u00fd</h3><p class="hint">%s</p><div class="btngrid">%s%s</div></div>' % (
        status,
        view.action("process", process_label, "go big", view.busy_process or not waiting, "queue"),
        view.action("collect", "🔎 Thu th\u1eadp video m\u1edbi", "ghost big", view.busy_browser, "queue"),
    )


def render(view):
    d = view.d
    candidates = accordion(
        "candidates",
        "\u1ee8ng vi\u00ean ch\u01b0a t\u1ea3i v\u1ec1 (%s)" % shown_of(len(d.get("candidates", [])), view.counts.get("candidate", 0)),
        '<p class="muted small">\u0110\u00e3 t\u00ecm th\u1ea5y v\u00e0 \u0111\u1ea1t ng\u01b0\u1ee1ng th\u1ecbnh h\u00e0nh; s\u1ebd \u0111\u01b0\u1ee3c t\u1ea3i v\u1ec1 \u1edf l\u1ea7n thu th\u1eadp k\u1ebf ti\u1ebfp.</p>'
        + _video_table(d.get("candidates", []), view.now, "Kh\u00f4ng c\u00f3 \u1ee9ng vi\u00ean n\u00e0o."),
    )
    return (
        '<h2>H\u00e0ng \u0111\u1ee3i</h2><p class="hint">\u0110\u01b0\u1eddng \u0111i c\u1ee7a m\u1ed9t video: <b>\u1ee8ng vi\u00ean</b> (\u0111\u00e3 t\u00ecm th\u1ea5y, ch\u01b0a t\u1ea3i) → <b>Ch\u1edd x\u1eed l\u00fd</b> (\u0111\u00e3 t\u1ea3i, ch\u1edd Gemini) → '
        "<b>S\u1eb5n s\u00e0ng</b> (sang tab \u0110\u0103ng b\u00e0i) → <b>\u0110\u00e3 \u0111\u0103ng</b>.</p>%s%s%s"
        '<h3 class="sub">\u0110ang ch\u1edd x\u1eed l\u00fd (%s)</h3>%s%s'
    ) % (
        view.funnel(),
        processing_card(view),
        task_panel(view.tasks, view.now, ("process", "update", "collect")),
        shown_of(len(d.get("queue", [])), view.waiting),
        _video_table(d.get("queue", []), view.now, "Kh\u00f4ng c\u00f3 video n\u00e0o ch\u1edd x\u1eed l\u00fd."),
        candidates,
    )
