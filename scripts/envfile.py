"""One reader for `.env`, shared by every tool (setup, doctor, n8n tools, the browser agent, restore), following the same rules as
`docker compose`, so a value means the same thing to all of them:
  - blank lines and lines starting with '#' are ignored; an optional `export ` prefix is accepted
  - KEY=value            an unquoted value ends at whitespace followed by '#' (an inline comment)
  - KEY='value # kept'   quotes are removed and everything inside them is kept
  - the last assignment of a key wins; an empty value counts as "not set" for callers (they test truthiness)
Only the `$` interpolation of Compose is not emulated: write `$$` for a literal dollar in .env values used by containers.
"""

import re
from pathlib import Path

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def parse_value(raw):
    stripped = raw.strip()
    if stripped[:1] in ('"', "'"):
        end = stripped.find(stripped[0], 1)
        return stripped[1:end] if end > 0 else stripped[1:]
    # a comment starts at a '#' that begins the value or follows whitespace ("KEY=   # note" is an empty value, "KEY=a#b" is "a#b")
    return re.split(r"(?:^|\s)#", raw, maxsplit=1)[0].strip()


def parse(path):
    """{KEY: value} of a .env file; {} if it does not exist."""
    out = {}
    path = Path(path)
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            out[m.group(1)] = parse_value(m.group(2))
    return out


def format_line(key, value):
    """KEY=value that parse() reads back unchanged (quotes only when the value needs them)."""
    if re.search(r"[\s#]", value) and "'" not in value:
        return "%s='%s'" % (key, value)
    return "%s=%s" % (key, value)
