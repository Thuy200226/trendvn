"""The sending loop: at most RATE_PER_MIN messages a minute, one at a time."""
import time

from . import config, smtp, store


def run_once(db):
    store.recover(db)
    job = store.claim(db)
    if not job:
        return False
    store.finish(db, job["id"], smtp.send(job))
    return True


def loop():
    db = store.connect()
    gap = 60.0 / config.RATE_PER_MIN
    while True:
        if not run_once(db):
            time.sleep(5)
        else:
            time.sleep(gap)
