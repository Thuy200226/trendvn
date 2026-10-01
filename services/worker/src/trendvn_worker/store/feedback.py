"""Feedback loop: views and likes of what we posted, and how they re-weight the sources."""

import re
import time

from ..domain.platforms import PLATFORMS


class FeedbackMixin:
    """Post performance read back from the TikTok profile."""

    # ------------------------------------------------------------------ feedback loop
    def record_stats(self, items):
        """Views/likes read from our own TikTok profile, matched to jobs by the video id in publish_url."""
        if not isinstance(items, list) or len(items) > 200:
            raise ValueError("items must be a list of at most 200")
        now, matched = time.time(), 0
        with self.transaction() as db:
            for it in items:
                vid = str(it.get("video_id", ""))
                if not re.fullmatch(r"\d{6,25}", vid):
                    continue
                nums = []
                for k in ("views", "likes", "comments", "shares"):
                    v = it.get(k, 0)
                    nums.append(v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10**12 else 0)
                row = db.execute("SELECT id FROM jobs WHERE state='published' AND publish_url LIKE ?", ("%/video/" + vid,)).fetchone()
                if row:
                    db.execute("INSERT INTO post_stats VALUES (?,?,?,?,?,?)", (row["id"], now, *nums))
                    matched += 1
        return {"matched": matched}

    def performance(self, limit=30):
        with self.connect() as db:
            rows = db.execute(
                """SELECT j.id,j.platform,j.title,j.route,j.publish_url,j.published_at,j.meta,
                (SELECT views FROM post_stats s WHERE s.job_id=j.id ORDER BY at DESC LIMIT 1) views,
                (SELECT likes FROM post_stats s WHERE s.job_id=j.id ORDER BY at DESC LIMIT 1) likes
                FROM jobs j WHERE j.state='published' ORDER BY j.published_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def platform_weights(self):
        """Nudge source priority toward platforms whose reposts actually performed. Needs evidence before it moves at all."""
        with self.connect() as db:
            rows = db.execute(
                """SELECT j.platform p,
                (SELECT views FROM post_stats s WHERE s.job_id=j.id ORDER BY at DESC LIMIT 1) v
                FROM jobs j WHERE j.state='published' AND j.published_at<? """,
                (time.time() - 24 * 3600,),
            ).fetchall()
        data = [(r["p"], r["v"]) for r in rows if r["v"] is not None]
        weights = {p: 1.0 for p in PLATFORMS}
        if len(data) < 8:
            return weights
        overall = sum(v for _, v in data) / len(data) or 1
        for p in PLATFORMS:
            vs = [v for q, v in data if q == p]
            if len(vs) >= 3:
                weights[p] = round(min(1.5, max(0.6, (sum(vs) / len(vs)) / overall)), 2)
        return weights
