"""`./trendvn tiktok <login|trust|status|dry-run|verify|stats>`: the owner's commands for the publisher."""

import json
import sys

from .jobs import dry_run_next, report_login, run_stats, verify_unresolved
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


def _account_username(account):
    """(known, username): whether the worker knows this account id, and its TikTok name. If the worker cannot be asked, anything goes."""
    from ..worker_client import worker_get

    try:
        accounts = worker_get("/api/status").get("accounts", [])
    except Exception:
        return True, None
    for entry in accounts:
        if entry["id"] == (account or "main"):
            return True, entry["username"]
    return False, None


def main(argv=None):
    argv, account = _split(list(sys.argv[1:] if argv is None else argv))
    command = argv[0] if argv else "status"
    known, username = _account_username(account) if command in ("login", "trust", "status") else (True, None)
    if not known:
        raise SystemExit("Không có tài khoản có mã %r. Thêm nó ở bảng điều khiển → Thêm → Tài khoản TikTok và chủ đề." % account)
    if command == "login":
        print("OK" if login(_minutes(argv, 10), account, expected=username) else "TIMEOUT")
    elif command == "trust":
        print("OK" if trust(_minutes(argv, 15), account) else "TIMEOUT")
    elif command == "status":
        status = session_status(deep=True, account=account, expected=username)
        print(json.dumps(status, ensure_ascii=False))
        if username is not None:  # the worker is reachable: let it know, so the schedule stops or resumes using this account
            report_login(account, bool(status.get("logged_in")))
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
