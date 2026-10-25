"""The two video cards: a rendered video ready to post, and a video held back for the owner to review."""

import re

from ..domain import topics
from ..domain.accounts import account_flag
from .components import chip, platform_badge, state_chip
from .format import escape as E, headline, left_text, meta_of, num
from .labels import ROUTE_LABEL, vi_reason

CONFIRM_VISIBILITY = {"public": "C\u00d4NG KHAI", "friends": "B\u1ea0N B\u00c8", "self": "CH\u1ec8 M\u00ccNH T\u00d4I"}


def _fact_chips(job, info):
    facts = []
    if info.get("w"):
        portrait_916 = info["h"] > info["w"] and abs(info["w"] / info["h"] - 9 / 16) < 0.03
        facts.append(chip("%d×%d%s" % (info["w"], info["h"], " · 9:16" if portrait_916 else ""), "good" if portrait_916 else "warn"))
    if info.get("duration"):
        facts.append(chip("%s gi\u00e2y" % info["duration"], "mute"))
    if info.get("size"):
        facts.append(chip("%.1f MB" % (info["size"] / 1e6), "mute"))
    facts.append(chip(ROUTE_LABEL.get(job["route"], job["route"] or ""), "info"))
    if info.get("reframed"):
        facts.append(chip("\u0111\u00e3 \u0111\u01b0a v\u00e0o khung d\u1ecdc", "mute"))
    if info.get("voice"):
        facts.append(chip("gi\u1ecdng " + str(info["voice"]), "info"))
    if info.get("hard_subs_blurred"):
        facts.append(chip("l\u00e0m m\u1edd ph\u1ee5 \u0111\u1ec1 g\u1ed1c khi c\u00f3 ph\u1ee5 \u0111\u1ec1 Vi\u1ec7t", "mute"))
    elif info.get("hard_subs"):
        facts.append(chip("ph\u1ee5 \u0111\u1ec1 g\u1ed1c gi\u1eef nguy\u00ean", "mute"))
    if info.get("warning"):
        facts.append(chip(info["warning"], "warn"))
    return "".join(facts)


def _score_line(meta, with_views=True):
    parts = []
    if meta.get("score"):
        parts.append("\u0111i\u1ec3m %s" % num(meta["score"]))
    if meta.get("likes"):
        parts.append("%s tim" % num(meta["likes"]))
    if with_views and meta.get("views"):
        parts.append("%s xem" % num(meta["views"]))
    if meta.get("age_h") is not None:
        parts.append("%.0f gi\u1edd tu\u1ed5i" % meta["age_h"])
    return " · ".join(parts)


FAILED_REST_SECONDS = 3600  # the scheduler skips a video that failed to post this recently (store/publishing.py::_best_ready_video)


def _destination_line(view, job):
    """Which topic the video is about and which accounts take it; says so when none does."""
    topic = job.get("topic")
    if len(view.d.get("accounts", [])) < 2 and not topic:
        return ""
    label = topics.label(topic) if topic else "ch\u01b0a ph\u00e2n lo\u1ea1i"
    takers = view.takers(topic)
    if takers:
        names = ", ".join("@" + a["username"] for a in takers)
        return '<div class="muted small">Ch\u1ee7 \u0111\u1ec1: <b>%s</b> · %s <b>%s</b></div>' % (
            E(label),
            (
                "l\u1ecbch t\u1ef1 \u0111\u1ed9ng \u0111\u0103ng l\u00ean"
                if len(takers) == 1
                else "l\u1ecbch t\u1ef1 \u0111\u1ed9ng ch\u1ecdn m\u1ed9t trong"
            ),
            E(names),
        )
    default = view.destination(topic)
    return (
        '<div class="note warn small">Ch\u1ee7 \u0111\u1ec1 <b>%s</b> ch\u01b0a c\u00f3 t\u00e0i kho\u1ea3n n\u00e0o nh\u1eadn. L\u1ecbch t\u1ef1 \u0111\u1ed9ng s\u1ebd kh\u00f4ng \u0111\u0103ng; n\u00fat \u0110\u0103ng ngay d\u00f9ng @%s.</div>'
        % (
            E(label),
            E(default["username"] if default else view.cfg["target"]),
        )
    )


