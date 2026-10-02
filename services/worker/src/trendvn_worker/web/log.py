"""One line per event on stdout: `./trendvn logs worker` (docker logs) shows it. Never includes tokens, cookies or request bodies."""

import re
import time

# keeps tab and newline (tracebacks); drops what could forge a log line or move a terminal, C1 controls (0x80-0x9f) included
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def log(message):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + CONTROL.sub("?", message), flush=True)
