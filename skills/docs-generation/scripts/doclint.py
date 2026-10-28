#!/usr/bin/env python3
"""Documentation linter for the docs-generation standard (Python 3.8+, standard library only).

Rules (see references/verification.md): required, links, reachable, one-h1, fences, flows-no-tech,
markers, paths, identifiers, commands, sections, budgets, fence-lang.
Errors exit 1; warnings print and exit 0 unless --strict. --final turns unfilled template markers into errors.
Optional config: .doclint.json at the root (or --config), see doclint.example.json.
"""

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULTS = {
    "docs_dir": "docs",
    "required": ["README.md", "docs/FLOWS.md", "docs/TECH.md", "docs/OPERATIONS.md", "docs/ROADMAP.md", "CHANGELOG.md"],
    "flows": "docs/FLOWS.md",
    "history_globs": ["docs/history/*", "CHANGELOG.md"],
    "extra_tech_terms": [],
    "allowed_tech_terms": [],
    "ignore_paths": [".env", ".env.*", "data/*", "node_modules/*", ".venv/*", "venv/*", "dist/*", "build/*", "*.log", "tmp/*"],
    "ignore_identifiers": [],
    "budgets": {"README.md": 60, "docs/FLOWS.md": 200, "docs/TECH.md": 300, "docs/OPERATIONS.md": 200, "docs/ROADMAP.md": 80},
    "commands": None,
    "marker_regex": r"\b(?:FILL:|TODO|TBD|XXX|FIXME)\b|lorem ipsum",
}

TECH_TERMS = [
    "docker", "containers?", "kubernetes", "k8s", "sqlite", "postgres(?:ql)?", "mysql", "mongodb", "redis", "kafka", "rabbitmq",
    "nginx", "https?", "api", "(?-i:REST)", "graphql", "grpc", "websockets?", "endpoints?", "json", "yaml", "sql", "regex", "token",
    "jwt", "oauth", "cron", "webhooks?", "leases?", "systemd", "launchd", "venv", "compose", "stdlib", "localhost",
]
SECTION_RULES = {  # document key -> (heading regex, what is missing)
    "flows": (r"goes wrong|fail|error|problem", "a failure table (what the system does, what you do)"),
    "tech": (r"security", "a security section"),
    "operations": (r"wrong|troubleshoot|fix|problem", "a troubleshooting table"),
    "roadmap": (r"not verified", "a 'Not verified' section"),
}
PATH_EXT = (
    r"py|js|jsx|ts|tsx|mjs|cjs|sh|bash|zsh|json|ya?ml|toml|ini|cfg|md|go|rs|rb|java|kt|swift|c|h|cpp|hpp|cs|php|sql|html|css|scss|txt|lock|drawio|mmd"
)
FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^\s`]*)")
FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, rule, rel, line, msg):
        self.items.append((level, rule, rel, line, msg))

    def count(self, level):
        return sum(1 for i in self.items if i[0] == level)


def load_config(root, path):
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg_path = Path(path) if path else root / ".doclint.json"
    if cfg_path.is_file():
        user = json.loads(cfg_path.read_text(encoding="utf-8"))
        for key, value in user.items():
            if key.startswith("_"):
                continue
            if isinstance(cfg.get(key), dict) and isinstance(value, dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    return cfg


def index_files(root):
    """Relative paths of the repository's files: git's view when available, else a walk."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=True,
        ).stdout.decode("utf-8", "replace")
        files = [f for f in out.split("\0") if f and (root / f).is_file()]
        if files:
            return sorted(files)
    except (OSError, subprocess.CalledProcessError):
        pass
    found = []
    for base, dirs, names in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            found.append(os.path.relpath(os.path.join(base, name), str(root)).replace(os.sep, "/"))
    return sorted(found)


def suffix_set(paths):
    """Every trailing run of segments of every path and of every directory, for 'does this path exist anywhere' lookups."""
    out = set()
    for p in paths:
        parts = p.split("/")
        for i in range(len(parts)):
            out.add("/".join(parts[i:]))
        for j in range(1, len(parts)):
            for i in range(j):
                out.add("/".join(parts[i:j]))
    return out


def scan_fences(lines):
    blocks, cur = [], None
    for n, line in enumerate(lines, 1):
        if cur is None:
            m = FENCE_OPEN.match(line)
            if m:
                cur = {"start": n, "char": m.group(2)[0], "len": len(m.group(2)), "lang": m.group(3)}
        else:
            m = FENCE_CLOSE.match(line)
            if m and m.group(1)[0] == cur["char"] and len(m.group(1)) >= cur["len"]:
                cur["end"] = n
                blocks.append(cur)
                cur = None
    if cur is not None:
        cur["end"] = None
        blocks.append(cur)
    return blocks


def prose_lines(lines):
    """(line number, text) of lines outside fenced code, with inline code spans removed."""
    inside = set()
    for b in scan_fences(lines):
        inside.update(range(b["start"], (b["end"] or len(lines)) + 1))
    return [(n, re.sub(r"`[^`]*`", "", line)) for n, line in enumerate(lines, 1) if n not in inside]


def slug(heading):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"[`*]", "", text).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors_of(lines):
    seen, out = {}, set()
    for n, line in prose_lines(lines):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            base = slug(m.group(2))
            k = seen.get(base, 0)
            seen[base] = k + 1
            out.add(base if k == 0 else "%s-%d" % (base, k))
    return out


