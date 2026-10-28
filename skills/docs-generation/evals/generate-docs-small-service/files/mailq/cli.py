"""Command line: serve | worker | status | retry ID | resolve ID sent|retry | purge --days N."""
import sys
import time

from . import api, store, worker


def main(argv):
    cmd = argv[0] if argv else "status"
    db = store.connect()
    if cmd == "serve":
        api.serve()
    elif cmd == "worker":
        worker.loop()
    elif cmd == "status":
        for row in db.execute("SELECT state, COUNT(*) n FROM jobs GROUP BY state"):
            print("%-8s %d" % (row["state"], row["n"]))
    elif cmd == "retry":
        db.execute("UPDATE jobs SET state='pending', attempts=0, not_before=0 WHERE id=? AND state IN ('failed','dead')", (argv[1],))
    elif cmd == "resolve":
        print("ok" if store.resolve(db, argv[1], argv[2]) else "job is not in state unknown")
    elif cmd == "purge":
        days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 30
        db.execute("DELETE FROM jobs WHERE state IN ('sent','dead') AND updated<?", (time.time() - days * 86400,))
    else:
        sys.exit("unknown command: " + cmd)


if __name__ == "__main__":
    main(sys.argv[1:])
