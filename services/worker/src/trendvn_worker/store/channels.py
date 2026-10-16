"""What the system knows of each account's sign-in on the channels it searches (the last report from the browser agent)."""

import time

from ..domain.channels import CHANNELS, STATES


class ChannelsMixin:
    def channel_write(self, account, channel, state, who=""):
        """Record metadata using the caller's transaction when identity must be pinned."""
        with self.transaction() as db:
            self._write_channel(db, account, channel, state, who)

    @staticmethod
    def _write_channel(db, account, channel, state, who=""):
        db.execute(
            """INSERT INTO channel_logins(account,channel,state,who,at) VALUES(?,?,?,?,?)
            ON CONFLICT(account,channel) DO UPDATE SET state=excluded.state,at=excluded.at,
            who=CASE WHEN excluded.state='out' THEN '' WHEN excluded.who<>'' THEN excluded.who ELSE channel_logins.who END""",
            (account, channel, state, str(who or "")[:80], time.time()),
        )

    def channel_report(self, account, channel, state, who="", expected_username=None):
        """Bind a source report and TikTok's login flag to the same identity in one transaction."""
        if channel not in CHANNELS or state not in STATES:
            raise ValueError("Kênh, trạng thái hoặc tài khoản không hợp lệ")
        announce = False
        with self.transaction() as db:
            receiver = db.execute("SELECT username FROM accounts WHERE id=?", (account,)).fetchone()
            if not receiver or expected_username is not None and receiver[0] != expected_username:
                raise ValueError("Tài khoản đã thay đổi; không nhận báo cáo phiên cũ")
            if channel == "tiktok" and state == "ok" and who and who.casefold() != receiver[0].casefold():
                raise ValueError("Phiên TikTok không thuộc tài khoản đã chọn")
            self._write_channel(db, account, channel, state, who)
            if channel == "tiktok" and state in ("ok", "out"):
                announce = self._set_account_login(db, account, state == "ok")
        if announce:
            self._announce_sign_out(account)

    def channel_states(self):
        """{account: {channel: {'state','who','at'}}}"""
        with self.connect() as db:
            rows = db.execute("SELECT account,channel,state,who,at FROM channel_logins").fetchall()
        out = {}
        for row in rows:
            out.setdefault(row["account"], {})[row["channel"]] = {"state": row["state"], "who": row["who"], "at": row["at"]}
        return out
