#!/usr/bin/env python3
"""Keep the documentation honest (run by `./trendvn test lint`):
1. every `./trendvn <command> [<sub>]` written in docs, code strings and scripts is a command the CLI really has (read from `./trendvn help`);
2. every relative markdown link points at a file that exists;
3. no leftovers of the pre-1.4 layouts (old paths and old script names) outside the history files;
4. README.md links every live document in docs/, and every other file under docs/ (history, diagrams) is linked from some document,
   so a document cannot be forgotten;
5. every markdown document has exactly one H1 (code blocks excluded);
6. docs/FLOWS.md (what happens) contains no technology terms: they belong in docs/TECH.md, so the two stay apart.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_FILES = {"CHANGELOG.md", "scripts/migrate.sh"}
problems = []


def is_history(rel):
    """Files that describe the old layout on purpose: the changelog, the migration script and everything under docs/history/."""
    return rel in HISTORY_FILES or rel.startswith("docs/history/")


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
    if is_history(rel):
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

# every command the CLI has must be documented in docs/OPERATIONS.md
commands_doc = (ROOT / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")
for cmd in sorted(top - {"help", "version"}):
    if "./trendvn " + cmd not in commands_doc:
        problems.append("docs/OPERATIONS.md kh\u00f4ng nh\u1eafc t\u1edbi l\u1ec7nh ./trendvn %s" % cmd)

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
    if is_history(rel):
        continue
    for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if OLD.search(line) and not any(a in line for a in ALLOWED_LINE):
            problems.append(
                "%s:%d c\u00f2n \u0111\u01b0\u1eddng d\u1eabn/t\u00ean c\u1ee7a b\u1ed1 c\u1ee5c c\u0169: %s"
                % (rel, n, OLD.search(line).group(0))
            )

# ---- 4. no document is forgotten
DOCS = ROOT / "docs"


def link_targets(md):
    """The files a markdown file links to (relative links only)."""
    return {
        (md.parent / target.split("#")[0]).resolve()
        for target in re.findall(r"\]\(([^)\s]+)\)", md.read_text(encoding="utf-8"))
        if not re.match(r"(https?:|mailto:|#)", target) and target.split("#")[0]
    }


from_readme = link_targets(ROOT / "README.md")
from_docs = set().union(*(link_targets(m) for m in sorted(DOCS.glob("*.md"))))
for f in sorted(DOCS.rglob("*")):
    if not (f.is_file() and f.suffix in (".md", ".drawio")):
        continue
    top_level = f.parent == DOCS
    if top_level and f.resolve() not in from_readme:
        problems.append(
            "%s kh\u00f4ng \u0111\u01b0\u1ee3c li\u00ean k\u1ebft trong README.md (b\u1ea3n \u0111\u1ed3 t\u00e0i li\u1ec7u)"
            % f.relative_to(ROOT).as_posix()
        )
    elif not top_level and f.resolve() not in from_docs:
        problems.append(
            "%s kh\u00f4ng \u0111\u01b0\u1ee3c t\u00e0i li\u1ec7u n\u00e0o li\u00ean k\u1ebft t\u1edbi" % f.relative_to(ROOT).as_posix()
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

# ---- 6. the flows document says what happens, never what it is made of
TECH_TERMS = re.compile(
    r"\b(n8n|docker|container|sqlite|playwright|ffmpeg|yt-dlp|http|https|api|endpoint|token|lease|launchd|systemd|venv|compose|stdlib|webhook|cron|chrome|gemini)\b|/api/",
    re.I,
)
flows = DOCS / "FLOWS.md"
if flows.exists():
    in_code = False
    for n, line in enumerate(flows.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        found = TECH_TERMS.search(line)
        if found and not (in_code and line.lstrip().startswith("%%")):
            problems.append("docs/FLOWS.md:%d n\u00eau c\u00f4ng ngh\u1ec7 (%s): \u0111\u01b0a v\u00e0o docs/TECH.md" % (n, found.group(0)))

if problems:
    print("doclint: %d v\u1ea5n \u0111\u1ec1\n  - " % len(problems) + "\n  - ".join(problems))
    sys.exit(1)
print("doclint OK: l\u1ec7nh, li\u00ean k\u1ebft v\u00e0 \u0111\u01b0\u1eddng d\u1eabn trong t\u00e0i li\u1ec7u kh\u1edbp m\u00e3.")
