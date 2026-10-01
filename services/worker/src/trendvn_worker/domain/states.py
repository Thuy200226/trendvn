"""The life of a video: every state a job can be in."""

STATES = (
    "baseline",
    "candidate",
    "queued",
    "processing",
    "awaiting_approval",
    "ready",
    "publishing",
    "published",
    "needs_review",
    "publish_unknown",
    "duplicate",
    "failed",
    "rejected",
)
