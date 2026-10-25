"""Post one video through TikTok Studio, conservatively: after the Post click anything unverified is "unknown"."""

import re
import time

from ..browser import chrome
from ..config import RUNTIME
from ..log import log
from .challenge import Challenge, wait_for_upload_ui
from .constants import HEADED, POST_LABELS, UPLOAD_URL
from .profile import account_flag, logged_in, own_descriptions, profile_name, wrong_account
from .screenshots import export_shot, shot
from .studio import dismiss_popups, set_caption, set_visibility, studio_shows, wait_uploaded
from .text import norm, sha256

POST_BUTTON_WAIT = 300  # seconds the Post button may stay disabled while TikTok processes the upload
CONFIRM_LABELS = ("Post now", "\u0110\u0103ng ngay")
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
            return (
                "unknown",
                "",
                "\u0110\u00e3 b\u1ea5m \u0110\u0103ng nh\u01b0ng g\u1eb7p l\u1ed7i khi x\u00e1c nh\u1eadn: " + str(e)[:140],
            )
        return (
            "failed",
            "",
            "Kh\u00f4ng ch\u1ea1y \u0111\u01b0\u1ee3c tr\u00ecnh duy\u1ec7t ho\u1eb7c l\u1ed7i tr\u01b0\u1edbc khi \u0111\u0103ng: "
            + str(e)[:160],
        )


def _publish_one(job, dry_run, state):
    video = RUNTIME / "jobs" / job["id"] / "final.mp4"
    if not video.is_file():
        return "failed", "", "Kh\u00f4ng th\u1ea5y file video \u0111\u00e3 d\u1ef1ng"
    if sha256(video) != job["output_hash"]:
        return "failed", "", "Hash video thay \u0111\u1ed5i sau khi d\u1ef1ng; kh\u00f4ng \u0111\u0103ng"
    with chrome(profile_name(job.get("account")), locale="vi-VN", headless=not HEADED, viewport=(1280, 1000)) as ctx:
        if not logged_in(ctx):
            return "signed_out", "", "Ch\u01b0a \u0111\u0103ng nh\u1eadp TikTok cho @%s trong h\u1ed3 s\u01a1 ri\u00eang" % job["target"]
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
        return (
            "deferred",
            "",
            "T\u00e0i kho\u1ea3n \u0111\u00e3 c\u00f3 b\u00e0i c\u00f3 m\u00f4 t\u1ea3 gi\u1ed1ng h\u1ec7t. H\u00e3y s\u1eeda m\u00f4 t\u1ea3 r\u1ed3i \u0111\u0103ng l\u1ea1i.",
        )
    return "duplicate", "", "T\u00e0i kho\u1ea3n \u0111\u00e3 c\u00f3 b\u00e0i c\u00f9ng n\u1ed9i dung m\u00f4 t\u1ea3"


