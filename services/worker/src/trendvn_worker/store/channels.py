"""What the system knows of each account's sign-in on the channels it searches (the last report from the browser agent)."""

import time

CHANNELS = ("tiktok", "douyin")
STATES = ("ok", "out", "wall")  # signed in, signed out, or a verification wall in the way; no row = never looked


class ChannelsMixin:
    def channel_report(self, account, channel, state, who=""):
        if channel not in CHANNELS or state not in STATES or not self.account(account):
            raise ValueError("Kênh, trạng thái hoặc tài khoản không hợp lệ")
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO channel_logins(account,channel,state,who,at) VALUES(?,?,?,?,?)",
                (account, channel, state, str(who or "")[:80], time.time()),
            )

    def channel_states(self):
        """{account: {channel: {'state','who','at'}}}"""
        with self.connect() as db:
            rows = db.execute("SELECT account,channel,state,who,at FROM channel_logins").fetchall()
        out = {}
        for row in rows:
            out.setdefault(row["account"], {})[row["channel"]] = {"state": row["state"], "who": row["who"], "at": row["at"]}
        return out
