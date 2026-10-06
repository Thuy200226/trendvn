"""Post one video through TikTok Studio, conservatively: after the Post click anything unverified is "unknown"."""

import re
import time

from ..browser import chrome
from ..config import RUNTIME
from ..log import log
from .challenge import Challenge, wait_for_upload_ui
from .constants import HEADED, POST_LABELS, UPLOAD_URL
from .profile import account_flag, logged_in, own_descriptions, profile_name, wrong_account, signed_in_as
from .screenshots import export_shot, shot
from .studio import dismiss_popups, set_caption, set_visibility, studio_shows, wait_uploaded
from .text import norm, sha256

POST_BUTTON_WAIT = 300  # seconds the Post button may stay disabled while TikTok processes the upload
CONFIRM_LABELS = ("Post now", "Đăng ngay")
PROFILE_CHECKS = 4  # how many times the public profile is read after posting, 45 s apart


def publish_one(job, dry_run=True):
    """Never raises. Returns (outcome, url, reason) with outcome in published|failed|deferred|challenge|signed_out|unknown|duplicate|dry_run.
    Any error before the Post button is clicked is 'failed' (nothing was posted); after the click it is always 'unknown'."""
    state = {"clicked": False}
    try:
        return _publish_one(job, dry_run, state)
    except Exception as e:
        log("publish error: %s" % str(e)[:200])
        if state["clicked"]:
            return "unknown", "", "Đã bấm Đăng nhưng gặp lỗi khi xác nhận: " + str(e)[:140]
        return "failed", "", "Không chạy được trình duyệt hoặc lỗi trước khi đăng: " + str(e)[:160]


def _publish_one(job, dry_run, state):
    video = RUNTIME / "jobs" / job["id"] / "final.mp4"
    if not video.is_file():
        return "failed", "", "Không thấy file video đã dựng"
    if sha256(video) != job["output_hash"]:
        return "failed", "", "Hash video thay đổi sau khi dựng; không đăng"
    with chrome(profile_name(job.get("account")), locale="vi-VN", headless=not HEADED, viewport=(1280, 1000)) as ctx:
        if not logged_in(ctx):
            return "signed_out", "", "Chưa đăng nhập TikTok cho @%s trong hồ sơ riêng" % job["target"]
        if job.get("search_account"):  # a video found for one account is only ever posted on that account
            who = signed_in_as(ctx)
            if not who or who.casefold() != job["target"].casefold():
                return "signed_out", "", "Không xác minh được đúng tài khoản đã chọn; dừng đăng"
        mismatch = wrong_account(ctx, job["target"])
        if mismatch:
            return "signed_out", "", mismatch
        existing = own_descriptions(ctx, job["target"])
        refusal = _duplicate_refusal(job, existing)
        if refusal:
            return refusal
        result = _post_in_studio(ctx, job, video, dry_run, state)
        if result:
            return result
        return _confirm_on_profile(ctx, job, {e["id"] for e in existing})


def _duplicate_refusal(job, existing):
    """An (outcome, url, reason) when the account already carries a post with exactly this caption, else None."""
    key = norm(job["caption"])
    if not key or not any(norm(e["desc"]) == key for e in existing):
        return None
    if job.get("manual"):  # the owner chose this video: let them edit the caption instead of discarding it
        return "deferred", "", "Tài khoản đã có bài có mô tả giống hệt. Hãy sửa mô tả rồi đăng lại."
    return "duplicate", "", "Tài khoản đã có bài cùng nội dung mô tả"


def _post_in_studio(ctx, job, video, dry_run, state):
    """Upload, fill in and (unless dry_run) click Post. Returns the final (outcome, url, reason) when the attempt ended here,
    or None once Post was clicked and the result still has to be verified on the profile."""
    page = ctx.new_page()
    try:
        failure, target, post_button = _upload_and_fill(page, job, video)
        if failure:
            return failure
        if dry_run:
            return "dry_run", export_shot(page, "dry_run"), "Chạy thử: đã tải video, điền mô tả, dừng trước nút Đăng"
        state["clicked"] = True
        post_button.click()
        _confirm_post(page)
        return None
    except Challenge as e:
        picture = shot(page, "challenge") or ""
        if state["clicked"]:
            return "unknown", picture, "Đã bấm Đăng nhưng TikTok đòi xác minh: chưa biết bài có lên không"
        return "challenge", picture, "%s. Đăng tạm dừng tới khi bạn giải: ./trendvn tiktok trust%s" % (e, account_flag(job.get("account")))
    except Exception as e:
        picture = shot(page, "error") or ""
        if state["clicked"]:
            return "unknown", picture, "Đã bấm Đăng nhưng chưa xác nhận: " + str(e)[:120]
        return "failed", picture, "Lỗi trước khi bấm Đăng: " + str(e)[:160]
    finally:
        page.close()


