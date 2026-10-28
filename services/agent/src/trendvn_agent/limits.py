"""How long each browser job may take, in seconds. One table for the agent's overdue alert (server.py) and for the n8n request timeouts
(n8n/build.py loads this file), so n8n never gives up on a job the agent still counts as normal.

A job over its limit is only REPORTED, never killed: ending a Chrome that is in the middle of a post could leave a post nobody can account for.
The publish limit is the sum of the longest waits in publisher/post.py (about 27 to 31 minutes with every wait used up); the others are
generous estimates, not measurements.
"""

JOB_SECONDS = {
    "/api/collect": 900,
    "/api/publish": 1920,
    "/api/session": 900,
    "/api/verify": 900,
    "/api/stats": 600,
    "/api/dry-run": 900,
}
N8N_MARGIN_SECONDS = 60  # n8n waits this much longer than the agent's limit