class Docs:
    def __init__(self, root, cfg, files):
        self.root, self.cfg = root, cfg
        docs_dir = cfg["docs_dir"].strip("/")
        self.paths = [
            f for f in files
            if f.endswith(".md") and ("/" not in f or f.startswith(docs_dir + "/"))
        ]
        self.text = {f: (root / f).read_text(encoding="utf-8", errors="replace") for f in self.paths}
        self.lines = {f: t.split("\n") for f, t in self.text.items()}

    def history(self, rel):
        return any(fnmatch.fnmatch(rel, g) for g in self.cfg["history_globs"])

    def live(self):
        return [f for f in self.paths if not self.history(f)]


def rule_required(rep, d):
    for rel in d.cfg["required"]:
        if not (d.root / rel).is_file():
            rep.add("error", "required", rel, 0, "missing document")


def rule_links(rep, d):
    anchor_cache = {}

    def anchors(rel):
        if rel not in anchor_cache:
            anchor_cache[rel] = anchors_of(d.lines[rel]) if rel in d.lines else None
        return anchor_cache[rel]

    for rel in d.paths:
        for n, line in prose_lines(d.lines[rel]):
            for target in re.findall(r"\]\(([^)\s]+)\)", line):
                if re.match(r"(https?:|mailto:|tel:)", target):
                    continue
                path, _, frag = target.partition("#")
                dest = (d.root / rel).parent / path if path else d.root / rel
                if not dest.resolve().exists():
                    rep.add("error", "links", rel, n, "broken link: %s" % target)
                elif frag and dest.suffix == ".md":
                    try:
                        key = dest.resolve().relative_to(d.root.resolve()).as_posix()
                    except ValueError:
                        continue
                    found = anchors(key)
                    if found is not None and slug(frag) not in found and frag not in found:
                        rep.add("error", "links", rel, n, "anchor not found: %s" % target)


def links_from(d, rel):
    out = set()
    for _, line in prose_lines(d.lines[rel]):
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            if not re.match(r"(https?:|mailto:|tel:|#)", target) and target.split("#")[0]:
                out.add(((d.root / rel).parent / target.split("#")[0]).resolve())
    return out


def rule_reachable(rep, d, files):
    docs_dir = d.cfg["docs_dir"].strip("/")
    readme = "README.md"
    if readme not in d.lines:
        return
    from_readme = links_from(d, readme)
    from_any = set()
    for rel in d.paths:
        from_any |= links_from(d, rel)
    for f in files:
        if not f.startswith(docs_dir + "/") or not f.endswith((".md", ".drawio")):
            continue
        top_level = f.count("/") == 1
        target = (d.root / f).resolve()
        if top_level and f.endswith(".md") and target not in from_readme:
            rep.add("error", "reachable", f, 0, "not linked from README.md (the document map)")
        elif not top_level and target not in from_any:
            rep.add("error", "reachable", f, 0, "no document links to it")


def rule_one_h1(rep, d):
    for rel in d.paths:
        titles = sum(1 for _, line in prose_lines(d.lines[rel]) if re.match(r"# \S", line))
        if titles != 1:
            rep.add("error", "one-h1", rel, 0, "%d H1 headings (need exactly 1)" % titles)


def rule_fences(rep, d):
    for rel in d.paths:
        for b in scan_fences(d.lines[rel]):
            if b["end"] is None:
                rep.add("error", "fences", rel, b["start"], "code fence is never closed")
            elif not b["lang"]:
                rep.add("warning", "fence-lang", rel, b["start"], "code fence has no language tag")