def _failed(page, name, reason):
    return "failed", shot(page, name) or "", reason


def _upload_and_fill(page, job, video):
    """Open the upload page, send the file, write the caption and visibility. Returns (failure, target, post button):
    failure is an (outcome, url, reason) tuple, or None when the Post button is ready."""
    page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    if "/login" in page.url:  # the session ended: the account's trouble, not the video's (see publish_one's callers)
        return ("signed_out", "", "Phiên đăng nhập TikTok đã hết hạn cho @%s" % job.get("target", "?")), None, None
    target, file_input = wait_for_upload_ui(page)
    if file_input is None:
        return _failed(page, "no_file_input", "Không tìm thấy ô chọn file; giao diện TikTok Studio có thể đã đổi"), None, None
    file_input.set_input_files(str(video))
    editor = target.locator('[contenteditable="true"]').first
    editor.wait_for(timeout=180000)
    if not wait_uploaded(page):
        return _failed(page, "upload_slow", "TikTok chưa nhận xong video sau 4 phút"), None, None
    dismiss_popups(page)
    if not set_caption(page, editor, job["caption"]):
        dismiss_popups(page)
        if not set_caption(page, editor, job["caption"]):
            return _failed(page, "caption", "Không điền được mô tả vào ô nhập của TikTok"), None, None
    if not set_visibility(page, job.get("visibility", "public")):
        return _failed(page, "visibility", "Không chọn được chế độ hiển thị; dừng để không đăng sai đối tượng"), None, None
    dismiss_popups(page)
    post_button = _wait_for_post_button(page, target)
    if post_button is None:
        return _failed(page, "post_disabled", "Nút Đăng chưa sẵn sàng (video chưa tải xong hoặc bị chặn)"), None, None
    return None, target, post_button


def _wait_for_post_button(page, target):
    deadline = time.time() + POST_BUTTON_WAIT
    while time.time() < deadline:
        for candidate in (target.locator('[data-e2e="post_video_button"]'), target.get_by_role("button", name=POST_LABELS)):
            if candidate.count() and candidate.first.is_enabled():
                return candidate.first
        page.wait_for_timeout(2000)
    return None


def _confirm_post(page):
    """After the Post click: accept TikTok's confirmation dialog if one appears, then wait for the upload page to close."""
    page.wait_for_timeout(3000)
    for label in CONFIRM_LABELS:
        confirm = page.get_by_role("button", name=re.compile("^" + label + "$", re.I))
        if confirm.count():
            confirm.first.click()
            break
    for _ in range(30):  # TikTok leaves the upload page once it accepted the post
        if "tiktokstudio/upload" not in page.url:
            break
        page.wait_for_timeout(2000)
    page.wait_for_timeout(5000)


def _confirm_on_profile(ctx, job, before_ids):
    """The new caption must appear on the public profile with an id that was not there before posting."""
    key = norm(job["caption"])
    for _ in range(PROFILE_CHECKS):
        after = own_descriptions(ctx, job["target"])
        fresh = [e for e in after if e["id"] not in before_ids and norm(e["desc"]) == key]
        if fresh:
            return "published", "https://www.tiktok.com/@%s/video/%s" % (job["target"], fresh[0]["id"]), "Đã xác nhận trên hồ sơ"
        if job.get("visibility", "public") != "public" and studio_shows(ctx, job["caption"]):
            return "published", "", "Đã xác nhận trong trang nội dung của TikTok Studio (bài không công khai nên chưa có trên hồ sơ)"
        time.sleep(45)
    return "unknown", "", "Đã bấm Đăng nhưng chưa thấy bài trên hồ sơ công khai (có thể đang chờ duyệt)"
