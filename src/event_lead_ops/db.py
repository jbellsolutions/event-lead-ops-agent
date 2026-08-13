from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import HealthStatus, OperationMode, ProposedAction, SourceRecord
from .policy import ApprovalEnvelope, assert_write_allowed, make_idempotency_key, payload_hash

PACKAGE_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
REPOSITORY_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATIONS_DIR = (
    PACKAGE_MIGRATIONS_DIR
    if PACKAGE_MIGRATIONS_DIR.is_dir()
    else REPOSITORY_MIGRATIONS_DIR
)


def iso(value: datetime | None = None) -> str:
    return (value or datetime.now(UTC)).astimezone(UTC).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db(db: sqlite3.Connection, migrations_dir: str | Path | None = None) -> None:
    directory = Path(migrations_dir) if migrations_dir else MIGRATIONS_DIR
    db.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL
        )"""
    )
    for migration in sorted(directory.glob("*.sql")):
        version = migration.stem
        applied = db.execute(
            "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
        ).fetchone()
        if applied:
            continue
        db.executescript(migration.read_text())
        db.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, iso()),
        )
    db.commit()


def record_source_health(
    db: sqlite3.Connection,
    *,
    source: str,
    status: HealthStatus,
    account_alias: str = "default",
    route: str | None = None,
    detail: str | None = None,
    evidence_path: str | None = None,
    checked_at: datetime | None = None,
    certified_at: datetime | None = None,
) -> None:
    if status is HealthStatus.HEALTHY and (not route or certified_at is None):
        raise ValueError("healthy status requires route and certification time")
    db.execute(
        """INSERT INTO source_health
        (source, account_alias, status, route, checked_at, certified_at, detail, evidence_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, account_alias) DO UPDATE SET
        status=excluded.status, route=excluded.route, checked_at=excluded.checked_at,
        certified_at=excluded.certified_at, detail=excluded.detail,
        evidence_path=excluded.evidence_path""",
        (
            source,
            account_alias,
            status.value,
            route,
            iso(checked_at),
            iso(certified_at) if certified_at else None,
            detail,
            evidence_path,
        ),
    )
    db.commit()


def _record_id(source: str, external_id: str) -> str:
    return hashlib.sha256(f"{source}:{external_id}".encode()).hexdigest()[:32]


def _record_values(record: SourceRecord) -> dict[str, Any]:
    now = iso()
    metadata_json = json.dumps(record.metadata, sort_keys=True, separators=(",", ":"))
    content_material = json.dumps(
        {
            "title": record.title,
            "body": record.body,
            "location": record.location,
            "price_minor": record.price_minor,
            "currency": record.currency,
            "posted_at": iso(record.posted_at) if record.posted_at else None,
            "metadata": record.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    content_hash = hashlib.sha256(content_material.encode()).hexdigest()
    dedupe_material = "|".join(
        [
            record.source.lower().strip(),
            record.record_type.lower().strip(),
            " ".join(record.title.lower().split()),
            " ".join(record.location.lower().split()),
        ]
    )
    return {
        "id": _record_id(record.source, record.external_id),
        "source": record.source,
        "external_id": record.external_id,
        "record_type": record.record_type,
        "canonical_url": record.canonical_url,
        "title": record.title,
        "body": record.body,
        "location": record.location,
        "price_minor": record.price_minor,
        "currency": record.currency,
        "posted_at": iso(record.posted_at) if record.posted_at else None,
        "first_seen_at": now,
        "last_seen_at": now,
        "content_hash": content_hash,
        "dedupe_key": hashlib.sha256(dedupe_material.encode()).hexdigest(),
        "raw_evidence_path": record.raw_evidence_path,
        "metadata_json": metadata_json,
    }


def upsert_source_record(db: sqlite3.Connection, record: SourceRecord) -> str:
    """Return inserted, updated, or duplicate."""
    values = _record_values(record)
    existing = db.execute(
        """SELECT id, content_hash FROM source_records
        WHERE source=? AND (external_id=? OR canonical_url=?)""",
        (record.source, record.external_id, record.canonical_url),
    ).fetchone()
    if existing is None:
        columns = ", ".join(values)
        placeholders = ", ".join(f":{column}" for column in values)
        db.execute(f"INSERT INTO source_records ({columns}) VALUES ({placeholders})", values)
        db.commit()
        return "inserted"
    values["id"] = existing["id"]
    changed = existing["content_hash"] != values["content_hash"]
    db.execute(
        """UPDATE source_records SET
        external_id=:external_id, record_type=:record_type, canonical_url=:canonical_url,
        title=:title, body=:body, location=:location, price_minor=:price_minor,
        currency=:currency, posted_at=:posted_at, last_seen_at=:last_seen_at,
        content_hash=:content_hash, dedupe_key=:dedupe_key,
        raw_evidence_path=:raw_evidence_path, metadata_json=:metadata_json
        WHERE id=:id""",
        values,
    )
    db.commit()
    return "updated" if changed else "duplicate"


def create_proposed_action(
    db: sqlite3.Connection,
    *,
    source: str,
    action_type: str,
    payload: dict[str, Any],
    account_alias: str = "default",
    campaign_id: str | None = None,
) -> ProposedAction:
    hashed = payload_hash(payload)
    idempotency = make_idempotency_key(source, account_alias, action_type, payload)
    existing = db.execute(
        "SELECT * FROM proposed_actions WHERE idempotency_key=?", (idempotency,)
    ).fetchone()
    if existing:
        return ProposedAction(
            id=existing["id"], source=source, action_type=action_type, payload=payload,
            payload_hash=hashed, idempotency_key=idempotency,
            account_alias=account_alias, campaign_id=campaign_id,
        )
    action_id = uuid.uuid4().hex
    now = iso()
    db.execute(
        """INSERT INTO proposed_actions
        (id, source, account_alias, campaign_id, action_type, payload_json, payload_hash,
         idempotency_key, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?)""",
        (
            action_id, source, account_alias, campaign_id, action_type,
            json.dumps(payload, sort_keys=True, separators=(",", ":")), hashed,
            idempotency, now, now,
        ),
    )
    db.commit()
    return ProposedAction(
        id=action_id, source=source, action_type=action_type, payload=payload,
        payload_hash=hashed, idempotency_key=idempotency,
        account_alias=account_alias, campaign_id=campaign_id,
    )


def create_approval(
    db: sqlite3.Connection,
    proposed: ProposedAction,
    *,
    approver: str,
    expires_at: datetime,
) -> ApprovalEnvelope:
    approval_id = uuid.uuid4().hex
    try:
        db.execute("BEGIN IMMEDIATE")
        stored = db.execute(
            "SELECT payload_hash, status FROM proposed_actions WHERE id=?",
            (proposed.id,),
        ).fetchone()
        if stored is None:
            raise KeyError(proposed.id)
        if stored["payload_hash"] != proposed.payload_hash:
            raise RuntimeError("proposed action does not match stored payload")
        if stored["status"] != "pending_approval":
            raise RuntimeError(f"proposed action is not pending approval: {stored['status']}")
        db.execute(
            """INSERT INTO approvals
            (id, proposed_action_id, payload_hash, approver, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, 'approved', ?, ?)""",
            (approval_id, proposed.id, proposed.payload_hash, approver, iso(), iso(expires_at)),
        )
        db.execute(
            "UPDATE proposed_actions SET status='approved', updated_at=? WHERE id=?",
            (iso(), proposed.id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ApprovalEnvelope(
        approval_id=approval_id,
        proposed_action_id=proposed.id,
        approved_payload_hash=proposed.payload_hash,
        approver=approver,
        expires_at=expires_at,
    )


def begin_approved_action(
    db: sqlite3.Connection,
    *,
    proposed: ProposedAction,
    current_payload: dict[str, Any],
    approval: ApprovalEnvelope,
    mode: OperationMode,
    health: HealthStatus,
    now: datetime | None = None,
) -> tuple[str, bool]:
    """Atomically consume approval. Return (action_id, should_execute_platform_action)."""
    now = now or datetime.now(UTC)
    assert_write_allowed(
        mode=mode,
        health=health,
        proposed_action_id=proposed.id,
        current_payload=current_payload,
        approval=approval,
        now=now,
    )
    action_id = uuid.uuid4().hex
    try:
        db.execute("BEGIN IMMEDIATE")
        stored_action = db.execute(
            """SELECT source, account_alias, action_type, payload_hash, idempotency_key
            FROM proposed_actions WHERE id=?""",
            (proposed.id,),
        ).fetchone()
        if stored_action is None:
            raise KeyError(proposed.id)
        if (
            stored_action["source"] != proposed.source
            or stored_action["account_alias"] != proposed.account_alias
            or stored_action["action_type"] != proposed.action_type
            or stored_action["payload_hash"] != proposed.payload_hash
            or stored_action["idempotency_key"] != proposed.idempotency_key
        ):
            raise RuntimeError("proposed action does not match stored action")
        stored_health = db.execute(
            """SELECT status, route, certified_at FROM source_health
            WHERE source=? AND account_alias=?""",
            (stored_action["source"], stored_action["account_alias"]),
        ).fetchone()
        if (
            stored_health is None
            or stored_health["status"] != HealthStatus.HEALTHY.value
            or not stored_health["route"]
            or not stored_health["certified_at"]
        ):
            raise RuntimeError("database source health is not healthy")
        existing = db.execute(
            "SELECT id FROM actions WHERE idempotency_key=?",
            (stored_action["idempotency_key"],),
        ).fetchone()
        if existing:
            db.rollback()
            return existing["id"], False
        approval_row = db.execute(
            """SELECT proposed_action_id, status, payload_hash, expires_at
            FROM approvals WHERE id=?""",
            (approval.approval_id,),
        ).fetchone()
        if approval_row is None or approval_row["status"] != "approved":
            raise RuntimeError("approval is not available for consumption")
        if approval_row["proposed_action_id"] != proposed.id:
            raise RuntimeError("stored approval belongs to a different proposed action")
        if approval_row["payload_hash"] != payload_hash(current_payload):
            raise RuntimeError("stored approval payload hash does not match")
        if datetime.fromisoformat(approval_row["expires_at"]) <= now:
            raise RuntimeError("stored approval expired")
        db.execute(
            """INSERT INTO actions
            (id, proposed_action_id, approval_id, source, action_type, idempotency_key,
             payload_hash, status, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'executing', ?)""",
            (
                action_id, proposed.id, approval.approval_id, proposed.source,
                proposed.action_type, proposed.idempotency_key, proposed.payload_hash, iso(now),
            ),
        )
        db.execute(
            "UPDATE approvals SET status='consumed', consumed_at=? WHERE id=?",
            (iso(now), approval.approval_id),
        )
        db.execute(
            "UPDATE proposed_actions SET status='executing', updated_at=? WHERE id=?",
            (iso(now), proposed.id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return action_id, True


def finish_action(
    db: sqlite3.Connection,
    action_id: str,
    *,
    status: str,
    platform_external_id: str | None = None,
    platform_url: str | None = None,
    evidence_path: str | None = None,
    error_class: str | None = None,
    error_detail: str | None = None,
) -> None:
    if status not in {"succeeded", "failed", "needs_reconciliation"}:
        raise ValueError("invalid terminal action status")
    row = db.execute(
        "SELECT proposed_action_id, status FROM actions WHERE id=?", (action_id,)
    ).fetchone()
    if row is None:
        raise KeyError(action_id)
    if row["status"] != "executing":
        raise RuntimeError(f"action is not executing: {row['status']}")
    db.execute(
        """UPDATE actions SET status=?, platform_external_id=?, platform_url=?,
        evidence_path=?, finished_at=?, error_class=?, error_detail=? WHERE id=?""",
        (
            status, platform_external_id, platform_url, evidence_path, iso(),
            error_class, error_detail, action_id,
        ),
    )
    db.execute(
        "UPDATE proposed_actions SET status=?, updated_at=? WHERE id=?",
        (status, iso(), row["proposed_action_id"]),
    )
    db.commit()


def status_summary(db: sqlite3.Connection) -> dict[str, Any]:
    return {
        "source_records": db.execute("SELECT COUNT(*) FROM source_records").fetchone()[0],
        "pending_approvals": db.execute(
            "SELECT COUNT(*) FROM proposed_actions WHERE status='pending_approval'"
        ).fetchone()[0],
        "actions_succeeded": db.execute(
            "SELECT COUNT(*) FROM actions WHERE status='succeeded'"
        ).fetchone()[0],
        "actions_needing_reconciliation": db.execute(
            "SELECT COUNT(*) FROM actions WHERE status='needs_reconciliation'"
        ).fetchone()[0],
        "health": [
            dict(row)
            for row in db.execute(
                """SELECT source, account_alias, status, checked_at,
                certified_at, detail FROM source_health"""
            ).fetchall()
        ],
    }