def _confirm_text(view, job):
    """The question asked before 'Post now': where it goes, how visible, and any rule the click overrides."""
    d, cfg = view.d, view.cfg
    account = view.destination(job.get("topic"))
    warnings = []
    # the rules that apply are the account's own (its limit, its golden hours), not the channel's totals
    today, limit, inside = (
        (account["published_today"], account["daily_limit"], account["in_window"])
        if account
        else (d["published_today"], d["daily_limit"], d["in_window"])
    )
    if today >= limit:
        warnings.append(
            "H\u00f4m nay \u0111\u00e3 \u0111\u0103ng \u0111\u1ee7 %d/%d b\u00e0i, b\u1ea1n v\u1eabn mu\u1ed1n \u0111\u0103ng th\u00eam?"
            % (today, limit)
        )
    if not inside:
        warnings.append("\u0110ang ngo\u00e0i gi\u1edd v\u00e0ng.")
    shown = account["visibility"] if account else cfg["visibility"]
    visibility = CONFIRM_VISIBILITY.get(shown, shown)
    return "\u0110\u0103ng video n\u00e0y l\u00ean @%s ngay b\u00e2y gi\u1edd? Ch\u1ebf \u0111\u1ed9 hi\u1ec3n th\u1ecb: %s. %s" % (
        account["username"] if account else cfg["target"],
        visibility,
        " ".join(warnings),
    )


def _account_hold(view, account):
    """What keeps the schedule from posting on this account right now (from the dashboard's numbers, the same order the scheduler checks
    them in), or None when nothing does."""
    name = "@" + account["username"]
    if account.get("logged_in") is False:
        return "%s ch\u01b0a \u0111\u0103ng nh\u1eadp TikTok (./trendvn tiktok login%s)" % (name, account_flag(account["id"]))
    if view.unconfirmed_for(account):
        return "%s c\u00f3 b\u00e0i \u0111\u0103ng ch\u01b0a x\u00e1c nh\u1eadn (x\u1eed l\u00fd \u1edf tab C\u1ea7n xem)" % name
    if not account.get("in_window", True):
        return "%s ngo\u00e0i gi\u1edd v\u00e0ng, l\u1ea7n t\u1edbi %s" % (name, account.get("next_window") or "?")
    if account["published_today"] >= account["daily_limit"]:
        return "%s \u0111\u00e3 \u0111\u0103ng \u0111\u1ee7 %d/%d b\u00e0i h\u00f4m nay" % (
            name,
            account["published_today"],
            account["daily_limit"],
        )
    wait = (account.get("next_post_at") or 0) - view.now
    if wait > 0:
        return "%s ph\u1ea3i gi\u00e3n c\u00e1ch gi\u1eefa hai b\u00e0i, c\u00f2n %s" % (name, left_text(wait))
    return None


def _everyone_hold(view, job):
    """What holds this video back whichever account would post it: a verification pause, a post in flight, a recent failure of this video."""
    if view.challenge_on:
        return "TikTok \u0111ang \u0111\u00f2i x\u00e1c minh (\u0111\u0103ng t\u1ea1m d\u1eebng cho t\u1edbi khi b\u1ea1n gi\u1ea3i)"
    if view.counts.get("publishing", 0):
        return "m\u1ed9t b\u00e0i kh\u00e1c \u0111ang \u0111\u01b0\u1ee3c \u0111\u0103ng"
    failed = job.get("last_publish_fail")
    if failed and view.now - failed < FAILED_REST_SECONDS:
        return (
            "l\u1ea7n \u0111\u0103ng tr\u01b0\u1edbc l\u1ed7i n\u00ean video n\u00e0y ngh\u1ec9 %s tr\u01b0\u1edbc khi th\u1eed l\u1ea1i"
            % left_text(FAILED_REST_SECONDS - (view.now - failed))
        )
    return None


