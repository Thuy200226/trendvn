"""One line per event on stdout: `./trendvn logs worker` (docker logs) shows it. Never includes tokens, cookies or request bodies."""

import re
import time

CONTROL = re.compile(
    r"[\x00-\x08\x0b-\x1f\x7f]"
)  # keeps tab and newline (tracebacks); drops what could forge a log line or move a terminal


def log(message):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + CONTROL.sub("?", message), flush=True)
