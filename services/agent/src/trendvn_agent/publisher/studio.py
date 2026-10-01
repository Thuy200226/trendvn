"""Steps on the Studio upload page: popups, upload progress, caption, visibility."""

import re
import time

from .constants import POPUP_BUTTONS, UPLOADED_HINTS, VISIBILITY_LABELS
from .text import norm


def dismiss_popups(page):
    """Close TikTok's tips and the 'automatic content checks' offer that cover the editor. Returns how many were closed."""
    closed = 0
    for _ in range(6):
        hit = False
        for name in POPUP_BUTTONS:
            try:
                b = page.get_by_role("button", name=re.compile("^" + name + "$"))
                if b.count() and b.first.is_visible():
                    b.first.click(timeout=5000)
                    page.wait_for_timeout(900)
                    hit = True
                    closed += 1
            except Exception:
                continue
        if not hit:
            break
    return closed


def wait_uploaded(page, seconds=240):
    """The upload status block reads 'Đã tải lên (size)' when TikTok has received the whole file."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            box = page.locator('[data-e2e="upload_status_container"]')
            if box.count() and any(h.lower() in box.first.inner_text().lower() for h in UPLOADED_HINTS):
                return True
        except Exception:
            pass
        page.wait_for_timeout(2000)
    return False


def set_caption(page, editor, caption):
    """Replace the pre-filled file name with our caption and confirm it really is there."""
    editor.click(timeout=15000)
    page.keyboard.press("Control+A")
    page.keyboard.press("Meta+A")
    page.keyboard.press("Delete")
    page.keyboard.type(caption, delay=25)
    page.wait_for_timeout(1200)
    shown = re.sub(r"\s+", " ", editor.inner_text()).strip()
    return norm(shown).startswith(norm(caption)[:25]) and "final" != shown


def set_visibility(page, wanted):
    """Pick who can see the post. 'public' is TikTok's default and is left untouched."""
    if wanted == "public" or wanted not in VISIBILITY_LABELS:
        return True
    labels = VISIBILITY_LABELS[wanted]
    box = page.locator('[data-e2e="video_visibility_container"]')
    box.locator('button, [role="combobox"], [role="button"]').first.click(timeout=10000)
    page.wait_for_timeout(800)
    for label in labels:
        opt = page.get_by_text(label, exact=True)
        if opt.count():
            opt.last.click(timeout=8000)
            page.wait_for_timeout(800)
            break
    return any(l in box.inner_text() for l in labels)


def studio_shows(ctx, caption, seconds=60):
    """Second opinion for posts the public profile cannot show (private or friends-only): TikTok Studio's own content list."""
    page = ctx.new_page()
    try:
        page.goto("https://www.tiktok.com/tiktokstudio/content", wait_until="domcontentloaded", timeout=60000)
        needle = re.sub(r"\s+", " ", caption).strip()[:25]
        deadline = time.time() + seconds
        while time.time() < deadline:
            if needle and needle in re.sub(r"\s+", " ", page.inner_text("body")):
                return True
            page.wait_for_timeout(2500)
    except Exception:
        pass
    finally:
        page.close()
    return False
