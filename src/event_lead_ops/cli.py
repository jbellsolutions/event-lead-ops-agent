from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .db import connect, init_db, status_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="event-lead-ops")
    parser.add_argument("--db", default="state/event-lead-ops.sqlite3")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="apply SQLite migrations")
    sub.add_parser("status", help="print redacted database status as JSON")
    health = sub.add_parser("health", help="alias for status until live adapters are installed")
    health.add_argument("source", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.db)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    if args.command == "init-db":
        init_db(db)
        print(json.dumps({"database": str(path), "initialized": True}))
        return 0
    init_db(db)
    summary = status_summary(db)
    if args.command == "health" and args.source:
        summary["health"] = [x for x in summary["health"] if x["source"] == args.source]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
