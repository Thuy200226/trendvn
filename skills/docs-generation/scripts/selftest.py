#!/usr/bin/env python3
"""Self-test for scaffold.py, doclint.py and check_mermaid.py (Python 3.8+, standard library only).

Builds a scratch repository from the templates, makes it pass, then breaks it one way at a time and checks that the
linter names exactly that rule. Run it after copying the skill somewhere new; exit 1 on any failure.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script, *args):
    done = subprocess.run([sys.executable, str(HERE / script)] + list(args), capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def build(repo):
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "queue.py").write_text("MAX_RETRIES = 3\n\n\ndef claim():\n    return None\n", encoding="utf-8")
    code, out = run("scaffold.py", str(repo), "--name", "Demo")
    assert code == 0, out
    for rel in ["README.md", "CHANGELOG.md", "docs/FLOWS.md", "docs/TECH.md", "docs/OPERATIONS.md", "docs/ROADMAP.md"]:
        p = repo / rel
        text = re.sub(r"<!--\s*FILL:.*?-->", "filled", p.read_text(encoding="utf-8"), flags=re.S)
        p.write_text(text, encoding="utf-8")
    (repo / "docs" / "TECH.md").write_text(
        (repo / "docs" / "TECH.md").read_text(encoding="utf-8") + "\nSee `app/queue.py` and `claim()`; the limit is `MAX_RETRIES`.\n",
        encoding="utf-8",
    )


def edit(repo, rel, fn):
    p = repo / rel
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


CASES = [
    ("broken link", lambda r: edit(r, "README.md", lambda t: t + "\n[x](docs/NOPE.md)\n"), "links", "doclint.py", []),
    ("broken anchor", lambda r: edit(r, "README.md", lambda t: t + "\n[x](docs/TECH.md#no-such-heading)\n"), "links", "doclint.py", []),
    ("anchor that exists passes", lambda r: edit(r, "README.md", lambda t: t + "\n[x](docs/TECH.md#2-design-decisions)\n"), None, "doclint.py", []),
    ("second H1", lambda r: edit(r, "docs/TECH.md", lambda t: t + "\n# Another title\n"), "one-h1", "doclint.py", []),
    ("unclosed fence", lambda r: edit(r, "docs/OPERATIONS.md", lambda t: t + "\n```bash\nls\n"), "fences", "doclint.py", []),
    ("technology in FLOWS", lambda r: edit(r, "docs/FLOWS.md", lambda t: t + "\nThe worker calls an HTTP API.\n"), "flows-no-tech", "doclint.py", []),
    ("technology in a FLOWS comment is allowed", lambda r: edit(r, "docs/FLOWS.md", lambda t: t + "\n<!-- uses an HTTP API -->\n"), None, "doclint.py", []),
    ("missing path", lambda r: edit(r, "docs/TECH.md", lambda t: t + "\nSee `app/gone.py`.\n"), "paths", "doclint.py", []),
    ("document not linked from README", lambda r: edit(r, "README.md", lambda t: t.replace("[docs/ROADMAP.md](docs/ROADMAP.md)", "ROADMAP")), "reachable", "doclint.py", []),
    ("missing required document", lambda r: (r / "CHANGELOG.md").unlink(), "required", "doclint.py", []),
    ("unfinished marker fails --final", lambda r: edit(r, "docs/TECH.md", lambda t: t + "\nTODO write this\n"), "markers", "doclint.py", ["--final"]),
    ("unknown identifier warns", lambda r: edit(r, "docs/TECH.md", lambda t: t + "\nCall `gone_function()`.\n"), "identifiers", "doclint.py", ["--strict"]),
    ("diagram with parentheses in an unquoted label", lambda r: edit(r, "docs/FLOWS.md", lambda t: t + "\n```mermaid\nflowchart LR\n  A[start (now)] --> B\n```\n"), "ERROR", "check_mermaid.py", ["--structural"]),
]


def main():
    failures = 0
    base = Path(tempfile.mkdtemp(prefix="docs-generation-selftest-"))
    try:
        template_repo = base / "template"
        build(template_repo)
        code, out = run("doclint.py", "--root", str(template_repo), "--final")
        print("%-52s %s" % ("clean scaffold passes --final", "ok" if code == 0 else "FAIL"))
        if code != 0:
            print(out)
            failures += 1
        code, out = run("check_mermaid.py", "--root", str(template_repo), "--structural")
        print("%-52s %s" % ("clean diagrams pass the structural check", "ok" if code == 0 else "FAIL"))
        failures += code != 0
        for name, mutate, expect, script, flags in CASES:
            repo = base / "case"
            if repo.exists():
                shutil.rmtree(str(repo))
            shutil.copytree(str(template_repo), str(repo))
            subprocess.run(["git", "init", "-q"], cwd=str(repo))
            mutate(repo)
            args = ["--root", str(repo)] + flags
            code, out = run(script, *args)
            if expect is None:
                good = code == 0
            else:
                good = code != 0 and re.search(r"\b%s\b" % re.escape(expect), out) is not None
            print("%-52s %s" % (name, "ok" if good else "FAIL"))
            if not good:
                print(out)
                failures += 1
        code, out = run("scaffold.py", str(template_repo), "--dry-run")
        good = code == 0 and "skip" in out and not re.search(r"^(would )?create", out, re.M)
        print("%-52s %s" % ("scaffold never overwrites existing files", "ok" if good else "FAIL"))
        failures += not good
    finally:
        shutil.rmtree(str(base), ignore_errors=True)
    print("selftest: %s" % ("all passed" if not failures else "%d failed" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
