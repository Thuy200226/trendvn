"""Discovery and media fetch for Douyin, Kuaishou (CN) and TikTok, Instagram Reels (US).

Reads the same public JSON the sites' own web pages load, inside a real Chrome. It never solves CAPTCHAs or logs in; a login wall or
verification page is reported as a stream failure, not bypassed. US streams are only collected when the browser's exit country is
verified as US, so Vietnamese feeds are never mislabelled as US trends.
"""

from .run import collect
from .sources import SOURCES

__all__ = ["collect", "SOURCES"]