def rule_flows_no_tech(rep, d):
    rel = d.cfg["flows"]
    if rel not in d.text:
        return
    terms = [t for t in TECH_TERMS if t not in d.cfg["allowed_tech_terms"]] + list(d.cfg["extra_tech_terms"])
    pattern = re.compile(r"\b(%s)\b|/api/" % "|".join(terms), re.I)
    body = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), d.text[rel], flags=re.S)
    for n, line in enumerate(body.split("\n"), 1):
        if line.lstrip().startswith("%%"):
            continue
        m = pattern.search(line)
        if m:
            rep.add("error", "flows-no-tech", rel, n, "technology term '%s': it belongs in TECH.md" % m.group(0))


def rule_markers(rep, d, final):
    pattern = re.compile(d.cfg["marker_regex"])
    for rel in d.live():
        for n, line in enumerate(d.lines[rel], 1):
            m = pattern.search(line)
            if m:
                rep.add("error" if final else "warning", "markers", rel, n, "unfinished marker '%s'" % m.group(0))


def looks_like_path(tok):
    if re.search(r"[\s*<>{}$|;&=,()\[\]]|://", tok) or tok.startswith(("-", "~", "/", "$", "@", "#")):
        return False
    body = tok.rstrip("/")
    if not re.fullmatch(r"[\w.\-/]+", body):
        return False
    if tok.startswith(("./", "../")) or tok.endswith("/"):
        return True
    return bool(re.search(r"\.(?:%s)$" % PATH_EXT, body))


def rule_paths(rep, d, files, known):
    dirs_first = {f.split("/")[0] for f in files if "/" in f}
    for rel in d.live():
        for n, line in prose_lines_with_code(d.lines[rel]):
            for tok in re.findall(r"`([^`\n]+)`", line):
                tok = re.sub(r":\d+(?:-\d+)?$", "", tok)
                if ":" in tok and looks_like_path(tok.split(":")[0]):
                    tok = tok.split(":")[0]
                if not looks_like_path(tok):
                    continue
                norm = tok.rstrip("/")
                while norm.startswith("./"):
                    norm = norm[2:]
                if norm.startswith("../"):
                    continue
                if "/" in norm and not tok.endswith("/") and not re.search(r"\.(?:%s)$" % PATH_EXT, norm) and norm.split("/")[0] not in dirs_first:
                    continue
                if any(fnmatch.fnmatch(norm + "/", g) or fnmatch.fnmatch(norm, g) for g in d.cfg["ignore_paths"]):
                    continue
                if norm in known or (d.root / rel).parent.joinpath(norm).exists():
                    continue
                rep.add("error", "paths", rel, n, "no such path in the repo: %s (a file made at run time? add it to ignore_paths)" % tok)


def prose_lines_with_code(lines):
    """Lines outside fenced blocks, inline code kept (the path and identifier rules read it)."""
    inside = set()
    for b in scan_fences(lines):
        inside.update(range(b["start"], (b["end"] or len(lines)) + 1))
    return [(n, line) for n, line in enumerate(lines, 1) if n not in inside]


def source_words(root, files):
    words, total = set(), 0
    for f in files:
        if f.endswith((".md", ".drawio", ".lock", ".png", ".jpg", ".svg", ".gif", ".ico", ".pdf")):
            continue
        try:
            data = (root / f).read_bytes()
        except OSError:
            continue
        if len(data) > 1_000_000 or b"\0" in data[:2048]:
            continue
        total += len(data)
        if total > 200_000_000:
            break
        words.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", data.decode("utf-8", "ignore")))
    return words


def rule_identifiers(rep, d, files):
    words = source_words(d.root, files)
    func = re.compile(r"[A-Za-z_][\w.]*\(\)")
    const = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")
    snake = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
    ignore = set(d.cfg["ignore_identifiers"])
    for rel in d.live():
        seen = set()
        for n, line in prose_lines_with_code(d.lines[rel]):
            for tok in re.findall(r"`([^`\n]+)`", line):
                if tok in ignore or tok in seen:
                    continue
                if func.fullmatch(tok):
                    parts = tok[:-2].split(".")
                elif const.fullmatch(tok) or snake.fullmatch(tok):
                    parts = [tok]
                else:
                    continue
                seen.add(tok)
                if not all(p in words for p in parts[-1:]):
                    rep.add("warning", "identifiers", rel, n, "'%s' does not appear in the source" % tok)


