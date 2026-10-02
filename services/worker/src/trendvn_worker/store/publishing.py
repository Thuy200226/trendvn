"""Publishing: claim a rendered video, record the outcome, and the safety rails around the account."""

import json
import time
import uuid

from ..domain.accounts import accepts, effective
from ..domain.captions import build_caption
from ..domain.platforms import valid_post_url


class PublishingMixin:
    """Everything between "a video is ready" and "it is on TikTok"."""

    def published_today(self, db=None, now=None, account=None):
        """Posts made today (confirmed, in flight or unconfirmed): on one account, or on all of them."""
        start = self.day_start(now)
        q = "SELECT count(*) FROM jobs WHERE state IN ('published','publishing','publish_unknown') AND COALESCE(published_at,updated)>=?"
        args = [start]
        if account is not None:
            q += " AND COALESCE(account,?)=?"
            args += [self._default_id(), account["id"]]
        if db is not None:
            return db.execute(q, args).fetchone()[0]
        with self.connect() as c:
            return c.execute(q, args).fetchone()[0]

    def _default_id(self):
        default = self.default_account()
        return default["id"] if default else "main"

    def publish_claim(self, now=None, job_id=None):
        """Reserve a rendered video for publishing on one of the accounts.
        Scheduled use (job_id=None): honours the switch and, for each account, its posting window, daily limit and spacing; the account
        that posted longest ago goes first and gets the best-scored video among the topics it takes.
        Manual use (job_id given, from the dashboard button): the owner's click is the consent for that one video, so the switch,
        window, limit, spacing and topic are waived; the safety rails that protect the account (one post in flight, unconfirmed posts,
        TikTok verification pause) still apply."""
        now = now or time.time()
        cfg = self.settings()
        manual = job_id is not None
        if not manual and not cfg["publisher_enabled"]:
            return {"status": "disabled", "reason": "Publishing switch is off"}
        if cfg.get("publisher_challenge"):
            return {"status": "blocked", "reason": "TikTok is asking for human verification; solve it once with `./trendvn tiktok trust`"}
        with self.transaction() as db:
            accounts = self._accounts_in(db, enabled_only=True)  # read under the lock: an account deleted a moment ago must not get a post
            if not accounts:
                return {"status": "blocked", "reason": "Chưa có tài khoản TikTok nào đang bật"}
            if db.execute("SELECT count(*) FROM jobs WHERE state='publishing'").fetchone()[0]:
                return {"status": "blocked", "reason": "A previous publish is unconfirmed; resolve it before publishing again"}
            if manual:
                row = self._chosen_video(db, job_id)
                if not row:
                    return {"status": "idle", "reason": "Video này không còn ở trạng thái sẵn sàng đăng"}
                account = self._account_for_manual(db, row, accounts, now)
                if self._unconfirmed(db, account):
                    return {"status": "blocked", "reason": "A previous publish is unconfirmed; resolve it before publishing again"}
                return self._reserve(db, row, account, cfg, now, manual)
            return self._claim_scheduled(db, accounts, cfg, now)

    def _claim_scheduled(self, db, accounts, cfg, now):
        """Try the accounts in turn: first those that did not just fail, then the one that posted longest ago. The first with room and a
        fitting video gets it. Accounts the browser is known not to be signed in to are skipped. When none gets a video the answer is the
        most useful reason: the soonest opening of an account that has a video waiting; else "no video is waiting" if some account had
        room; else (everyone is held back and nothing waits) the soonest opening."""
        logins = self.login_map(cfg)
        held_with_video, held_without, has_room = [], [], False
        ordered = sorted(accounts, key=lambda a: (self._failed_lately(db, a, now), self._last_post(db, a) or 0))
        for account in ordered:
            row = self._best_ready_video(db, account, now)
            if logins.get(account["id"]) is False:
                refusal = {
                    "status": "blocked",
                    "reason": "Chưa đăng nhập TikTok cho @%s: ./trendvn tiktok login --account %s" % (account["username"], account["id"]),
                }
            elif self._unconfirmed(db, account):
                refusal = {"status": "blocked", "reason": "A previous publish is unconfirmed; resolve it before publishing again"}
            else:
                refusal = self._schedule_refusal(db, account, cfg, now)
            if refusal:
                (held_with_video if row else held_without).append(refusal)
            elif row:
                return self._reserve(db, row, account, cfg, now, False)
            else:
                has_room = True
        soonest = lambda refusals: min(refusals, key=lambda r: (r["status"] == "blocked", r.get("retry_after", 0)))  # noqa: E731
        if held_with_video:
            return soonest(held_with_video)
        if has_room:
            return {"status": "idle", "reason": "No rendered video is waiting"}
        return soonest(held_without)

    def _failed_lately(self, db, account, now):
        """1 if a post on this account failed in the last half hour, so the other accounts get their turn first (a broken account must not
        use up every tick), else 0."""
        last = db.execute(
            "SELECT max(last_publish_fail) FROM jobs WHERE COALESCE(account,?)=?", (self._default_id(), account["id"])
        ).fetchone()[0]
        return 1 if last and now - last < 1800 else 0

    def _last_post(self, db, account):
        return db.execute(
            "SELECT max(published_at) FROM jobs WHERE state='published' AND COALESCE(account,?)=?", (self._default_id(), account["id"])
        ).fetchone()[0]

    def _unconfirmed(self, db, account):
        """Is a post of this account waiting to be confirmed (it may or may not be on TikTok)?"""
        return db.execute(
            "SELECT count(*) FROM jobs WHERE state='publish_unknown' AND COALESCE(account,?)=?", (self._default_id(), account["id"])
        ).fetchone()[0]

    def _schedule_refusal(self, db, account, cfg, now):
        """Why the schedule may not post on this account right now (outside its golden hours, daily limit, spacing), or None."""
        eff = effective(account, cfg)
        inside, opening = self.window_state({**cfg, "post_windows": eff["windows"]}, now)
        if not inside:
            return {"status": "wait", "reason": "Ngoài giờ vàng; lần tới lúc " + opening, "next_window": opening}
        if self.published_today(db, now, account) >= eff["daily_limit"]:
            return {"status": "limit", "reason": "Daily limit reached"}
        last = self._last_post(db, account)
        if last and now - last < eff["min_gap"]:
            return {"status": "wait", "reason": "Minimum gap between posts not reached", "retry_after": int(last + eff["min_gap"] - now)}
        return None

    @staticmethod
    def _best_ready_video(db, account, now):
        """The highest-scored rendered video this account takes, skipping any that failed to post within the last hour."""
        rows = db.execute(
            "SELECT * FROM jobs WHERE state='ready' AND output_file IS NOT NULL AND COALESCE(last_publish_fail,0)<? "
            "ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen",
            (now - 3600,),
        )
        return next((row for row in rows if accepts(account, row["topic"])), None)

    @staticmethod
    def _chosen_video(db, job_id):
        return db.execute(
            "SELECT * FROM jobs WHERE id=? AND state IN ('ready','awaiting_approval') AND output_file IS NOT NULL", (job_id,)
        ).fetchone()

    def _account_for_manual(self, db, row, accounts, now):
        """The account a hand-picked video goes to: one that takes its topic (not one known to be signed out, then the one with the fewest
        posts today), else the default account."""
        fitting = [a for a in accounts if accepts(a, row["topic"])]
        if not fitting:
            return accounts[0]
        logins = self.login_map(self.settings())
        return min(fitting, key=lambda a: (logins.get(a["id"]) is False, self.published_today(db, now, a)))

    def _reserve(self, db, row, account, cfg, now, manual):
        """Mark the video as being published (with a lease the agent must present when it reports back) and return the claim."""
        token = uuid.uuid4().hex
        db.execute(
            "UPDATE jobs SET state='publishing',publish_lease=?,prev_state=?,account=?,target=?,updated=? WHERE id=?",
            (token, row["state"], account["id"], account["username"], now, row["id"]),
        )
        self.event(db, row["id"], "publishing", ("thủ công " if manual else "") + "@" + account["username"])
        analysis = json.loads(row["analysis"]) if row["analysis"] else {}
        caption = row["caption_user"] or build_caption(analysis, row["title"])
        db.execute("UPDATE jobs SET caption=? WHERE id=?", (caption, row["id"]))
        return {
            "status": "claimed",
            "id": row["id"],
            "lease": token,
            "caption": caption,
            "route": row["route"],
            "manual": manual,
            "output_file": row["output_file"],
            "output_hash": row["output_hash"],
            "account": account["id"],
            "target": account["username"],
            "visibility": effective(account, cfg)["visibility"],
        }

    def publish_peek(self, job_id=None):
        """A rendered video for rehearsals (the next one, or a chosen one); changes nothing and ignores the publishing switch."""
        cfg = self.settings()
        accounts = self.accounts(enabled_only=True)
        with self.connect() as db:
            if job_id:
                row = self._chosen_video(db, job_id)
            else:
                row = db.execute(
                    "SELECT * FROM jobs WHERE state='ready' AND output_file IS NOT NULL ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT 1"
                ).fetchone()
            if not row or not accounts:
                return {"status": "idle", "reason": "No rendered video is waiting"}
            account = self._account_for_manual(db, row, accounts, time.time())
        a = json.loads(row["analysis"]) if row["analysis"] else {}
        return {
            "status": "ready",
            "id": row["id"],
            "caption": row["caption_user"] or build_caption(a, row["title"]),
            "route": row["route"],
            "output_file": row["output_file"],
            "output_hash": row["output_hash"],
            "account": account["id"],
            "target": account["username"],
            "visibility": effective(account, cfg)["visibility"],
        }

    def publish_finish(self, jid, lease, outcome, url="", reason=""):
        """outcome: published (confirmed on the account), failed (nothing was posted; counted), deferred (nothing was posted and it is
        not the video's fault, e.g. TikTok verification; not counted), unknown (may have posted), duplicate."""
        states = {"published": "published", "failed": "ready", "deferred": "ready", "unknown": "publish_unknown", "duplicate": "duplicate"}
        if outcome not in states:
            raise ValueError("Invalid publish outcome")
        if url and not valid_post_url(url):
            raise ValueError("Invalid publish URL")
        parked = False
        with self.transaction() as db:
            row = db.execute("SELECT attempts,publish_lease,state,prev_state,publish_fails FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["state"] != "publishing" or row["publish_lease"] != lease:
                raise ValueError("Stale publish lease")
            now = time.time()
            state = states[outcome]
            fails, last_fail = row["publish_fails"] or 0, None
            if outcome in ("failed", "deferred") and row["prev_state"] == "awaiting_approval":
                state = "awaiting_approval"  # a failed manual click must not silently approve the video for the scheduler
            if outcome == "failed":
                fails, last_fail = fails + 1, now
                if fails >= 3:
                    state, parked = "needs_review", True  # a video that keeps failing stops blocking the queue
                    reason = "Đăng thất bại %d lần liên tiếp, cần bạn xem: %s" % (fails, reason)
            db.execute(
                "UPDATE jobs SET state=?,publish_lease=NULL,publish_url=?,reason=?,published_at=?,updated=?,publish_fails=?,last_publish_fail=COALESCE(?,last_publish_fail) WHERE id=?",
                (state, url or None, reason[:700], now if outcome == "published" else None, now, fails, last_fail, jid),
            )
            self.event(db, jid, "publish_" + outcome, reason)
            title = (db.execute("SELECT title FROM jobs WHERE id=?", (jid,)).fetchone() or ["?"])[0][:60]
        if outcome == "published":
            self.emit("published", "✅ Đã đăng: %s\n%s" % (title, url), jid)
        elif outcome == "unknown":
            self.emit("urgent", "🚨 Đã bấm Đăng nhưng chưa xác nhận được: %s\nHệ thống dừng đăng. %s" % (title, reason), jid)
        elif parked:
            self.emit("review", "⚠️ Video đăng lỗi nhiều lần, đã chuyển sang Cần xem: %s\n%s" % (title, reason), jid)
        elif outcome == "failed":
            self.emit("publish_failed", "⚠️ Đăng chưa thành công (sẽ thử lại sau): %s" % reason, "publish_failed")

    def set_challenge(self, active):
        """TikTok asked for human verification. Publishing pauses (no retries that would keep triggering it) until the owner clears it."""
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("publisher_challenge", json.dumps(bool(active))))
            self.event(db, "", "challenge_on" if active else "challenge_off", "")
        if active:
            self.emit(
                "urgent",
                "🧩 TikTok đang yêu cầu xác minh (CAPTCHA). Đăng bài tạm dừng. Hãy giải một lần: chạy `./trendvn tiktok trust` (Mac: nhấp đúp macos/Xac-minh-TikTok.command).",
                "challenge",
            )

    def resolve_unknown(self, jid, outcome, url=""):
        """Operator/agent verified the account: mark an uncertain publish as published or as not posted."""
        if outcome not in ("published", "failed"):
            raise ValueError("Invalid outcome")
        if url and not valid_post_url(url):
            raise ValueError("Invalid publish URL")  # the link is shown on the dashboard: only a TikTok https link is accepted
        with self.transaction() as db:
            row = db.execute("SELECT state,prev_state FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["state"] != "publish_unknown":
                raise ValueError("Job is not awaiting confirmation")
            now = time.time()
            back = "awaiting_approval" if row["prev_state"] == "awaiting_approval" else "ready"
            db.execute(
                "UPDATE jobs SET state=?,publish_url=?,published_at=?,reason=?,updated=? WHERE id=?",
                (
                    "published" if outcome == "published" else back,
                    url or None,
                    now if outcome == "published" else None,
                    "Confirmed by account check",
                    now,
                    jid,
                ),
            )
            self.event(db, jid, "resolved_" + outcome)

    def unresolved(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,title,caption,updated,account,target FROM jobs WHERE state='publish_unknown'")]
