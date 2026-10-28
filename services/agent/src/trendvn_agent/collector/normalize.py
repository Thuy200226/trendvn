"""Number parsing and item-by-item parsing shared by the platform parsers."""

from ..log import log


def to_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


def parse_each(raw_items, parse_one, source):
    """Parse every raw item on its own. One odd item (a missing key, a wrong type, a huge number) drops only itself instead of the whole
    response, and a failure is logged: a site that changed its format would otherwise look like "no videos" and be misread as a rate limit.
    """
    items, failed = [], 0
    for raw in raw_items:
        try:
            item = parse_one(raw)
        except (TypeError, AttributeError, KeyError, IndexError, ValueError, ArithmeticError) as error:
            failed += 1
            if failed == 1:
                log("%s: skipped an item that does not parse (%s: %s)" % (source, type(error).__name__, str(error)[:80]))
            continue
        if item:
            items.append(item)
    if failed > 1:
        log("%s: %d items did not parse" % (source, failed))
    return items
