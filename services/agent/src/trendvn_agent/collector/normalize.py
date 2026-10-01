"""Number parsing shared by the platform parsers."""


def to_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None
