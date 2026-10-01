"""An isolated, persistent Chrome profile driven by Playwright (real Chrome, not the bundled Chromium)."""

import re
from contextlib import contextmanager

from .config import DATA, ENV, ensure_dirs


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
def chrome(profile, locale="en-US", headless=True, region=None, viewport=(1366, 900)):
    """Persistent, isolated Chrome profile driven by Playwright (real Chrome channel, not bundled Chromium)."""
    from playwright.sync_api import sync_playwright

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
            args=["--no-first-run", "--no-default-browser-check"],
        )
        proxy = proxy_for(region) if region else None
        if proxy:
            kwargs["proxy"] = proxy
        ctx = p.chromium.launch_persistent_context(str(pdir), **kwargs)
        try:
            yield ctx
        finally:
            ctx.close()
