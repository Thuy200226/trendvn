#!/usr/bin/env python3
"""Package a clean, secret-free release to hand to another machine:   ./trendvn package

Writes dist/trendvn-<version>.tar.gz (+ .sha256). It contains source only: never .env, data/ (videos, queue, TikTok session), .venv, backups
or dist. Pure Python, so it behaves the same on Linux and macOS (no GNU/BSD tar differences, no AppleDouble '._' files).
Before packing it runs the cheap checks (workflows match their generator, every Python file compiles, shell scripts parse) and refuses
to ship a broken tree.
"""

import gzip
import hashlib
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text().strip()
NAME = "trendvn-" + VERSION
EXCLUDE_TOP = {"data", ".venv", "dist", ".git", ".idea", ".vscode"}  # plus every top-level .env* except .env.example (see keep())
EXCLUDE_ANYWHERE = {"__pycache__", ".DS_Store", "exported"}  # n8n/exported/ is a local scratch folder (./trendvn n8n export)
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".swp")


def keep(path):
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if len(parts) == 1 and parts[0].startswith(".env") and parts[0] != ".env.example":
        return False  # .env, .env.bak, .env.before-restore...: secrets never ship
    return not (
        parts[0] in EXCLUDE_TOP
        or any(p in EXCLUDE_ANYWHERE for p in parts)
        or path.name.endswith(EXCLUDE_SUFFIX)
        or path.name.startswith("._")
    )


def preflight():
    problems = []
    if subprocess.run([sys.executable, str(ROOT / "n8n" / "build.py"), "--check"], capture_output=True).returncode != 0:
        problems.append("n8n/workflows kh\u00f4ng kh\u1edbp n8n/build.py (ch\u1ea1y ./trendvn n8n build)")
    for f in sorted(ROOT.rglob("*.py")):
        if keep(f):
            try:
                compile(f.read_text(encoding="utf-8"), str(f), "exec")
            except SyntaxError as e:
                problems.append("l\u1ed7i c\u00fa ph\u00e1p %s d\u00f2ng %s: %s" % (f.relative_to(ROOT), e.lineno, e.msg))
    for f in sorted(list(ROOT.rglob("*.sh")) + list(ROOT.rglob("*.command")) + [ROOT / "trendvn"]):
        if keep(f) and subprocess.run(["bash", "-n", str(f)], capture_output=True).returncode != 0:
            problems.append("l\u1ed7i c\u00fa ph\u00e1p shell: " + str(f.relative_to(ROOT)))
    changelog = (ROOT / "CHANGELOG.md").read_text()
    if "## %s " % VERSION not in changelog:
        problems.append("CHANGELOG.md ch\u01b0a c\u00f3 m\u1ee5c cho phi\u00ean b\u1ea3n " + VERSION)
    return problems


def main():
    problems = preflight()
    if problems:
        print("Kh\u00f4ng \u0111\u00f3ng g\u00f3i v\u00ec:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 1
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / (NAME + ".tar.gz")
    # Same source -> same bytes (and same sha256): the mtime of every file and of the gzip header is the release date from CHANGELOG.md.
    m = re.search(r"^## %s [—-] (\d{4})-(\d{2})-(\d{2})" % re.escape(VERSION), (ROOT / "CHANGELOG.md").read_text(), re.M)
    stamp = int(time.mktime(time.strptime("-".join(m.groups()), "%Y-%m-%d"))) if m else 0
    count = 0
    with (
        open(out, "wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=stamp, filename="") as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for path in sorted(ROOT.rglob("*")):
            if path.is_dir() or path.is_symlink() or not keep(path):
                continue
            info = tar.gettarinfo(str(path), arcname="%s/%s" % (NAME, path.relative_to(ROOT).as_posix()))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = stamp
            with open(path, "rb") as fh:
                tar.addfile(info, fh)
            count += 1
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (dist / (NAME + ".tar.gz.sha256")).write_text("%s  %s\n" % (digest, out.name))
    print("\u0110\u00e3 t\u1ea1o dist/%s (%d file, %.0f KB)\nsha256 %s" % (out.name, count, out.stat().st_size / 1024, digest))
    print("Ch\u00e9p sang m\u00e1y Mac (AirDrop/USB), gi\u1ea3i n\u00e9n, r\u1ed3i l\u00e0m theo docs/MAC.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
