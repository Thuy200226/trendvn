"""Errors the processing pipeline distinguishes."""


class RateLimited(ValueError):
    pass


class Transient(RateLimited):
    """Google is overloaded or throttling right now; the job goes back to the queue instead of being marked broken."""


class KeyRejected(ValueError):
    """Google does not accept the API key (wrong, revoked, or without permission). Every video would fail the same way: it is the owner's to
    fix in Settings, and no video is blamed for it."""


class VoiceoverUnfit(ValueError):
    pass
