"""TikTok Studio publisher driven through a dedicated, isolated Chrome profile (no TikTok API, no cookies copied).

You sign in once yourself in the visible window opened by `./trendvn tiktok login`; the session then lives only in
data/agent/profiles/publisher. The publisher never types a password. Outcomes are conservative: once the Post button has
been clicked, anything short of a verified post is reported as "unknown" and publishing stops until it is resolved, so a
video can never be posted twice by an automatic retry.
"""

from .jobs import dry_run_next, run_publish, run_stats, verify_unresolved
from .session import login, session_status, trust

__all__ = ["run_publish", "dry_run_next", "run_stats", "verify_unresolved", "login", "trust", "session_status"]
