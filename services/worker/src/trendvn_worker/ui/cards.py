"""The two video cards: a rendered video ready to post, and a video held back for the owner to review."""

import re

from .components import chip, platform_badge, state_chip
from .format import escape as E, meta_of, num
from .labels import ROUTE_LABEL, vi_reason

CONFIRM_VISIBILITY = {"public": "CÔNG KHAI", "friends": "BẠN BÈ", "self": "CHỈ MÌNH TÔI"}


def _fact_chips(job, info):
    facts = []
    if info.get("w"):
        portrait_916 = info["h"] > info["w"] and abs(info["w"] / info["h"] - 9 / 16) < 0.03
        facts.append(chip("%d×%d%s" % (info["w"], info["h"], " · 9:16" if portrait_916 else ""), "good" if portrait_916 else "warn"))
    if info.get("duration"):
        facts.append(chip("%s giây" % info["duration"], "mute"))
    if info.get("size"):
        facts.append(chip("%.1f MB" % (info["size"] / 1e6), "mute"))
    facts.append(chip(ROUTE_LABEL.get(job["route"], job["route"] or ""), "info"))
    if info.get("reframed"):
        facts.append(chip("đã đưa vào khung dọc", "mute"))
    if info.get("hard_subs"):
        facts.append(chip("đã che phụ đề gốc", "mute"))
    if info.get("warning"):
        facts.append(chip(info["warning"], "warn"))
    return "".join(facts)


def _score_line(meta, with_views=True):
    parts = []
    if meta.get("score"):
        parts.append("điểm %s" % num(meta["score"]))
    if meta.get("likes"):
        parts.append("%s tim" % num(meta["likes"]))
    if with_views and meta.get("views"):
        parts.append("%s xem" % num(meta["views"]))
    if meta.get("age_h") is not None:
        parts.append("%.0f giờ tuổi" % meta["age_h"])
    return " · ".join(parts)


def _confirm_text(view):
    """The question asked before 'Đăng ngay': where it goes, how visible, and any rule the click overrides."""
    d, cfg = view.d, view.cfg
    warnings = []
    if d["published_today"] >= d["daily_limit"]:
        warnings.append("Hôm nay đã đăng đủ %d/%d bài, bạn vẫn muốn đăng thêm?" % (d["published_today"], d["daily_limit"]))
    if not d["in_window"]:
        warnings.append("Đang ngoài giờ vàng.")
    visibility = CONFIRM_VISIBILITY.get(cfg["visibility"], cfg["visibility"])
    return "Đăng video này lên @%s ngay bây giờ? Chế độ hiển thị: %s. %s" % (cfg["target"], visibility, " ".join(warnings))


def ready_card(job, view, blocked):
    """One rendered video: preview, editable caption and hashtags, quality facts, and the buttons to post it."""
    info = job.get("info") or {}
    lint = job["lint"]
    poster = ' poster="/media/%s/poster"' % E(job["id"]) if info.get("poster") else ""
    video = '<video controls preload="none" playsinline%s src="/media/%s/final"></video>' % (poster, E(job["id"]))
    if lint["ok"]:
        lint_html = '<div class="lint ok">✓ Mô tả tốt: %d ký tự, %d hashtag</div>' % (lint["length"], lint["tags"])
    else:
        lint_html = '<div class="lint warn">⚠ %s</div>' % E(" · ".join(lint["issues"]))
    disabled = " disabled" if (blocked or view.busy_browser) else ""
    if blocked:
        reason = '<div class="note warn">%s</div>' % E(blocked)
    elif view.busy_browser:
        reason = '<div class="note">Đang có việc khác chạy. Nút sẽ dùng được khi nó xong.</div>'
    else:
        reason = ""
    tags = "".join('<span class="tag">%s</span>' % E(t) for t in re.findall(r"#\w+", job["caption"]))
    approve = (
        '<button class="ghost" formaction="/decide" name="action" value="approve">✔ Duyệt cho lịch tự đăng</button>'
        if job["state"] == "awaiting_approval"
        else ""
    )
    reset = (
        '<button class="ghost" formaction="/caption" name="action" value="reset">↺ Dùng mô tả của hệ thống</button>'
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
        '<div class="facts">%(facts)s</div>%(why)s'
        '<label class="cap">Mô tả và hashtag sẽ đăng'
        '<textarea name="caption" rows="4" maxlength="2200" data-caption spellcheck="false">%(caption)s</textarea></label>'
        '<div class="row small"><span class="muted"><span data-len>%(length)d</span> ký tự · <span data-tags>%(ntags)d</span> hashtag%(edited)s</span></div>'
        '<div class="tags">%(chips)s</div>%(lint)s%(reason)s'
        '<div class="btns">'
        '%(approve)s<button class="go big" formaction="/task" name="kind" value="publish" data-confirm="%(confirm)s"%(dis)s>🚀 Đăng ngay</button>'
        '<button class="ghost" formaction="/task" name="kind" value="dryrun"%(dis)s>👁 Xem thử, không đăng</button>'
        '<button class="ghost" formaction="/caption" name="action" value="save">💾 Lưu mô tả</button>%(reset)s'
        '<button class="ghost danger" formaction="/decide" name="action" value="reject" data-confirm="Bỏ video này khỏi danh sách đăng?">🗑 Bỏ video</button>'
        "</div></div></form>"
    ) % {
        "id": E(job["id"]),
        "csrf": view.csrf,
        "media": video,
        "plat": platform_badge(job["platform"]),
        "state": state_chip(job["state"]),
        "title": E((job["title"] or "(không có tiêu đề)")[:120]),
        "score": E(_score_line(meta_of(job))),
        "facts": _fact_chips(job, info),
        "why": '<div class="muted small">%s</div>' % E(info["why"]) if info.get("why") else "",
        "caption": E(job["caption"]),
        "length": lint["length"],
        "ntags": lint["tags"],
        "edited": " · đã sửa tay" if job["caption_edited"] else "",
        "chips": tags,
        "lint": lint_html,
        "reason": reason,
        "confirm": E(_confirm_text(view)),
        "dis": disabled,
        "approve": approve,
        "reset": reset,
    }


def review_card(job, csrf):
    """A video the system held back, with the reason in plain words and the owner's choices."""
    retry = (
        '<button class="ghost" name="action" value="retry" title="Video đã dựng xong; đưa về danh sách sẵn sàng đăng">↩ Đưa về sẵn sàng đăng</button>'
        if job.get("output_file")
        else ""
    )
    return (
        '<form method="post" action="/decide" class="card ready"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="id" value="%s">'
        '<div class="media"><video controls preload="none" playsinline src="/media/%s/source"></video></div>'
        '<div class="body stack"><div class="row">%s%s</div><div class="ttl">%s</div><div class="muted small">%s</div>'
        '<div class="note warn">Lý do giữ lại: <b>%s</b></div>'
        '<div class="btns">%s<button class="go" name="action" value="approve" title="Chạy lại và bỏ qua kiểm tra chủ đề/độ chắc chắn">Duyệt lại, bỏ qua kiểm tra</button>'
        '<button class="ghost danger" name="action" value="reject">Bỏ</button></div></div></form>'
    ) % (
        csrf,
        E(job["id"]),
        E(job["id"]),
        platform_badge(job["platform"]),
        state_chip(job["state"]),
        E((job["title"] or "(không có tiêu đề)")[:120]),
        E(_score_line(meta_of(job), with_views=False)),
        E(vi_reason(job["reason"])),
        retry,
    )
