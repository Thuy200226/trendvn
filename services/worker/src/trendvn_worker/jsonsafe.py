"""Reading JSON our own code wrote into the database, tolerating a damaged or hand-edited value: one bad row must not take a page, the
start-up or the publisher down."""

import json


def loads(text, default=None):
    """The decoded value, or `default` when `text` is NULL, empty, not JSON, or the wrong kind of thing (`default`'s type, when given)."""
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return default
    if default is not None and not isinstance(value, type(default)):
        return default
    return value
