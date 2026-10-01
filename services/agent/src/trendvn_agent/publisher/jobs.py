"""What the schedule and the dashboard ask the publisher to do: post, rehearse, read stats, verify."""

from ..browser import chrome
from ..log import log
from ..worker_client import worker, worker_get
from .constants import HEADED
from .post import publish_one
from .profile import own_descriptions, profile_name
from .text import norm


def report_login(account, ok):
    """Tell the worker whether the browser is signed in to an account. Never raises: this is bookkeeping, not part of a post."""
    try:
        worker("/api/accounts/login", {"id": account or "main", "ok": bool(ok)})
    except Exception as error:
        log("could not report the login state: " + str(error)[:120])


def run_publish(job_id=None):
    """Claim one video from the worker and post it. Scheduled: the worker enforces switch, window, daily limit and spacing.
    With job_id (the dashboard's Post button) the owner's click is the consent and only the account-protecting rails apply."""
    claim = worker("/api/publish/claim", {"job_id": job_id} if job_id else {})
    if claim["status"] != "claimed":
        return claim
    outcome, url, reason = publish_one(claim, dry_run=False)
    # 'deferred' = nothing was posted and it is not this video's fault (verification, duplicate caption): not counted as a failure
    finish = {
        "published": "published",
        "duplicate": "duplicate",
        "unknown": "unknown",
        "deferred": "deferred",
        "challenge": "deferred",
        "signed_out": "deferred",  # not the video's fault either: nothing was posted
    }.get(outcome, "failed")
    if outcome == "challenge":
        worker("/api/publisher/challenge", {"active": True})
    if outcome == "signed_out":
        report_login(claim.get("account"), False)  # the schedule leaves this account alone until it is signed in again
    worker(
        "/api/publish/finish",
        {"id": claim["id"], "lease": claim["lease"], "outcome": finish, "url": url if url.startswith("https://") else "", "reason": reason},
    )
    return {"status": outcome, "id": claim["id"], "reason": reason, "url": url if url.startswith("https://") else ""}


def dry_run_next(job_id=None):
    """Rehearse a ready video (the next one, or the chosen one) without touching the switch: upload, caption, screenshot, stop."""
    st = worker("/api/publish/peek", {"job_id": job_id} if job_id else {})
    if st.get("status") != "ready":
        return st
    outcome, shot, reason = publish_one(st, dry_run=True)
    return {"status": outcome, "reason": reason, "screenshot": shot}


def _accounts():
    """(id, username) of every enabled account, as the worker knows them."""
    status = worker_get("/api/status")
    return [(a["id"], a["username"]) for a in status.get("accounts", []) if a["enabled"]] or [("main", status["target"])]


def run_stats():
    """Read views/likes of our posts from the public profile of every account and hand them to the worker (feeds the source weights)."""
    items, errors = [], []
    for account, username in _accounts():
        try:
            with chrome(profile_name(account), locale="vi-VN", headless=not HEADED) as ctx:
                posts = own_descriptions(ctx, username)
        except Exception as error:  # one account failing must not hide the others' numbers
            errors.append("@%s: %s" % (username, str(error)[:80]))
            continue
        items += [
            {
                "video_id": p["id"],
                "views": p["views"] or 0,
                "likes": p["likes"] or 0,
                "comments": p["comments"] or 0,
                "shares": p["shares"] or 0,
            }
            for p in posts
            if p["id"].isdigit()
        ]
    matched = 0
    for i in range(0, len(items), 200):  # the worker accepts 200 posts per call; a busy channel has more
        matched += worker("/api/stats", {"items": items[i : i + 200]}).get("matched", 0)
    result = {"read": len(items), "matched": matched}
    if errors:
        result["errors"] = errors
    return result


def verify_unresolved():
    """Resolve uncertain publishes by reading the public profile of the account each was posted to; never re-posts."""
    items = worker("/api/publish/unresolved", {})["items"]
    if not items:
        return {"resolved": 0}
    default = _accounts()[0]
    resolved = 0
    for account in sorted({job.get("account") or default[0] for job in items}):
        mine = [job for job in items if (job.get("account") or default[0]) == account]
        username = mine[0].get("target") or next((u for a, u in _accounts() if a == account), default[1])
        with chrome(profile_name(account), locale="vi-VN", headless=not HEADED) as ctx:
            posts = own_descriptions(ctx, username)
        for job in mine:
            key = norm(job.get("caption"))
            match = [p for p in posts if key and norm(p["desc"]) == key]
            if match:
                worker(
                    "/api/publish/resolve",
                    {"id": job["id"], "outcome": "published", "url": "https://www.tiktok.com/@%s/video/%s" % (username, match[0]["id"])},
                )
                resolved += 1
    return {"resolved": resolved, "still_unknown": len(items) - resolved}
