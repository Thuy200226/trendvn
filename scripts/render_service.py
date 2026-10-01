#!/usr/bin/env python3
"""Render a service template (scripts/service/*.in) for this checkout: render_service.py <template> <project-root>.

Done in Python instead of sed so that a path or display variable can never break the result (sed needs escaping for '&', '|', newlines).
systemd units get DISPLAY / WAYLAND_DISPLAY lines from the current environment (a visible Chrome window needs to know the screen);
launchd plists get XML-escaped paths. Prints the result on stdout.
"""

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

template, root = Path(sys.argv[1]), sys.argv[2]
text = template.read_text()
if template.name.endswith(".plist.in"):
    print(text.replace("@ROOT@", escape(root)), end="")
else:
    display = [f"Environment={k}={os.environ[k]}" for k in ("DISPLAY", "WAYLAND_DISPLAY") if os.environ.get(k)]
    out = text.replace("@ROOT@", root.replace("%", "%%"))
    print(out.replace("@DISPLAYENV@\n", "".join(line + "\n" for line in display)), end="")
