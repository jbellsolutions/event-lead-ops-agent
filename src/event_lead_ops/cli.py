from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .config import canonical_source, load_and_validate_config
from .db import (
    connect,
    init_db,
    record_authorized_approver,
    status_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="event-lead-ops")
    parser.add_argument("--db", default="state/event-lead-ops.sqlite3")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="apply SQLite migrations")
    sub.add_parser("status", help="print redacted database status as JSON")
    health = sub.add_parser("health", help="alias for status until live adapters are installed")
    health.add_argument("source", nargs="?")
    validate = sub.add_parser("validate-config", help="validate one configuration file")
    validate.add_argument("kind", choices=("business", "platforms", "scoring", "schedules"))
    validate.add_argument("path")
    approver = sub.add_parser("approver", help="manage database-owned approver identities")
    approver_sub = approver.add_subparsers(dest="approver_command", required=True)
    approver_add = approver_sub.add_parser("add")
    approver_add.add_argument("--provider", default="slack")
    approver_add.add_argument("--external-user-id", required=True)
    approver_add.add_argument("--operator-alias", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-config":
        load_and_validate_config(args.path, kind=args.kind)
        print(json.dumps({"kind": args.kind, "path": args.path, "valid": True}))
        return 0
    path = Path(args.db)
    db = connect(path)
    if args.command == "init-db":
        init_db(db)
        print(json.dumps({"database": str(path), "initialized": True}))
        return 0
    init_db(db)
    if args.command == "approver":
        record_authorized_approver(
            db,
            provider=args.provider,
            external_user_id=args.external_user_id,
            operator_alias=args.operator_alias,
        )
        print(json.dumps({"provider": args.provider, "registered": True}))
        return 0
    summary = status_summary(db)
    if args.command == "health" and args.source:
        source = canonical_source(args.source)
        summary["health"] = [x for x in summary["health"] if x["source"] == source]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
