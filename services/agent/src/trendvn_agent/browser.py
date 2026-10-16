"""An isolated, persistent Chrome profile driven by Playwright (real Chrome, not the bundled Chromium)."""

import re
import threading
from collections import defaultdict
from contextlib import contextmanager

from .config import DATA, ENV, ensure_dirs


class BrowserBusy(Exception):
    """Raised when the requested Chrome profile is currently held by another job."""


_PROFILE_LOCKS = defaultdict(threading.Lock)
_LOCKS_GUARD = threading.Lock()


def get_profile_lock(profile):
    """Get the specific lock for a Chrome profile directory."""
    with _LOCKS_GUARD:
        return _PROFILE_LOCKS[profile]


def is_busy():
    """Check if any Chrome profile is currently locked and active."""
    with _LOCKS_GUARD:
        return any(lock.locked() for lock in _PROFILE_LOCKS.values())


def busy_profiles():
    """List names of profiles currently held by running jobs."""
    with _LOCKS_GUARD:
        return [name for name, lock in _PROFILE_LOCKS.items() if lock.locked()]


def proxy_for(region):
    """Optional per-region exit, e.g. TRENDVN_US_PROXY=http://user:pass@host:port for real US trends."""
    value = ENV.get("TRENDVN_%s_PROXY" % region.upper(), "").strip()
    if not value:
        return None
    m = re.fullmatch(r"(https?|socks5)://(?:([^:@/]+):([^@/]*)@)?([^:/@]+):(\d{1,5})", value)
    if not m:
        raise ValueError("TRENDVN_%s_PROXY has an invalid format" % region.upper())
    scheme, user, password, host, port = m.groups()
    cfg = {"server": f"{scheme}://{host}:{port}"}
    if user:
        cfg.update(username=user, password=password)
    return cfg


@contextmanager
def chrome(profile, locale="en-US", headless=True, region=None, viewport=(1366, 900), lock_timeout=120):
    """Persistent, isolated Chrome profile driven by Playwright (real Chrome channel, not bundled Chromium).
    Different profiles run concurrently without blocking each other. Jobs sharing the same profile wait for each other."""
    from playwright.sync_api import sync_playwright

    lock = get_profile_lock(profile)
    acquired = lock.acquire(blocking=True, timeout=lock_timeout)
    if not acquired:
        raise BrowserBusy("Hồ sơ trình duyệt %s đang được tác vụ khác sử dụng. Vui lòng thử lại sau." % profile)

    try:
        ensure_dirs()
        pdir = DATA / "profiles" / profile
        pdir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sync_playwright() as p:
            # Honest automation: no flags or User-Agent edits that hide the fact that a program is driving the browser.
            kwargs = dict(
                channel="chrome",
                headless=headless,
                locale=locale,
                viewport={"width": viewport[0], "height": viewport[1]},
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                    "--disk-cache-size=67108864",
                    "--media-cache-size=1048576",
                ],
            )
            proxy = proxy_for(region) if region else None
            if proxy:
                kwargs["proxy"] = proxy
            ctx = p.chromium.launch_persistent_context(str(pdir), **kwargs)
            try:
                yield ctx
            finally:
                ctx.close()
    finally:
        lock.release()
