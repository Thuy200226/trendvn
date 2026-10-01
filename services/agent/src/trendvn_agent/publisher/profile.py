"""The signed-in account: is the session alive, and what is already on the profile."""

import json
import re
import time

from ..log import log

MAIN_PROFILE = "publisher"  # the account of 1.0 - 1.3 keeps its signed-in profile
ACCOUNT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,23}")


def profile_name(account):
    """The Chrome profile folder of an account: one per TikTok account, so their sessions never mix."""
    if account in (None, "", "main"):
        return MAIN_PROFILE
    if not ACCOUNT_ID.fullmatch(str(account)):
        raise ValueError("Mã tài khoản không hợp lệ")
    return MAIN_PROFILE + "-" + account


def logged_in(ctx):
    return any(c["name"] == "sessionid" and "tiktok.com" in c["domain"] for c in ctx.cookies())


WHO_AM_I = """() => {
  const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
  if (!el) return null;
  try {
    const user = JSON.parse(el.textContent).__DEFAULT_SCOPE__['webapp.app-context'].user;
    return user && user.uniqueId ? String(user.uniqueId) : null;
  } catch (e) { return null; }
}"""


def signed_in_as(ctx):
    """The TikTok handle this browser profile is signed in as, read from the page's own data; None when it cannot be read. A profile
    that is signed in to a different account than the one a video is meant for must never post it."""
    page = ctx.new_page()
    try:
        page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        return page.evaluate(WHO_AM_I)
    except Exception as e:
        log("could not read the signed-in account: " + str(e)[:120])
        return None
    finally:
        page.close()


def wrong_account(ctx, expected):
    """A Vietnamese message when the profile is signed in as someone other than `expected`, else None (including when unreadable)."""
    who = signed_in_as(ctx)
    if who and who.lower() != str(expected).lower():
        return "Hồ sơ Chrome đang đăng nhập @%s, không phải @%s. Đăng nhập lại đúng tài khoản." % (who, expected)
    return None


def own_descriptions(ctx, target):
    """Captions already on the account (public profile), used to avoid re-posting the same idea."""
    page = ctx.new_page()
    seen = []

    def on_resp(r):
        try:
            if "/api/post/item_list" in r.url and r.status == 200:
                for it in json.loads(r.body()).get("itemList") or []:
                    st = it.get("stats") or {}
                    seen.append(
                        {
                            "id": str(it.get("id")),
                            "desc": it.get("desc") or "",
                            "views": st.get("playCount"),
                            "likes": st.get("diggCount"),
                            "comments": st.get("commentCount"),
                            "shares": st.get("shareCount"),
                        }
                    )
        except Exception:
            pass

    page.on("response", on_resp)
    try:
        page.goto("https://www.tiktok.com/@" + target, wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + 40  # the profile builds itself as slowly as Studio does; wait for the first video list
        while not seen and time.time() < deadline:
            page.wait_for_timeout(1500)
        for _ in range(3):
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(2000)
    except Exception as e:
        log("profile read warning: " + str(e)[:120])
    finally:
        page.close()
    return seen
