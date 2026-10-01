"""Errors the processing pipeline distinguishes."""


class RateLimited(ValueError):
    pass


class Transient(RateLimited):
    """Google is overloaded or throttling right now; the job goes back to the queue instead of being marked broken."""


class VoiceoverUnfit(ValueError):
    pass