def rule_commands(rep, d):
    cfg = d.cfg["commands"]
    if not cfg:
        return False
    prefix = cfg["prefix"]
    try:
        out = subprocess.run(cfg["help"], shell=True, cwd=str(d.root), capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        rep.add("error", "commands", "(config)", 0, "could not run the help command: %s" % cfg["help"])
        return True
    top, subs = set(cfg.get("extra", ["help", "version"])), {}
    for line in out.splitlines():
        m = re.match(r"^  ([a-z0-9-]+)((?:[ |][a-z0-9|-]+)*)", line)
        if m:
            top.add(m.group(1))
            for tok in re.findall(r"[a-z0-9-]+", m.group(2).split("[")[0]):
                subs.setdefault(m.group(1), set()).add(tok)
    needs_sub = set(cfg.get("needs_sub", []))
    rx = re.compile(re.escape(prefix) + r" ([a-z0-9-]+)(?: ([a-z0-9-]+))?")
    for rel in d.live():
        for n, line in enumerate(d.lines[rel], 1):
            for m in rx.finditer(line):
                cmd, sub = m.group(1), m.group(2)
                if cmd not in top:
                    rep.add("error", "commands", rel, n, "%s %s: no such command" % (prefix, cmd))
                elif cmd in needs_sub and sub and sub not in subs.get(cmd, set()) and not sub.isdigit():
                    rep.add("error", "commands", rel, n, "%s %s %s: no such sub-command (has: %s)" % (prefix, cmd, sub, ", ".join(sorted(subs.get(cmd, [])))))
    ref = cfg.get("reference_doc", "docs/OPERATIONS.md")
    if ref in d.text:
        for cmd in sorted(top - set(cfg.get("extra", ["help", "version"]))):
            if "%s %s" % (prefix, cmd) not in d.text[ref]:
                rep.add("error", "commands", ref, 0, "the CLI has '%s %s' but the document never mentions it" % (prefix, cmd))
    return True


def rule_sections(rep, d):
    keys = {"flows": d.cfg["flows"], "tech": "docs/TECH.md", "operations": "docs/OPERATIONS.md", "roadmap": "docs/ROADMAP.md"}
    for key, rel in keys.items():
        if rel not in d.lines:
            continue
        heads = [
            m.group(1)
            for _, line in prose_lines(d.lines[rel])
            for m in [re.match(r"^#{2,6}\s+(.*)$", line)]
            if m
        ]
        pattern, what = SECTION_RULES[key]
        if not any(re.search(pattern, h, re.I) for h in heads):
            rep.add("warning", "sections", rel, 0, "no heading for " + what)
    flows = d.cfg["flows"]
    if flows in d.text and "```mermaid" not in d.text[flows]:
        rep.add("warning", "sections", flows, 0, "no Mermaid diagram")


def rule_budgets(rep, d):
    for rel, limit in d.cfg["budgets"].items():
        if rel in d.lines and len(d.lines[rel]) > limit:
            rep.add("warning", "budgets", rel, 0, "%d lines, budget %d" % (len(d.lines[rel]), limit))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--config", help="config file (default: <root>/.doclint.json if present)")
    ap.add_argument("--final", action="store_true", help="unfilled markers are errors")
    ap.add_argument("--strict", action="store_true", help="warnings fail the run too")
    ap.add_argument("--only", help="comma-separated rule names to run")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg = load_config(root, args.config)
    files = index_files(root)
    d = Docs(root, cfg, files)
    known = suffix_set(files)
    only = set(args.only.split(",")) if args.only else None
    want = lambda name: only is None or name in only  # noqa: E731
    rep, skipped = Report(), []

    if want("required"):
        rule_required(rep, d)
    if want("links"):
        rule_links(rep, d)
    if want("reachable"):
        rule_reachable(rep, d, files)
    if want("one-h1"):
        rule_one_h1(rep, d)
    if want("fences") or want("fence-lang"):
        rule_fences(rep, d)
    if want("flows-no-tech"):
        rule_flows_no_tech(rep, d)
    if want("markers"):
        rule_markers(rep, d, args.final)
    if want("paths"):
        rule_paths(rep, d, files, known)
    if want("identifiers"):
        rule_identifiers(rep, d, files)
    if want("commands") and not rule_commands(rep, d):
        skipped.append("commands (no config)")
    if want("sections"):
        rule_sections(rep, d)
    if want("budgets"):
        rule_budgets(rep, d)

    for level, rule, rel, line, msg in sorted(rep.items, key=lambda i: (i[0] != "error", i[2], i[3])):
        print("%-7s %-13s %s%s  %s" % (level, rule, rel, ":%d" % line if line else "", msg))
    errors, warnings = rep.count("error"), rep.count("warning")
    note = "; skipped: " + ", ".join(skipped) if skipped else ""
    print("doclint: %d error(s), %d warning(s) in %d document(s)%s" % (errors, warnings, len(d.paths), note))
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
