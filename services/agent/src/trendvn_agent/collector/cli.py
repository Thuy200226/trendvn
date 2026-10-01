"""`python -m trendvn_agent.collector [douyin kuaishou tiktok instagram]`: scan for real and hand the results to the worker."""

import json
import sys

from . import SOURCES, collect


def main(argv=None):
    platforms = [a for a in (argv if argv is not None else sys.argv[1:]) if a in SOURCES]
    print(json.dumps(collect(platforms or None), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
