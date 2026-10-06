"""The channels that have a search and a sign-in (the browser agent keeps its own copy beside the code that reads each of them)."""

NAMES = {"tiktok": "TikTok", "douyin": "Douyin"}
CHANNELS = tuple(NAMES)
STATES = ("ok", "out", "wall")  # signed in, signed out, or a verification wall in the way; no row = never looked
