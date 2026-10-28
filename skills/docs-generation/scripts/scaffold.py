#!/usr/bin/env python3
"""Create the documentation skeleton (README, FLOWS, TECH, OPERATIONS, ROADMAP, CHANGELOG) in a repository.

Never overwrites an existing file: it reports what it skipped. Skeletons carry '<!-- FILL: ... -->' markers
that `doclint.py --final` fails on until they are replaced. Python 3.8+, standard library only.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL / "assets" / "templates"
TARGETS = {
    "README.md": "README.md",
    "CHANGELOG.md": "CHANGELOG.md",
    "FLOWS.md": "{docs}/FLOWS.md",
    "TECH.md": "{docs}/TECH.md",
    "OPERATIONS.md": "{docs}/OPERATIONS.md",
    "ROADMAP.md": "{docs}/ROADMAP.md",
}


def write_new(dest, text, dry):
    if dest.exists():
        print("skip    %s (exists)" % dest)
        return False
    print("%s %s" % ("would create" if dry else "create ", dest))
    if not dry:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo", help="repository root")
    ap.add_argument("--name", help="project name for the README title (default: the folder name)")
    ap.add_argument("--docs-dir", default="docs", help="folder for the four live documents (default: docs)")
    ap.add_argument("--install-lint", action="store_true", help="copy doclint.py to <repo>/scripts/doclint.py")
    ap.add_argument("--append-agents", action="store_true", help="add the documentation section to AGENTS.md (created if absent)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        sys.exit("not a directory: %s" % repo)
    name = args.name or repo.name
    created = 0

    for src, target in TARGETS.items():
        text = (TEMPLATES / src).read_text(encoding="utf-8")
        if src == "README.md":
            text = re.sub(r"^# .*$", "# " + name, text, count=1, flags=re.M)
        created += write_new(repo / target.format(docs=args.docs_dir.strip("/")), text, args.dry_run)

    if args.install_lint:
        dest = repo / "scripts" / "doclint.py"
        if dest.exists():
            print("skip    %s (exists; the repo keeps its own linter)" % dest)
        else:
            print("%s %s" % ("would copy" if args.dry_run else "copy   ", dest))
            if not args.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(SKILL / "scripts" / "doclint.py"), str(dest))
                dest.chmod(0o755)

    if args.append_agents:
        section = (TEMPLATES / "AGENTS-docs-section.md").read_text(encoding="utf-8")
        agents = repo / "AGENTS.md"
        if not agents.exists():
            write_new(agents, "# AGENTS.md\n\n" + section, args.dry_run)
        elif "## Documentation" in agents.read_text(encoding="utf-8"):
            print("skip    %s (already has a Documentation section)" % agents)
        else:
            print("%s a Documentation section to %s" % ("would append" if args.dry_run else "append ", agents))
            if not args.dry_run:
                with agents.open("a", encoding="utf-8") as fh:
                    fh.write("\n" + section)

    print("\n%d file(s) %s. Next: fill every FILL marker, then run" % (created, "would be created" if args.dry_run else "created"))
    print("  python3 %s --root %s --final" % (SKILL / "scripts" / "doclint.py", repo))
    print("  python3 %s --root %s" % (SKILL / "scripts" / "check_mermaid.py", repo))


if __name__ == "__main__":
    main()
