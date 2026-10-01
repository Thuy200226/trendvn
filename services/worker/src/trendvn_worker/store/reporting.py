"""Read models for the dashboard, the API and the daily summary."""

from ..domain.accounts import effective

# columns of a job shown in lists on the dashboard
JOB_COLUMNS = "id,platform,title,state,reason,route,meta,url,updated,first_seen,duration"
# settings the dashboard page needs (a subset of all settings)
DASHBOARD_SETTINGS = (
    "daily_limit", "min_publish_gap", "post_windows", "max_age_days", "max_duration", "max_candidates_per_scan", "max_backlog",
    "min_views", "min_likes", "audio_confidence", "gemini_daily_limit", "require_approval", "voiceover_enabled", "target", "voice",
    "timezone", "model", "tts_model", "visibility",
)  # fmt: skip
# the collector's thresholds, exposed through /api/status
THRESHOLD_SETTINGS = ("min_views", "min_likes", "max_duration", "max_candidates_per_scan", "max_backlog", "max_age_days")


class ReportingMixin:
    """Aggregated views over the database."""

    def recent_events(self, limit=40):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    """SELECT e.at,e.event,e.detail,e.job_id,COALESCE(j.title,'') title,COALESCE(j.platform,'') platform
                FROM events e LEFT JOIN jobs j ON j.id=e.job_id WHERE e.event<>'baseline' ORDER BY e.id DESC LIMIT ?""",
                    (limit,),
                )
            ]

    def summary_text(self, now=None):
        st = self.status()
        c = st["counts"]
        best = [p for p in self.performance(10) if p["views"]]
        best = max(best, key=lambda p: p["views"], default=None)
        lines = [
            "📊 TrendVN hôm nay: đã đăng %d/%d" % (st["published_today"], st["daily_limit"]),
            "Hàng chờ: %d chờ xử lý, %d đã dựng, %d chờ duyệt"
            % (c.get("queued", 0) + c.get("processing", 0), c.get("ready", 0), c.get("awaiting_approval", 0) + c.get("needs_review", 0)),
        ]
        if st["unresolved_publishes"]:
            lines.append("🚨 %d bài đăng chưa xác nhận" % st["unresolved_publishes"])
        if st["discovery"] != "connected":
            lines.append("🔌 Bộ thu thập: " + st["discovery"])
        if st["publisher"] != "connected":
            lines.append("🔌 Trình đăng: " + st["publisher"])
        if best:
            lines.append("🏆 Bài tốt nhất gần đây: %s (%s lượt xem)" % (best["title"][:50], format(best["views"], ",")))
        return "\n".join(lines)

    def dashboard_data(self):
        """Everything the dashboard page shows, in one read."""
        status = self.status()
        cfg = self.settings()
        in_window, next_window = self.window_state(cfg)
        with self.connect() as db:
            data = dict(
                status,
                review=self._jobs_in(db, ("needs_review",)),
                approval=self._jobs_in(db, ("awaiting_approval",)),
                queue=self._queue(db),
                candidates=self._candidates(db),
                pipeline=self._jobs_in(db, ("candidate", "queued", "processing", "ready", "publishing")),
                by_platform=self._counts_by_platform(db),
            )
        data.update(
            performance=self.performance(30),
            unresolved=self.unresolved(),
            events=self.recent_events(40),
            weights=self.platform_weights(),
            in_window=in_window,
            next_window=next_window,
            settings={key: cfg[key] for key in DASHBOARD_SETTINGS},
        )
        return data

    @staticmethod
    def _jobs_in(db, states, limit=30):
        marks = ",".join("?" * len(states))
        sql = "SELECT %s,output_file FROM jobs WHERE state IN (%s) ORDER BY updated DESC LIMIT ?" % (JOB_COLUMNS, marks)
        return [dict(row) for row in db.execute(sql, (*states, limit))]

    @staticmethod
    def _queue(db):
        """Waiting videos in the order they will be processed: the one being processed first, then oldest first (see claim())."""
        sql = (
            "SELECT %s FROM jobs WHERE state IN ('processing','queued') ORDER BY (state='processing') DESC, first_seen LIMIT 30"
            % JOB_COLUMNS
        )
        return [dict(row) for row in db.execute(sql)]

    @staticmethod
    def _candidates(db):
        """Videos found but not downloaded yet, best score first."""
        sql = (
            "SELECT %s FROM jobs WHERE state='candidate' ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT 20"
            % JOB_COLUMNS
        )
        return [dict(row) for row in db.execute(sql)]

    @staticmethod
    def _counts_by_platform(db):
        counts = {}
        for row in db.execute("SELECT platform,state,count(*) n FROM jobs GROUP BY platform,state"):
            counts.setdefault(row["platform"], {})[row["state"]] = row["n"]
        return counts

    def status(self):
        """The compact state used by the API, n8n, the agent and `./trendvn doctor`."""
        with self.connect() as db:
            counts = {row["state"]: row["n"] for row in db.execute("SELECT state,count(*) n FROM jobs GROUP BY state")}
            jobs = [
                dict(row)
                for row in db.execute(
                    "SELECT id,platform,title,state,reason,route,publish_url,updated FROM jobs ORDER BY updated DESC LIMIT 100"
                )
            ]
            streams = [dict(row) for row in db.execute("SELECT * FROM streams")]
        cfg = self.settings()
        discovery_beat = cfg.get("hb_discovery") or {}
        publisher_beat = cfg.get("hb_publisher") or {}
        accounts = self._account_overview(cfg, publisher_beat)
        return {
            "project": "TrendVN",
            "target": cfg["target"],
            "counts": counts,
            "jobs": jobs,
            "streams": streams,
            "processing_enabled": cfg["processing_enabled"],
            "publisher_enabled": cfg["publisher_enabled"],
            "daily_limit": sum(a["daily_limit"] for a in accounts if a["enabled"]) or cfg["daily_limit"],
            "published_today": self.published_today(),
            "accounts": accounts,
            "wanted_topics": self.wanted_topics(),
            "discovery": self.component_state("discovery", cfg),
            "publisher": self.component_state("publisher", cfg),
            "discovery_at": discovery_beat.get("at"),
            "publisher_at": publisher_beat.get("at"),
            "discovery_detail": discovery_beat.get("detail"),
            "publisher_detail": publisher_beat.get("detail"),
            "gemini_configured": (self.root / "gemini.key").exists(),
            "unresolved_publishes": len(self.unresolved()),
            "thresholds": {key: cfg[key] for key in THRESHOLD_SETTINGS},
            "weights": self.platform_weights(),
            "require_approval": cfg["require_approval"],
            "voiceover_enabled": cfg["voiceover_enabled"],
            "publisher_challenge": bool(cfg.get("publisher_challenge")),
            "note": "Publishing stays off until the switch is turned on from the local dashboard.",
        }

    def _account_overview(self, cfg, publisher_beat):
        """Each account with what it posted today, its effective daily limit and whether the browser is signed in to it."""
        logins = (publisher_beat.get("detail") or {}).get("login") if isinstance(publisher_beat.get("detail"), dict) else None
        overview = []
        for account in self.accounts():
            eff = effective(account, cfg)
            overview.append(
                {
                    "id": account["id"],
                    "username": account["username"],
                    "label": account["label"],
                    "topics": account["topics"],
                    "enabled": account["enabled"],
                    "daily_limit": eff["daily_limit"],
                    "min_gap": eff["min_gap"],
                    "windows": eff["windows"],
                    "visibility": eff["visibility"],
                    "own": {k: account[k] for k in ("daily_limit", "min_gap", "windows", "visibility")},
                    "published_today": self.published_today(account=account),
                    "logged_in": logins.get(account["id"]) if isinstance(logins, dict) else None,
                }
            )
        return overview