def _waiting_line(view, job):
    """Why the schedule has not posted this video yet, in words (the scheduler itself only tells n8n, in English)."""
    if job["state"] == "awaiting_approval":
        text = "Ch\u1edd b\u1ea1n duy\u1ec7t: duy\u1ec7t xong th\u00ec l\u1ecbch m\u1edbi \u0111\u0103ng video n\u00e0y."
    elif not view.d["publisher_enabled"]:
        text = "C\u00f4ng t\u1eafc T\u1ef1 \u0111\u0103ng \u0111ang t\u1eaft n\u00ean l\u1ecbch ch\u01b0a \u0111\u0103ng video n\u00e0o. B\u1eadt \u1edf tab T\u1ed5ng quan."
    else:
        takers = view.takers(job.get("topic"))
        if not takers:
            return ""  # the destination line says that no account takes this topic
        everyone = _everyone_hold(view, job)
        holds = [everyone] if everyone else [_account_hold(view, a) for a in takers]
        if None in holds:
            text = "S\u1eb5n s\u00e0ng: l\u1ecbch s\u1ebd \u0111\u0103ng \u1edf l\u1ea7n ki\u1ec3m tra l\u1ecbch k\u1ebf ti\u1ebfp n\u1ebfu t\u1edbi l\u01b0\u1ee3t."
        else:
            text = "Ch\u01b0a \u0111\u0103ng v\u00ec: " + "; ".join(holds) + "."
    return '<div class="note small wait">%s</div>' % E(text)


def ready_card(job, view, blocked):
    """One rendered video: preview, editable caption and hashtags, quality facts, and the buttons to post it."""
    info = job.get("info") or {}
    lint = job["lint"]
    poster = ' poster="/media/%s/poster"' % E(job["id"]) if info.get("poster") else ""
    video = '<video controls preload="none" playsinline%s src="/media/%s/final"></video>' % (poster, E(job["id"]))
    if lint["ok"]:
        lint_html = '<div class="lint ok">✓ M\u00f4 t\u1ea3 t\u1ed1t: %d k\u00fd t\u1ef1, %d hashtag</div>' % (lint["length"], lint["tags"])
    else:
        lint_html = '<div class="lint warn">⚠ %s</div>' % E(" · ".join(lint["issues"]))
    disabled = " disabled" if (blocked or view.busy_browser) else ""
    if blocked:
        reason = '<div class="note warn">%s</div>' % E(blocked)
    elif view.busy_browser:
        reason = '<div class="note">\u0110ang c\u00f3 vi\u1ec7c kh\u00e1c ch\u1ea1y. N\u00fat s\u1ebd d\u00f9ng \u0111\u01b0\u1ee3c khi n\u00f3 xong.</div>'
    else:
        reason = ""
    tags = "".join('<span class="tag">%s</span>' % E(t) for t in re.findall(r"#\w+", job["caption"]))
    approve = (
        '<button class="ghost" formaction="/decide" name="action" value="approve">✔ Duy\u1ec7t cho l\u1ecbch t\u1ef1 \u0111\u0103ng</button>'
        if job["state"] == "awaiting_approval"
        else ""
    )
    reset = (
        '<button class="ghost" formaction="/caption" name="action" value="reset">↺ D\u00f9ng m\u00f4 t\u1ea3 c\u1ee7a h\u1ec7 th\u1ed1ng</button>'
        if job["caption_edited"]
        else ""
    )
    return (
        '<form method="post" action="/task" class="card ready" data-id="%(id)s"><input type="hidden" name="csrf" value="%(csrf)s"><input type="hidden" name="id" value="%(id)s">'
        '<div class="media">%(media)s</div>'
        '<div class="body stack">'
        '<div class="row">%(plat)s%(state)s</div>'
        '<div class="ttl">%(title)s</div>'
        '<div class="muted small">%(score)s</div>'
        '<div class="facts">%(facts)s</div>%(why)s%(dest)s%(wait)s'
        '<label class="cap">M\u00f4 t\u1ea3 v\u00e0 hashtag s\u1ebd \u0111\u0103ng'
        '<textarea name="caption" rows="4" maxlength="2200" data-caption spellcheck="false">%(caption)s</textarea></label>'
        '<div class="row small"><span class="muted"><span data-len>%(length)d</span> k\u00fd t\u1ef1 · <span data-tags>%(ntags)d</span> hashtag%(edited)s</span></div>'
        '<div class="tags">%(chips)s</div>%(lint)s%(reason)s'
        '<div class="btns">'
        '%(approve)s<button class="go big" formaction="/task" name="kind" value="publish" data-confirm="%(confirm)s"%(dis)s>🚀 \u0110\u0103ng ngay</button>'
        '<button class="ghost" formaction="/task" name="kind" value="dryrun"%(dis)s>👁 Xem th\u1eed, kh\u00f4ng \u0111\u0103ng</button>'
        '<button class="ghost" formaction="/caption" name="action" value="save">💾 L\u01b0u m\u00f4 t\u1ea3</button>%(reset)s'
        '<button class="ghost danger" formaction="/decide" name="action" value="reject" data-confirm="B\u1ecf video n\u00e0y kh\u1ecfi danh s\u00e1ch \u0111\u0103ng?">🗑 B\u1ecf video</button>'
        "</div></div></form>"
    ) % {
        "id": E(job["id"]),
        "csrf": view.csrf,
        "media": video,
        "plat": platform_badge(job["platform"]),
        "state": state_chip(job["state"]),
        "title": E((job["title"] or "(kh\u00f4ng c\u00f3 ti\u00eau \u0111\u1ec1)")[:120]),
        "score": E(_score_line(meta_of(job))),
        "facts": _fact_chips(job, info),
        "why": '<div class="muted small">%s</div>' % E(info["why"]) if info.get("why") else "",
        "dest": _destination_line(view, job),
        "wait": _waiting_line(view, job),
        "caption": E(job["caption"]),
        "length": lint["length"],
        "ntags": lint["tags"],
        "edited": " · \u0111\u00e3 s\u1eeda tay" if job["caption_edited"] else "",
        "chips": tags,
        "lint": lint_html,
        "reason": reason,
        "confirm": E(_confirm_text(view, job)),
        "dis": disabled,
        "approve": approve,
        "reset": reset,
    }


