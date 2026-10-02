"""Small file helpers."""

import hashlib
import shutil


def free_bytes(path):
    """Free space on the disk that holds `path` (a function of its own so tests need not depend on how full the real disk is)."""
    return shutil.disk_usage(path).free


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()
