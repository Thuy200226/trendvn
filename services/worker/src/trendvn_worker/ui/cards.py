"""The two video cards: a rendered video ready to post, and a video held back for the owner to review."""

import re

from ..domain import topics
from ..domain.accounts import account_flag
from .components import chip, platform_badge, state_chip
from .format import escape as E, headline, left_text, meta_of, num
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
    if info.get("voice"):
        facts.append(chip("giọng " + str(info["voice"]), "info"))
    if info.get("hard_subs_blurred"):
        facts.append(chip("làm mờ phụ đề gốc khi có phụ đề Việt", "mute"))
    elif info.get("hard_subs"):
        facts.append(chip("phụ đề gốc giữ nguyên", "mute"))
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


FAILED_REST_SECONDS = 3600  # the scheduler skips a video that failed to post this recently (store/publishing.py::_best_ready_video)


def _destination_line(view, job):
    """Which topic the video is about and which accounts take it; says so when none does."""
    if job.get("search_account"):
        account = view.destination(None, job["search_account"])
        text = (
            "Tài khoản đã chọn: @" + meta_of(job).get("search_username", account["username"])
            if account
            else "Tài khoản đã chọn đang tắt hoặc đã bị xóa; cần xử lý trước khi đăng"
        )
        return '<div class="note small">%s</div>' % E(text)
    topic = job.get("topic")
    if len(view.d.get("accounts", [])) < 2 and not topic:
        return ""
    label = topics.label(topic) if topic else "chưa phân loại"
    takers = view.takers(topic)
    if takers:
        names = ", ".join("@" + a["username"] for a in takers)
        return '<div class="muted small">Chủ đề: <b>%s</b> · %s <b>%s</b></div>' % (
            E(label),
            "lịch tự động đăng lên" if len(takers) == 1 else "lịch tự động chọn một trong",
            E(names),
        )
    default = view.destination(topic)
    return (
        '<div class="note warn small">Chủ đề <b>%s</b> chưa có tài khoản nào nhận. Lịch tự động sẽ không đăng; nút Đăng ngay dùng @%s.</div>'
        % (
            E(label),
            E(default["username"] if default else view.cfg["target"]),
        )
    )


def _confirm_text(view, job):
    """The question asked before 'Đăng ngay': where it goes, how visible, and any rule the click overrides."""
    d, cfg = view.d, view.cfg
    account = view.destination(job.get("topic"), job.get("search_account"))
    warnings = []
    # the rules that apply are the account's own (its limit, its golden hours), not the channel's totals
    today, limit, inside = (
        (account["published_today"], account["daily_limit"], account["in_window"])
        if account
        else (d["published_today"], d["daily_limit"], d["in_window"])
    )
    if today >= limit:
        warnings.append("Hôm nay đã đăng đủ %d/%d bài, bạn vẫn muốn đăng thêm?" % (today, limit))
    if not inside:
        warnings.append("Đang ngoài giờ vàng.")
    shown = account["visibility"] if account else cfg["visibility"]
    visibility = CONFIRM_VISIBILITY.get(shown, shown)
    return "Đăng video này lên @%s ngay bây giờ? Chế độ hiển thị: %s. %s" % (
        account["username"] if account else cfg["target"],
        visibility,
        " ".join(warnings),
    )


def _account_hold(view, account):
    """What keeps the schedule from posting on this account right now (from the dashboard's numbers, the same order the scheduler checks
    them in), or None when nothing does."""
    name = "@" + account["username"]
    if account.get("logged_in") is False:
        return "%s chưa đăng nhập TikTok (./trendvn tiktok login%s)" % (name, account_flag(account["id"]))
    if view.unconfirmed_for(account):
        return "%s có bài đăng chưa xác nhận (xử lý ở tab Cần xem)" % name
    if not account.get("in_window", True):
        return "%s ngoài giờ vàng, lần tới %s" % (name, account.get("next_window") or "?")
    if account["published_today"] >= account["daily_limit"]:
        return "%s đã đăng đủ %d/%d bài hôm nay" % (name, account["published_today"], account["daily_limit"])
    wait = (account.get("next_post_at") or 0) - view.now
    if wait > 0:
        return "%s phải giãn cách giữa hai bài, còn %s" % (name, left_text(wait))
    return None


def _everyone_hold(view, job):
    """What holds this video back whichever account would post it: a verification pause, a post in flight, a recent failure of this video."""
    if view.challenge_on:
        return "TikTok đang đòi xác minh (đăng tạm dừng cho tới khi bạn giải)"
    if view.counts.get("publishing", 0):
        return "một bài khác đang được đăng"
    failed = job.get("last_publish_fail")
    if failed and view.now - failed < FAILED_REST_SECONDS:
        return "lần đăng trước lỗi nên video này nghỉ %s trước khi thử lại" % left_text(FAILED_REST_SECONDS - (view.now - failed))
    return None


def _waiting_line(view, job):
    """Why the schedule has not posted this video yet, in words (the scheduler itself only tells n8n, in English)."""
    if job["state"] == "awaiting_approval":
        text = "Chờ bạn duyệt: duyệt xong thì lịch mới đăng video này."
    elif not view.d["publisher_enabled"]:
        text = "Công tắc Tự đăng đang tắt nên lịch chưa đăng video nào. Bật ở tab Tổng quan."
    else:
        takers = [view.destination(None, job["search_account"])] if job.get("search_account") else view.takers(job.get("topic"))
        takers = [a for a in takers if a]
        if not takers:
            return ""  # the destination line says that no account takes this topic
        everyone = _everyone_hold(view, job)
        holds = [everyone] if everyone else [_account_hold(view, a) for a in takers]
        if None in holds:
            text = "Sẵn sàng: lịch sẽ đăng ở lần kiểm tra lịch kế tiếp nếu tới lượt."
        else:
            text = "Chưa đăng vì: " + "; ".join(holds) + "."
    return '<div class="note small wait">%s</div>' % E(text)


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
        '<div class="facts">%(facts)s</div>%(why)s%(dest)s%(wait)s'
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
        "dest": _destination_line(view, job),
        "wait": _waiting_line(view, job),
        "caption": E(job["caption"]),
        "length": lint["length"],
        "ntags": lint["tags"],
        "edited": " · đã sửa tay" if job["caption_edited"] else "",
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
        headline(job, 120) or "(không có tiêu đề)",
        E(_score_line(meta_of(job), with_views=False)),
        E(vi_reason(job["reason"])),
        retry,
    )
