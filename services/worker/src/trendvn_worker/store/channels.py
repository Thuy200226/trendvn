"""What the system knows of each account's sign-in on the channels it searches (the last report from the browser agent)."""

import time

from ..domain.channels import CHANNELS, STATES


class ChannelsMixin:
    def channel_write(self, account, channel, state, who=""):
        """Record the state (no checks: callers have made them)."""
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO channel_logins(account,channel,state,who,at) VALUES(?,?,?,?,?)",
                (account, channel, state, str(who or "")[:80], time.time()),
            )

    def channel_report(self, account, channel, state, who=""):
        """What the agent found out about one account on one channel. TikTok's sign-in is also the Accounts tab's 'đã đăng nhập TikTok':
        the two are one fact and are kept in step whichever side learns it first."""
        if channel not in CHANNELS or state not in STATES or not self.account(account):
            raise ValueError("Kênh, trạng thái hoặc tài khoản không hợp lệ")
        self.channel_write(account, channel, state, who)
        if channel == "tiktok" and state in ("ok", "out"):
            self.set_account_login(account, state == "ok")

    def channel_states(self):
        """{account: {channel: {'state','who','at'}}}"""
        with self.connect() as db:
            rows = db.execute("SELECT account,channel,state,who,at FROM channel_logins").fetchall()
        out = {}
        for row in rows:
            out.setdefault(row["account"], {})[row["channel"]] = {"state": row["state"], "who": row["who"], "at": row["at"]}
        return out
