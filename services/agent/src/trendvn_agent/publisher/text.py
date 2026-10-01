"""Hashing and text normalisation used to match captions."""

import re
import hashlib


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def norm(text):
    return re.sub(r"[^\w]+", "", (text or "").lower())[:60]
