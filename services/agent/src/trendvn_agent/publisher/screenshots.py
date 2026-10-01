"""Screenshots for the owner: failures and the rehearsal result."""

import time

from ..config import DATA, RUNTIME


def shot(page, name):
    try:
        path = DATA / "shots" / ("%s_%d.png" % (name, int(time.time())))
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def export_shot(page, name):
    """Screenshot the owner can open from the dashboard (the worker serves data/worker/exports/shot_*.png). Returns the file name."""
    try:
        folder = RUNTIME / "exports"
        folder.mkdir(exist_ok=True)
        fname = "shot_%d.png" % int(time.time())
        page.screenshot(path=str(folder / fname), full_page=False)
        for old in sorted(folder.glob("shot_*.png"))[:-20]:  # keep the latest twenty
            old.unlink(missing_ok=True)
        return fname
    except Exception:
        return ""