def _post_in_studio(ctx, job, video, dry_run, state):
    """Upload, fill in and (unless dry_run) click Post. Returns the final (outcome, url, reason) when the attempt ended here,
    or None once Post was clicked and the result still has to be verified on the profile."""
    page = ctx.new_page()
    try:
        failure, target, post_button = _upload_and_fill(page, job, video)
        if failure:
            return failure
        if dry_run:
            return (
                "dry_run",
                export_shot(page, "dry_run"),
                "Ch\u1ea1y th\u1eed: \u0111\u00e3 t\u1ea3i video, \u0111i\u1ec1n m\u00f4 t\u1ea3, d\u1eebng tr\u01b0\u1edbc n\u00fat \u0110\u0103ng",
            )
        state["clicked"] = True
        post_button.click()
        _confirm_post(page)
        return None
    except Challenge as e:
        picture = shot(page, "challenge") or ""
        if state["clicked"]:
            return (
                "unknown",
                picture,
                "\u0110\u00e3 b\u1ea5m \u0110\u0103ng nh\u01b0ng TikTok \u0111\u00f2i x\u00e1c minh: ch\u01b0a bi\u1ebft b\u00e0i c\u00f3 l\u00ean kh\u00f4ng",
            )
        return (
            "challenge",
            picture,
            "%s. \u0110\u0103ng t\u1ea1m d\u1eebng t\u1edbi khi b\u1ea1n gi\u1ea3i: ./trendvn tiktok trust%s"
            % (e, account_flag(job.get("account"))),
        )
    except Exception as e:
        picture = shot(page, "error") or ""
        if state["clicked"]:
            return "unknown", picture, "\u0110\u00e3 b\u1ea5m \u0110\u0103ng nh\u01b0ng ch\u01b0a x\u00e1c nh\u1eadn: " + str(e)[:120]
        return "failed", picture, "L\u1ed7i tr\u01b0\u1edbc khi b\u1ea5m \u0110\u0103ng: " + str(e)[:160]
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
        return (
            (
                "signed_out",
                "",
                "Phi\u00ean \u0111\u0103ng nh\u1eadp TikTok \u0111\u00e3 h\u1ebft h\u1ea1n cho @%s" % job.get("target", "?"),
            ),
            None,
            None,
        )
    target, file_input = wait_for_upload_ui(page)
    if file_input is None:
        return (
            _failed(
                page,
                "no_file_input",
                "Kh\u00f4ng t\u00ecm th\u1ea5y \u00f4 ch\u1ecdn file; giao di\u1ec7n TikTok Studio c\u00f3 th\u1ec3 \u0111\u00e3 \u0111\u1ed5i",
            ),
            None,
            None,
        )
    file_input.set_input_files(str(video))
    editor = target.locator('[contenteditable="true"]').first
    editor.wait_for(timeout=180000)
    if not wait_uploaded(page):
        return _failed(page, "upload_slow", "TikTok ch\u01b0a nh\u1eadn xong video sau 4 ph\u00fat"), None, None
    dismiss_popups(page)
    if not set_caption(page, editor, job["caption"]):
        dismiss_popups(page)
        if not set_caption(page, editor, job["caption"]):
            return (
                _failed(
                    page,
                    "caption",
                    "Kh\u00f4ng \u0111i\u1ec1n \u0111\u01b0\u1ee3c m\u00f4 t\u1ea3 v\u00e0o \u00f4 nh\u1eadp c\u1ee7a TikTok",
                ),
                None,
                None,
            )
    if not set_visibility(page, job.get("visibility", "public")):
        return (
            _failed(
                page,
                "visibility",
                "Kh\u00f4ng ch\u1ecdn \u0111\u01b0\u1ee3c ch\u1ebf \u0111\u1ed9 hi\u1ec3n th\u1ecb; d\u1eebng \u0111\u1ec3 kh\u00f4ng \u0111\u0103ng sai \u0111\u1ed1i t\u01b0\u1ee3ng",
            ),
            None,
            None,
        )
    dismiss_popups(page)
    post_button = _wait_for_post_button(page, target)
    if post_button is None:
        return (
            _failed(
                page,
                "post_disabled",
                "N\u00fat \u0110\u0103ng ch\u01b0a s\u1eb5n s\u00e0ng (video ch\u01b0a t\u1ea3i xong ho\u1eb7c b\u1ecb ch\u1eb7n)",
            ),
            None,
            None,
        )
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
            return (
                "published",
                "https://www.tiktok.com/@%s/video/%s" % (job["target"], fresh[0]["id"]),
                "\u0110\u00e3 x\u00e1c nh\u1eadn tr\u00ean h\u1ed3 s\u01a1",
            )
        if job.get("visibility", "public") != "public" and studio_shows(ctx, job["caption"]):
            return (
                "published",
                "",
                "\u0110\u00e3 x\u00e1c nh\u1eadn trong trang n\u1ed9i dung c\u1ee7a TikTok Studio (b\u00e0i kh\u00f4ng c\u00f4ng khai n\u00ean ch\u01b0a c\u00f3 tr\u00ean h\u1ed3 s\u01a1)",
            )
        time.sleep(45)
    return (
        "unknown",
        "",
        "\u0110\u00e3 b\u1ea5m \u0110\u0103ng nh\u01b0ng ch\u01b0a th\u1ea5y b\u00e0i tr\u00ean h\u1ed3 s\u01a1 c\u00f4ng khai (c\u00f3 th\u1ec3 \u0111ang ch\u1edd duy\u1ec7t)",
    )
