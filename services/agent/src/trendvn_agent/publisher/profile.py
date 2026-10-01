"""The signed-in account: is the session alive, and what is already on the profile."""

import json
import time

from ..log import log


def logged_in(ctx):
    return any(c["name"] == "sessionid" and "tiktok.com" in c["domain"] for c in ctx.cookies())


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
