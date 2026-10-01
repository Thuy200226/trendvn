"""One line per event on stdout: `./trendvn logs worker` (docker logs) shows it. Never includes tokens, cookies or request bodies."""

import time


def log(message):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + message, flush=True)