def review_card(job, csrf):
    """A video the system held back, with the reason in plain words and the owner's choices."""
    retry = (
        '<button class="ghost" name="action" value="retry" title="Video \u0111\u00e3 d\u1ef1ng xong; \u0111\u01b0a v\u1ec1 danh s\u00e1ch s\u1eb5n s\u00e0ng \u0111\u0103ng">↩ \u0110\u01b0a v\u1ec1 s\u1eb5n s\u00e0ng \u0111\u0103ng</button>'
        if job.get("output_file")
        else ""
    )
    return (
        '<form method="post" action="/decide" class="card ready"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="id" value="%s">'
        '<div class="media"><video controls preload="none" playsinline src="/media/%s/source"></video></div>'
        '<div class="body stack"><div class="row">%s%s</div><div class="ttl">%s</div><div class="muted small">%s</div>'
        '<div class="note warn">L\u00fd do gi\u1eef l\u1ea1i: <b>%s</b></div>'
        '<div class="btns">%s<button class="go" name="action" value="approve" title="Ch\u1ea1y l\u1ea1i v\u00e0 b\u1ecf qua ki\u1ec3m tra ch\u1ee7 \u0111\u1ec1/\u0111\u1ed9 ch\u1eafc ch\u1eafn">Duy\u1ec7t l\u1ea1i, b\u1ecf qua ki\u1ec3m tra</button>'
        '<button class="ghost danger" name="action" value="reject">B\u1ecf</button></div></div></form>'
    ) % (
        csrf,
        E(job["id"]),
        E(job["id"]),
        platform_badge(job["platform"]),
        state_chip(job["state"]),
        headline(job, 120) or "(kh\u00f4ng c\u00f3 ti\u00eau \u0111\u1ec1)",
        E(_score_line(meta_of(job), with_views=False)),
        E(vi_reason(job["reason"])),
        retry,
    )
