#!/usr/bin/env python3
"""Keep the documentation honest (run by `./trendvn test lint`):
1. every `./trendvn <command> [<sub>]` written in docs, code strings and scripts is a command the CLI really has (read from `./trendvn help`);
2. every relative markdown link points at a file that exists;
3. no leftovers of the pre-1.3 layout (old paths and old script names) outside the history files.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = {"CHANGELOG.md", "docs/REVIEW-1.2.md", "docs/REVIEW-1.3.md", "scripts/migrate.sh"}  # these describe the old layout on purpose
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
    + list((ROOT / "docs").glob("*.md"))
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
                problems.append("%s:%d ./trendvn %s: không có lệnh này" % (rel, n, cmd))
            elif cmd in NEEDS_SUB and sub and not sub.startswith("-") and sub not in subs.get(cmd, set()) and not sub.isdigit():
                # a word after the sub-command slot may be plain prose ("./trendvn agent restart, rồi"): only flag lowercase words that look like a sub-command
                if re.fullmatch(r"[a-z-]+", sub) and sub not in {"rồi", "và", "hoặc", "thì"}:
                    problems.append(
                        "%s:%d ./trendvn %s %s: không có lệnh con này (có: %s)" % (rel, n, cmd, sub, ", ".join(sorted(subs.get(cmd, []))))
                    )

# every command the CLI has must be documented in docs/COMMANDS.md
commands_doc = (ROOT / "docs" / "COMMANDS.md").read_text(encoding="utf-8")
for cmd in sorted(top - {"help", "version"}):
    if "./trendvn " + cmd not in commands_doc:
        problems.append("docs/COMMANDS.md không nhắc tới lệnh ./trendvn %s" % cmd)

# ---- 2. relative links
for f in list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md")):
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            if re.match(r"(https?:|mailto:|#)", target):
                continue
            path = target.split("#")[0]
            if path and not (f.parent / path).resolve().exists():
                problems.append("%s:%d liên kết hỏng: %s" % (f.relative_to(ROOT), n, target))

# ---- 3. old layout leftovers
OLD = re.compile(
    r"agent_data|(?<![\w/])runtime/|(?<![\w.])setup\.py|(?<![\w/])install\.sh|package\.sh|CAI-DAT|Cai-dat-Mac|import_workflows|build_workflows|"
    r"python agent/|(?<![\w/])agent/(?:server|publisher|collector|common)\.py|(?<![\w/])worker/(?:core|media|server|ui|tasks|prompts|notify)\.py"
)
ALLOWED_LINE = ("thư-mục-1.2", "thư mục cũ", "bản 1.2")  # the migration recipe legitimately names the old scripts
for f in files:
    rel = f.relative_to(ROOT).as_posix()
    if rel in HISTORY:
        continue
    for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if OLD.search(line) and not any(a in line for a in ALLOWED_LINE):
            problems.append("%s:%d còn đường dẫn/tên của bố cục cũ: %s" % (rel, n, OLD.search(line).group(0)))

if problems:
    print("doclint: %d vấn đề\n  - " % len(problems) + "\n  - ".join(problems))
    sys.exit(1)
print("doclint OK: lệnh, liên kết và đường dẫn trong tài liệu khớp mã.")
