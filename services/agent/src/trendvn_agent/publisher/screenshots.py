"""Screenshots for the owner: failures and the rehearsal result."""

import time

from ..config import DATA, RUNTIME

SHOTS_KEPT = (
    20  # a failed or CAPTCHA'd publish leaves a full-page picture; nothing else ever removed them and the disk is the recurring risk
)


def shot(page, name):
    try:
        folder = DATA / "shots"
        path = folder / ("%s_%d.png" % (name, int(time.time())))
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        return None
    try:
        for old in sorted(folder.glob("*.png"), key=lambda f: f.stat().st_mtime)[:-SHOTS_KEPT]:
            old.unlink(missing_ok=True)
    except OSError:
        pass  # pruning is housekeeping: it must never turn a successful picture into a failure
    return str(path)


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
