"""Post: every processed video with its caption editor and the Post button; and, when empty, why and what to do."""

from ..cards import ready_card
from ..components import task_panel
from ..format import escape as E
from ..labels import VISIBILITY_LABEL


def blocked_reason(view, job=None):
    """Why posting this video cannot start right now (shown on its card), or ''. The verification pause holds every account; an unconfirmed
    post holds only its own account, the one this video would go to."""
    if view.challenge_on:
        return "TikTok \u0111ang \u0111\u00f2i x\u00e1c minh%s: gi\u1ea3i m\u1ed9t l\u1ea7n b\u1eb1ng %s (xem m\u1ee5c C\u1ea7n xem)." % (
            view.challenge_who,
            view.challenge_command,
        )
    if view.d["unresolved_publishes"]:
        destination = view.destination((job or {}).get("topic"))
        if view.unconfirmed_for(destination):
            who = " c\u1ee7a @%s" % destination["username"] if destination else ""
            return (
                "C\u00f3 b\u00e0i \u0111\u0103ng%s ch\u01b0a x\u00e1c nh\u1eadn: x\u1eed l\u00fd \u1edf m\u1ee5c C\u1ea7n xem tr\u01b0\u1edbc."
                % who
            )
    return ""


def _today(view):
    """Posts made today: one total, or one figure per account when there are several."""
    d = view.d
    enabled = [a for a in d["accounts"] if a["enabled"]]
    if len(enabled) < 2:
        return "%d / %d" % (d["published_today"], d["daily_limit"])
    return " · ".join("@%s %d/%d" % (a["username"], a["published_today"], a["daily_limit"]) for a in enabled)


def _strip(view):
    d, cfg = view.d, view.cfg
    window = "\u0111ang m\u1edf" if d["in_window"] else E("m\u1edf l\u00fac " + (d["next_window"] or "—"))
    return (
        '<div class="card strip"><div><small>H\u00f4m nay</small><b>%s</b></div><div><small>Hi\u1ec3n th\u1ecb</small><b>%s</b></div>'
        "<div><small>Gi\u1edd v\u00e0ng</small><b>%s</b></div></div>"
    ) % (E(_today(view)), E(VISIBILITY_LABEL.get(cfg["visibility"], cfg["visibility"])), window)


def _empty_guide(view):
    """Nothing is ready: say which of the three situations this is, with the one button that moves it forward."""
    waiting, candidates = view.waiting, view.counts.get("candidate", 0)
    if waiting and not view.d["processing_enabled"]:
        why = (
            '<p><b>%d video \u0111ang ch\u1edd x\u1eed l\u00fd</b> nh\u01b0ng c\u00f4ng t\u1eafc "X\u1eed l\u00fd video" \u0111ang <b>T\u1eaeT</b>, n\u00ean ch\u01b0a video n\u00e0o \u0111\u01b0\u1ee3c d\u1ef1ng.</p>'
            '<p class="hint">B\u1eadt l\u00ean \u0111\u1ec3 Gemini l\u00e0m Vietsub ho\u1eb7c l\u1ed3ng ti\u1ebfng. Video xong s\u1ebd hi\u1ec7n \u1edf \u0111\u00e2y \u0111\u1ec3 b\u1ea1n \u0111\u0103ng.</p>%s'
        ) % (waiting, view.enable_processing("publish"))
    elif waiting:
        why = (
            "<p><b>%d video \u0111ang ch\u1edd x\u1eed l\u00fd</b> (m\u1ed7i video kho\u1ea3ng 1–3 ph\u00fat). X\u1eed l\u00fd xong s\u1ebd hi\u1ec7n \u1edf \u0111\u00e2y.</p>%s"
        ) % (
            waiting,
            view.action("process", "⚙️ X\u1eed l\u00fd ngay (%d)" % waiting, "go big", view.busy_process, "publish"),
        )
    else:
        extra = (" (c\u00f3 %d \u1ee9ng vi\u00ean ch\u01b0a t\u1ea3i v\u1ec1)" % candidates) if candidates else ""
        why = (
            '<p>Ch\u01b0a c\u00f3 video n\u00e0o \u0111\u1ec3 x\u1eed l\u00fd%s.</p><p class="hint">B\u1ea5m c\u1eadp nh\u1eadt \u0111\u1ec3 thu th\u1eadp video m\u1edbi v\u00e0 x\u1eed l\u00fd; video xong s\u1ebd hi\u1ec7n \u1edf \u0111\u00e2y.</p>%s'
        ) % (
            extra,
            view.action(
                "update",
                "▶ C\u1eadp nh\u1eadt &amp; chu\u1ea9n b\u1ecb \u0111\u0103ng",
                "go big",
                view.busy_browser or view.busy_process,
                "publish",
            ),
        )
    hints = []
    if view.attention:
        hints.append(
            '%d video \u0111ang \u1edf tab <a href="#attention">C\u1ea7n xem</a> (h\u1ec7 th\u1ed1ng gi\u1eef l\u1ea1i \u0111\u1ec3 b\u1ea1n duy\u1ec7t).'
            % view.attention
        )
    hints.append('<a href="#queue">Xem h\u00e0ng \u0111\u1ee3i →</a>')
    return (
        '<div class="card stack empty-guide"><h3>Ch\u01b0a c\u00f3 video n\u00e0o x\u1eed l\u00fd xong</h3>%s<p class="small muted">%s</p></div>'
        % (
            why,
            " ".join(hints),
        )
    )


def render(view):
    body = "".join(ready_card(job, view, blocked_reason(view, job)) for job in view.ready) if view.ready else _empty_guide(view)
    return (
        '<h2>\u0110\u0103ng b\u00e0i</h2><p class="hint">\u0110\u00e2y l\u00e0 c\u00e1c video \u0111\u00e3 x\u1eed l\u00fd xong. Xem th\u1eed, s\u1eeda m\u00f4 t\u1ea3 v\u00e0 hashtag n\u1ebfu mu\u1ed1n, r\u1ed3i b\u1ea5m <b>\u0110\u0103ng ngay</b> \u0111\u1ec3 \u0111\u0103ng \u0111\u00fang video \u0111\u00f3. '
        'L\u1ecbch t\u1ef1 \u0111\u1ed9ng v\u1eabn t\u1ef1 ch\u1ecdn b\u00e0i \u0111i\u1ec3m cao nh\u1ea5t \u0111\u1ec3 \u0111\u0103ng trong gi\u1edd v\u00e0ng.</p>%s%s<div class="stack">%s</div>'
    ) % (task_panel(view.tasks, view.now, ("publish", "dryrun", "update")), _strip(view), body)
