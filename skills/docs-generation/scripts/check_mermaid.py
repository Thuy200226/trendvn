#!/usr/bin/env python3
"""Check every ```mermaid block in the repository's Markdown files (Python 3.8+, standard library only).

With Node.js and a one-time install of the Mermaid parser (`--install`, downloads from npm) it uses the real
parser. Without them it falls back to a weaker structural check and says so. Exit 1 when a block is wrong.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIAGRAMS = (
    "flowchart", "graph", "stateDiagram", "stateDiagram-v2", "sequenceDiagram", "classDiagram", "erDiagram", "gantt", "pie",
    "journey", "gitGraph", "mindmap", "timeline", "quadrantChart", "requirementDiagram", "sankey-beta", "xychart-beta",
    "block-beta", "architecture-beta", "C4Context", "C4Container", "C4Component", "C4Dynamic", "C4Deployment",
)
PACKAGE = {"name": "docs-generation-mermaid", "private": True, "type": "module", "dependencies": {"mermaid": "^11.17.2", "jsdom": "^30.1.3"}}


def markdown_files(root):
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"], capture_output=True, check=True
        ).stdout.decode("utf-8", "replace")
        return [root / f for f in out.split("\0") if f and (root / f).is_file()]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", "node_modules", ".venv", "venv"}
        found = []
        for base, dirs, names in os.walk(str(root)):
            dirs[:] = [d for d in dirs if d not in skip]
            found += [Path(base) / n for n in names if n.endswith(".md")]
        return found


def extract_blocks(path, root):
    blocks, cur = [], None
    rel = path.relative_to(root).as_posix() if root in path.parents else str(path)
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        if cur is None:
            if re.match(r"^\s*```mermaid\s*$", line):
                cur = {"file": rel, "line": n, "lines": []}
        elif re.match(r"^\s*```\s*$", line):
            blocks.append({"file": cur["file"], "line": cur["line"], "code": "\n".join(cur["lines"])})
            cur = None
        else:
            cur["lines"].append(line)
    if cur is not None:
        blocks.append({"file": cur["file"], "line": cur["line"], "code": "\n".join(cur["lines"]) + "\n<unclosed fence>"})
    return blocks


def find_node():
    found = shutil.which("node")
    if found:
        return found
    home = Path.home()
    patterns = [
        str(home / ".local/share/fnm/node-versions/*/installation/bin/node"),
        str(home / ".nvm/versions/node/*/bin/node"),
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


def real_parse(blocks, node, cache, install):
    cache.mkdir(parents=True, exist_ok=True)
    have = (cache / "node_modules" / "mermaid").is_dir() and (cache / "node_modules" / "jsdom").is_dir()
    if not have:
        if not install:
            return None, "the Mermaid parser is not installed in %s (run with --install; it downloads packages from npm)" % cache
        npm = Path(node).with_name("npm")
        if not npm.exists():
            return None, "npm not found next to %s" % node
        (cache / "package.json").write_text(json.dumps(PACKAGE, indent=2), encoding="utf-8")
        env = dict(os.environ, PATH=str(Path(node).parent) + os.pathsep + os.environ.get("PATH", ""))
        done = subprocess.run([str(npm), "install", "--no-audit", "--no-fund", "--prefix", str(cache)], capture_output=True, text=True, env=env)
        if done.returncode != 0:
            return None, "npm install failed: " + done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "npm install failed"
    script = cache / "docs_mermaid_check.mjs"
    shutil.copyfile(str(HERE / "mermaid_check.mjs"), str(script))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(blocks, fh)
        data = fh.name
    try:
        done = subprocess.run([node, str(script), data], capture_output=True, text=True, cwd=str(cache), timeout=300)
    finally:
        os.unlink(data)
    try:
        return json.loads(done.stdout), None
    except ValueError:
        return None, "the parser produced no result: " + (done.stderr.strip().splitlines() or ["unknown error"])[-1]


def strip_quoted(text):
    return re.sub(r'"[^"]*"', '""', text)


def structural(block):
    """Weaker checks that catch the usual mistakes without the parser: returns a list of problems."""
    problems = []
    lines = [ln for ln in block["code"].split("\n") if ln.strip() and not ln.strip().startswith("%%")]
    if not lines:
        return ["empty diagram"]
    kind = lines[0].strip().split()[0]
    if kind not in DIAGRAMS:
        problems.append("first line must start with a diagram type, found '%s'" % kind)
    flow = kind in ("flowchart", "graph")
    depth = 0
    for text in lines[1:]:
        raw = text.strip()
        if text.count('"') % 2:
            problems.append("odd number of double quotes: %s" % raw)
        plain = re.sub(r"\|[^|]*\|", "||", strip_quoted(raw))
        for open_c, close_c in ("[]", "()", "{}"):
            if plain.count(open_c) != plain.count(close_c):
                problems.append("unbalanced %s%s: %s" % (open_c, close_c, raw))
        if flow:
            if re.match(r"subgraph\b", raw):
                depth += 1
            elif raw == "end":
                depth -= 1
            for label in re.findall(r"\w\[([^\]\"([/\\][^\]]*)\]", raw):  # shapes such as [("x")] and [[x]] start with a bracket
                if re.search(r"[()]", label):
                    problems.append("parentheses inside an unquoted label (quote the label): %s" % raw)
    if flow and depth != 0:
        problems.append("subgraph/end do not match")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("files", nargs="*", help="Markdown files to check (default: every tracked .md)")
    ap.add_argument("--install", action="store_true", help="install the Mermaid parser into the cache (downloads from npm)")
    ap.add_argument("--structural", action="store_true", help="skip the real parser, run only the structural check")
    ap.add_argument("--cache", default=os.environ.get("DOCS_GEN_MERMAID_DIR") or str(Path.home() / ".cache" / "docs-generation" / "mermaid"))
    args = ap.parse_args()

    root = Path(args.root).resolve()
    paths = [Path(f).resolve() for f in args.files] or markdown_files(root)
    blocks = [b for p in paths for b in extract_blocks(p, root)]
    if not blocks:
        print("check_mermaid: no mermaid blocks found")
        return 0

    results, mode, why = None, "structural (weaker)", ""
    node = None if args.structural else find_node()
    if node:
        results, why = real_parse(blocks, node, Path(args.cache), args.install)
        if results is not None:
            mode = "real Mermaid parser"
    elif not args.structural:
        why = "Node.js not found"
    if results is None:
        results = []
        for b in blocks:
            problems = structural(b)
            results.append({"file": b["file"], "line": b["line"], "ok": not problems, "error": "; ".join(problems)})

    bad = [r for r in results if not r["ok"]]
    for r in bad:
        print("ERROR %s:%d  %s" % (r["file"], r["line"], r["error"]))
    if why and mode.startswith("structural") and not args.structural:
        print("note: %s, so only the structural check ran" % why)
    print("check_mermaid: %d diagram(s) in %d file(s), %d with errors (%s)" % (len(results), len({r["file"] for r in results}), len(bad), mode))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
