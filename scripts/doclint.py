#!/usr/bin/env python3
"""Keep the documentation honest (run by `./trendvn test lint`):
1. every `./trendvn <command> [<sub>]` written in docs, code strings and scripts is a command the CLI really has (read from `./trendvn help`);
2. every relative markdown link points at a file that exists;
3. no leftovers of the pre-1.4 layouts (old paths and old script names) outside the history files;
4. docs/README.md (the index) links every file under docs/, so a new document cannot be forgotten;
5. every markdown document has exactly one H1 (code blocks excluded).
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = {
    "CHANGELOG.md",
    "docs/history/REVIEW-1.2.md",
    "docs/history/REVIEW-1.3.md",
    "docs/ROADMAP.md",
    "scripts/migrate.sh",
}  # these describe the old layout on purpose
problems = []

# ---- 1. commands: the truth is the help text
help_text = subprocess.run([str(ROOT / "trendvn"), "help"], capture_output=True, text=True).stdout
top, subs = set(), {}
for line in help_text.splitlines():
    m = re.match(r"^  ([a-z0-9-]+)((?:[ |][a-z0-9|-]+)*)", line)
    if not m:
        continue
    cmd = m.group(1)
    top.add(cmd)
    for token in re.findall(r"[a-z0-9-]+", m.group(2).split("[")[0]):
        subs.setdefault(cmd, set()).add(token)
top |= {"help", "version"}
NEEDS_SUB = {"n8n", "agent", "tiktok"}

files = [
    f
    for f in list(ROOT.glob("*.md"))
    + list((ROOT / "docs").rglob("*.md"))
    + list((ROOT / "services").rglob("*.py"))
    + list((ROOT / "scripts").glob("*"))
    + [ROOT / "Makefile", ROOT / ".env.example", ROOT / "compose.yaml"]
    if f.is_file() and f.name != "doclint.py"
]
for f in files:
    rel = f.relative_to(ROOT).as_posix()
    if rel in HISTORY:
        continue
    text = f.read_text(encoding="utf-8", errors="replace")
    for n, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"\./trendvn ([a-z0-9-]+)(?: ([a-z0-9-]+))?", line):
            cmd, sub = m.group(1), m.group(2)
            if cmd not in top:
                problems.append("%s:%d ./trendvn %s: kh\u00f4ng c\u00f3 l\u1ec7nh n\u00e0y" % (rel, n, cmd))
            elif cmd in NEEDS_SUB and sub and not sub.startswith("-") and sub not in subs.get(cmd, set()) and not sub.isdigit():
                # a word after the sub-command slot may be plain prose (""./trendvn agent restart, then"): only flag lowercase words that look like a sub-command
                if re.fullmatch(r"[a-z-]+", sub) and sub not in {"r\u1ed3i", "v\u00e0", "ho\u1eb7c", "th\u00ec"}:
                    problems.append(
                        "%s:%d ./trendvn %s %s: kh\u00f4ng c\u00f3 l\u1ec7nh con n\u00e0y (c\u00f3: %s)"
                        % (rel, n, cmd, sub, ", ".join(sorted(subs.get(cmd, []))))
                    )

# every command the CLI has must be documented in docs/COMMANDS.md
commands_doc = (ROOT / "docs" / "COMMANDS.md").read_text(encoding="utf-8")
for cmd in sorted(top - {"help", "version"}):
    if "./trendvn " + cmd not in commands_doc:
        problems.append("docs/COMMANDS.md kh\u00f4ng nh\u1eafc t\u1edbi l\u1ec7nh ./trendvn %s" % cmd)

# ---- 2. relative links
for f in list(ROOT.glob("*.md")) + list((ROOT / "docs").rglob("*.md")):
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            if re.match(r"(https?:|mailto:|#)", target):
                continue
            path = target.split("#")[0]
            if path and not (f.parent / path).resolve().exists():
                problems.append("%s:%d li\u00ean k\u1ebft h\u1ecfng: %s" % (f.relative_to(ROOT), n, target))

# ---- 3. old layout leftovers
OLD = re.compile(
    r"agent_data|(?<![\w/])runtime/|(?<![\w.])setup\.py|(?<![\w/])install\.sh|package\.sh|CAI-DAT|Cai-dat-Mac|import_workflows|build_workflows|"
    r"python agent/|(?<![\w/])agent/(?:server|publisher|collector|common)\.py|(?<![\w/])worker/(?:core|media|server|ui|tasks|prompts|notify)\.py|"
    r"services/worker/app|services/agent/(?:server|publisher|collector|common)\.py|(?<![\w/.])(?:publisher|collector)\.py|_looks_blocked"
)
ALLOWED_LINE = ("old-directory-1.2", "old directory", "version 1.2")  # migration instructions legitimately reference old scripts
for f in files:
    rel = f.relative_to(ROOT).as_posix()
    if rel in HISTORY:
        continue
    for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if OLD.search(line) and not any(a in line for a in ALLOWED_LINE):
            problems.append(
                "%s:%d c\u00f2n \u0111\u01b0\u1eddng d\u1eabn/t\u00ean c\u1ee7a b\u1ed1 c\u1ee5c c\u0169: %s"
                % (rel, n, OLD.search(line).group(0))
            )

# ---- 4. the index lists every document
DOCS = ROOT / "docs"
index_text = (DOCS / "README.md").read_text(encoding="utf-8")
listed = {
    (DOCS / target.split("#")[0]).resolve()
    for target in re.findall(r"\]\(([^)\s]+)\)", index_text)
    if not re.match(r"(https?:|mailto:|#)", target)
}
for f in sorted(DOCS.rglob("*")):
    if f.is_file() and f.suffix in (".md", ".drawio") and f != DOCS / "README.md" and f.resolve() not in listed:
        problems.append(
            "%s kh\u00f4ng c\u00f3 trong docs/README.md (m\u1ee5c l\u1ee5c t\u00e0i li\u1ec7u)" % f.relative_to(ROOT).as_posix()
        )

# ---- 5. one H1 per document
for f in [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "AGENTS.md"] + sorted(DOCS.rglob("*.md")):
    in_code, titles = False, 0
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(r"# \S", line):
            titles += 1
    if titles != 1:
        problems.append("%s c\u00f3 %d ti\u00eau \u0111\u1ec1 H1 (c\u1ea7n \u0111\u00fang 1)" % (f.relative_to(ROOT).as_posix(), titles))

if problems:
    print("doclint: %d v\u1ea5n \u0111\u1ec1\n  - " % len(problems) + "\n  - ".join(problems))
    sys.exit(1)
print("doclint OK: l\u1ec7nh, li\u00ean k\u1ebft v\u00e0 \u0111\u01b0\u1eddng d\u1eabn trong t\u00e0i li\u1ec7u kh\u1edbp m\u00e3.")
