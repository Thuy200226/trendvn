"""`./trendvn tiktok <login|trust|status|dry-run|verify|stats>`: the owner's commands for the publisher."""

import json
import sys

from .jobs import dry_run_next, run_stats, verify_unresolved
from .session import login, session_status, trust

USAGE = "usage: publisher login|trust|status|dry-run|verify|stats [minutes] [--account ID]"


def _split(argv):
    """(arguments without --account, account id or None): `login 5 --account pets` -> (['login', '5'], 'pets')."""
    if "--account" in argv:
        index = argv.index("--account")
        if index + 1 >= len(argv):
            raise SystemExit("--account needs an id")
        return argv[:index] + argv[index + 2 :], argv[index + 1]
    return argv, None


def _minutes(argv, default):
    return int(argv[1]) if len(argv) > 1 else default


def main(argv=None):
    argv, account = _split(list(sys.argv[1:] if argv is None else argv))
    command = argv[0] if argv else "status"
    if command == "login":
        print("OK" if login(_minutes(argv, 10), account) else "TIMEOUT")
    elif command == "trust":
        print("OK" if trust(_minutes(argv, 15), account) else "TIMEOUT")
    elif command == "status":
        print(json.dumps(session_status(deep=True, account=account), ensure_ascii=False))
    elif command == "dry-run":
        print(json.dumps(dry_run_next(), ensure_ascii=False))
    elif command == "stats":
        print(json.dumps(run_stats(), ensure_ascii=False))
    elif command == "verify":
        print(json.dumps(verify_unresolved(), ensure_ascii=False))
    else:
        print(USAGE)


if __name__ == "__main__":
    main()
