"""Screenshots for the owner: failures and the rehearsal result."""

import time

from ..config import DATA, RUNTIME

KEEP_SHOTS = 20  # a failure's screenshot (and the page text saved beside it) is for looking at once, not for keeping: the disk is small


def prune_shots(folder, keep=KEEP_SHOTS):
    """Keep the newest `keep` screenshots of the folder; an older one goes, and with it the text file saved beside it (a text file left
    without its screenshot is removed)."""
    pictures = sorted(folder.glob("*.png"), key=lambda p: (p.stat().st_mtime, p.name))
    for old in pictures[:-keep] if keep else pictures:
        old.unlink(missing_ok=True)
    for text in folder.glob("*.txt"):
        if not text.with_suffix(".png").exists():
            text.unlink(missing_ok=True)


def shot(page, name):
    try:
        folder = DATA / "shots"
        path = folder / ("%s_%d.png" % (name, int(time.time())))
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        return None
    try:
        prune_shots(folder)
    except OSError:  # a file that changed under us (another process, a stray link): the screenshot itself was taken
        pass
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
