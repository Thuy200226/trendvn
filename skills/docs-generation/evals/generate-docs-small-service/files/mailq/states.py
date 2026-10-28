"""Job states and the moves allowed between them (pure rules, no I/O)."""

PENDING, SENDING, SENT, FAILED, DEAD, UNKNOWN = "pending", "sending", "sent", "failed", "dead", "unknown"
MOVES = {
    PENDING: {SENDING},
    SENDING: {SENT, FAILED, UNKNOWN},
    FAILED: {PENDING, DEAD},
    UNKNOWN: {SENT, PENDING},
    SENT: set(),
    DEAD: set(),
}
