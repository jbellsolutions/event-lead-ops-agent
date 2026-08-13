from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    ExecutionReservation,
    HealthStatus,
    OperationMode,
    ProposedAction,
    RuntimeIdentity,
    SourceRecord,
)
from .policy import (
    ApprovalEnvelope,
    assert_write_allowed,
    canonical_json,
    make_idempotency_key,
    payload_hash,
)
from .profile_lock import ProfileLock
from .sources.craigslist import canonicalize_url as canonicalize_craigslist_url
from .sources.craigslist import listing_id_from_url as craigslist_id_from_url
from .sources.facebook_marketplace import canonicalize_url as canonicalize_facebook_url
from .sources.facebook_marketplace import listing_id_from_url as facebook_id_from_url

PACKAGE_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
REPOSITORY_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATIONS_DIR = (
    PACKAGE_MIGRATIONS_DIR
    if PACKAGE_MIGRATIONS_DIR.is_dir()
    else REPOSITORY_MIGRATIONS_DIR
)


def iso(value: datetime | None = None) -> str:
    value = value or datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("database timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _parse_database_timestamp(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"database timestamp is invalid: {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"database timestamp is not timezone-aware: {field}")
    return parsed.astimezone(UTC)


def _validate_action_evidence(
    path: str | None,
    *,
    evidence_root: Path,
    expected: dict[str, str | None],
) -> str:
    if not path:
        raise ValueError("action requires an existing evidence file")
    candidate = Path(path)
    try:
        link_stat = candidate.lstat()
    except FileNotFoundError as exc:
        raise ValueError("action requires an existing evidence file") from exc
    if stat.S_ISLNK(link_stat.st_mode) or not stat.S_ISREG(link_stat.st_mode):
        raise ValueError("action evidence must be a regular file, not a symlink")
    if stat.S_IMODE(link_stat.st_mode) & 0o077:
        raise ValueError("action evidence must be owner-only")
    evidence = candidate.resolve()
    root = evidence_root.resolve()
    if evidence.parent != root and root not in evidence.parents:
        raise ValueError("action evidence must be inside certified evidence root")
    payload_bytes = evidence.read_bytes()
    if len(payload_bytes) > 1_000_000:
        raise ValueError("action evidence manifest is too large")
    try:
        manifest = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("action evidence must be a JSON manifest") from exc
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("action evidence manifest does not match action")
    return hashlib.sha256(payload_bytes).hexdigest()


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    parent = db_path.parent
    if parent.exists():
        mode = stat.S_IMODE(parent.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"database parent must be owner-only (0700 or stricter): {parent}"
            )
    else:
        parent.mkdir(parents=True, exist_ok=False, mode=0o700)
        parent.chmod(0o700)
    descriptor = os.open(db_path, os.O_CREAT | os.O_APPEND, 0o600)
    os.close(descriptor)
    os.chmod(db_path, 0o600)
    db = sqlite3.connect(str(db_path), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 30000")
    db.execute("PRAGMA foreign_keys = ON")
    for attempt in range(30):
        try:
            mode = db.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise RuntimeError(f"failed to enable WAL mode: {mode}")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 29:
                db.close()
                raise
            time.sleep(0.05)
    return db


def _migration_statements(sql: str) -> list[str]:
    connection_pragmas = {
        "PRAGMA FOREIGN_KEYS = ON;",
        "PRAGMA JOURNAL_MODE = WAL;",
    }
    statements: list[str] = []
    pending = ""
    for line in sql.splitlines(keepends=True):
        if line.strip().upper() in connection_pragmas:
            continue
        pending += line
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            if statement:
                statements.append(statement)
            pending = ""
    if pending.strip():
        raise RuntimeError("migration contains an incomplete SQL statement")
    return statements


def init_db(db: sqlite3.Connection, migrations_dir: str | Path | None = None) -> None:
    directory = Path(migrations_dir) if migrations_dir else MIGRATIONS_DIR
    migrations = sorted(directory.glob("*.sql"))
    if not migrations:
        raise RuntimeError(f"no database migrations found in {directory}")
    db.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL
        )"""
    )
    db.commit()
    for migration in migrations:
        version = migration.stem
        try:
            db.execute("BEGIN IMMEDIATE")
            applied = db.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
            ).fetchone()
            if applied:
                db.rollback()
                continue
            for statement in _migration_statements(migration.read_text()):
                db.execute(statement)
            db.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, iso()),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise


def record_source_policy(
    db: sqlite3.Connection,
    *,
    source: str,
    mode: OperationMode,
    account_alias: str = "default",
    certification_ttl_hours: int = 24,
    execution_timeout_minutes: int = 15,
) -> None:
    if not 1 <= certification_ttl_hours <= 24:
        raise ValueError("certification TTL must be at most 24 hours and positive")
    if execution_timeout_minutes <= 0:
        raise ValueError("policy durations must be positive")
    db.execute(
        """INSERT INTO source_policies
        (source, account_alias, mode, certification_ttl_hours,
         execution_timeout_minutes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, account_alias) DO UPDATE SET
        mode=excluded.mode,
        certification_ttl_hours=excluded.certification_ttl_hours,
        execution_timeout_minutes=excluded.execution_timeout_minutes,
        updated_at=excluded.updated_at""",
        (
            source,
            account_alias,
            mode.value,
            certification_ttl_hours,
            execution_timeout_minutes,
            iso(),
        ),
    )
    db.commit()


def record_authorized_approver(
    db: sqlite3.Connection,
    *,
    external_user_id: str,
    operator_alias: str,
    provider: str = "slack",
    active: bool = True,
) -> None:
    if not external_user_id or not operator_alias:
        raise ValueError("approver ID and alias are required")
    now = iso()
    db.execute(
        """INSERT INTO authorized_approvers
        (provider, external_user_id, operator_alias, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, external_user_id) DO UPDATE SET
        operator_alias=excluded.operator_alias, active=excluded.active,
        updated_at=excluded.updated_at""",
        (provider, external_user_id, operator_alias, int(active), now, now),
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
    runtime: RuntimeIdentity | None = None,
    profile_lock: ProfileLock | None = None,
) -> None:
    if status is HealthStatus.HEALTHY:
        if not route or certified_at is None or runtime is None or profile_lock is None:
            raise ValueError(
                "healthy status requires route, certification time, runtime, and profile lock"
            )
        if (
            runtime.source != source
            or runtime.account_alias != account_alias
            or runtime.route != route
        ):
            raise ValueError("runtime identity does not match health identity")
        if certified_at.tzinfo is None or certified_at.utcoffset() is None:
            raise ValueError("health certification time must be timezone-aware")
        certified_at = certified_at.astimezone(UTC)
        if certified_at > datetime.now(UTC):
            raise ValueError("health certification time cannot be in the future")
        profile_lock.assert_owned(runtime.profile_dir)
        evidence_root = Path(runtime.evidence_root)
        if not evidence_root.is_dir():
            raise ValueError("runtime evidence root must be an existing directory")
        runtime_json = json.dumps(runtime.as_dict(), sort_keys=True, separators=(",", ":"))
        runtime_fingerprint = runtime.fingerprint
    else:
        runtime_json = None
        runtime_fingerprint = None
    db.execute(
        """INSERT INTO source_health
        (source, account_alias, status, route, browser_version, checked_at, certified_at,
         detail, evidence_path, runtime_fingerprint, runtime_json, evidence_root)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, account_alias) DO UPDATE SET
        status=excluded.status, route=excluded.route,
        browser_version=excluded.browser_version, checked_at=excluded.checked_at,
        certified_at=excluded.certified_at, detail=excluded.detail,
        evidence_path=excluded.evidence_path,
        runtime_fingerprint=excluded.runtime_fingerprint,
        runtime_json=excluded.runtime_json, evidence_root=excluded.evidence_root""",
        (
            source,
            account_alias,
            status.value,
            route,
            runtime.browser_major_version if runtime else None,
            iso(checked_at),
            iso(certified_at) if certified_at else None,
            detail,
            evidence_path,
            runtime_fingerprint,
            runtime_json,
            runtime.evidence_root if runtime else None,
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


def upsert_campaign(
    db: sqlite3.Connection,
    *,
    campaign_id: str,
    name: str,
    business_alias: str,
    offer_id: str,
    status: str = "draft",
    cooldown_hours: int = 24,
    config: dict[str, Any] | None = None,
) -> None:
    if status not in {"draft", "active", "paused", "archived"}:
        raise ValueError("invalid campaign status")
    if isinstance(cooldown_hours, bool) or cooldown_hours <= 0:
        raise ValueError("campaign cooldown_hours must be a positive integer")
    now = iso()
    db.execute(
        """INSERT INTO campaigns
        (id, name, business_alias, offer_id, status, config_json, cooldown_hours,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET name=excluded.name,
        business_alias=excluded.business_alias, offer_id=excluded.offer_id,
        status=excluded.status, config_json=excluded.config_json,
        cooldown_hours=excluded.cooldown_hours,
        updated_at=excluded.updated_at""",
        (
            campaign_id,
            name,
            business_alias,
            offer_id,
            status,
            json.dumps(config or {}, sort_keys=True, separators=(",", ":")),
            cooldown_hours,
            now,
            now,
        ),
    )
    db.commit()


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
    idempotency = make_idempotency_key(
        source, account_alias, campaign_id, action_type, payload
    )
    action_id = uuid.uuid4().hex
    now = iso()
    try:
        db.execute("BEGIN IMMEDIATE")
        cooldown_hours = None
        if action_type in {"publish_listing", "repost_listing"}:
            if not campaign_id:
                raise ValueError("listing publication requires campaign_id")
            campaign = db.execute(
                "SELECT cooldown_hours FROM campaigns WHERE id=?", (campaign_id,)
            ).fetchone()
            if campaign is None:
                raise ValueError("listing publication requires a stored campaign")
            cooldown_hours = campaign["cooldown_hours"]
        existing = db.execute(
            "SELECT * FROM proposed_actions WHERE idempotency_key=?", (idempotency,)
        ).fetchone()
        if existing:
            db.rollback()
            stored_payload = json.loads(existing["payload_json"])
            return ProposedAction(
                id=existing["id"], source=existing["source"],
                action_type=existing["action_type"], payload=stored_payload,
                payload_hash=existing["payload_hash"],
                idempotency_key=existing["idempotency_key"],
                account_alias=existing["account_alias"], campaign_id=existing["campaign_id"],
                attempt=existing["attempt"], retry_of=existing["retry_of"],
            )
        if action_type in {"publish_listing", "repost_listing"}:
            assert campaign_id is not None and cooldown_hours is not None
            unresolved = db.execute(
                """SELECT id FROM proposed_actions
                WHERE source=? AND account_alias=? AND campaign_id=? AND action_type IN
                ('publish_listing', 'repost_listing')
                AND status IN ('pending_approval', 'approved', 'executing',
                               'needs_reconciliation')
                LIMIT 1""",
                (source, account_alias, campaign_id),
            ).fetchone()
            if unresolved:
                raise RuntimeError(
                    f"campaign cooldown blocks new listing action: {unresolved['id']}"
                )
            cutoff = iso(datetime.now(UTC) - timedelta(hours=cooldown_hours))
            recent_terminal = db.execute(
                """SELECT pa.id FROM proposed_actions AS pa
                JOIN actions AS a ON a.proposed_action_id=pa.id
                WHERE pa.source=? AND pa.account_alias=? AND pa.campaign_id=?
                AND pa.action_type IN ('publish_listing', 'repost_listing')
                AND ((a.status='succeeded') OR
                     (a.status='failed' AND a.error_class='confirmed_no_submit'))
                AND a.finished_at>=? LIMIT 1""",
                (source, account_alias, campaign_id, cutoff),
            ).fetchone()
            if recent_terminal:
                raise RuntimeError(
                    f"campaign cooldown blocks new listing action: {recent_terminal['id']}"
                )
        db.execute(
            """INSERT INTO proposed_actions
            (id, source, account_alias, campaign_id, action_type, payload_json, payload_hash,
             idempotency_key, status, created_at, updated_at, cooldown_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?, ?)""",
            (
                action_id, source, account_alias, campaign_id, action_type,
                json.dumps(payload, sort_keys=True, separators=(",", ":")), hashed,
                idempotency, now, now, cooldown_hours,
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ProposedAction(
        id=action_id, source=source, action_type=action_type, payload=payload,
        payload_hash=hashed, idempotency_key=idempotency,
        account_alias=account_alias, campaign_id=campaign_id,
    )


def create_retry_proposed_action(
    db: sqlite3.Connection,
    failed_proposed_action_id: str,
) -> ProposedAction:
    retry_id = uuid.uuid4().hex
    now = iso()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM proposed_actions WHERE id=?", (failed_proposed_action_id,)
        ).fetchone()
        if row is None:
            raise KeyError(failed_proposed_action_id)
        if row["status"] != "failed":
            raise RuntimeError("only a confirmed failed action can be retried")
        action = db.execute(
            """SELECT error_class, evidence_path, evidence_sha256, finished_at FROM actions
            WHERE proposed_action_id=? AND status='failed'""",
            (failed_proposed_action_id,),
        ).fetchone()
        if (
            action is None
            or action["error_class"] != "confirmed_no_submit"
            or not action["evidence_path"]
            or not action["evidence_sha256"]
            or not Path(action["evidence_path"]).is_file()
        ):
            raise RuntimeError("retry requires evidenced confirmed_no_submit")
        if hashlib.sha256(Path(action["evidence_path"]).read_bytes()).hexdigest() != action[
            "evidence_sha256"
        ]:
            raise RuntimeError("retry evidence changed after terminal recording")
        if row["action_type"] in {"publish_listing", "repost_listing"}:
            cooldown_hours = row["cooldown_hours"]
            if not cooldown_hours or cooldown_hours <= 0:
                raise RuntimeError("listing retry is missing persisted campaign cooldown")
            competing = db.execute(
                """SELECT id FROM proposed_actions WHERE id<>? AND source=?
                AND account_alias=? AND campaign_id=? AND action_type IN
                ('publish_listing', 'repost_listing') AND status IN
                ('pending_approval', 'approved', 'executing', 'needs_reconciliation')
                LIMIT 1""",
                (
                    row["id"], row["source"], row["account_alias"], row["campaign_id"]
                ),
            ).fetchone()
            if competing:
                raise RuntimeError(
                    f"another listing proposal already blocks retry: {competing['id']}"
                )
            retry_after = _parse_database_timestamp(
                action["finished_at"], field="actions.finished_at"
            ) + timedelta(hours=cooldown_hours)
            if datetime.now(UTC) < retry_after:
                raise RuntimeError("campaign cooldown blocks listing retry")
        existing_retry = db.execute(
            "SELECT * FROM proposed_actions WHERE retry_of=?", (failed_proposed_action_id,)
        ).fetchone()
        if existing_retry:
            db.rollback()
            return ProposedAction(
                id=existing_retry["id"], source=existing_retry["source"],
                action_type=existing_retry["action_type"],
                payload=json.loads(existing_retry["payload_json"]),
                payload_hash=existing_retry["payload_hash"],
                idempotency_key=existing_retry["idempotency_key"],
                account_alias=existing_retry["account_alias"],
                campaign_id=existing_retry["campaign_id"],
                attempt=existing_retry["attempt"], retry_of=existing_retry["retry_of"],
            )
        attempt = row["attempt"] + 1
        payload = json.loads(row["payload_json"])
        idempotency = make_idempotency_key(
            row["source"], row["account_alias"], row["campaign_id"],
            row["action_type"], payload, attempt,
        )
        db.execute(
            """INSERT INTO proposed_actions
            (id, source, account_alias, campaign_id, action_type, payload_json, payload_hash,
             idempotency_key, status, created_at, updated_at, attempt, retry_of, cooldown_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?, ?, ?, ?)""",
            (
                retry_id, row["source"], row["account_alias"], row["campaign_id"],
                row["action_type"], row["payload_json"], row["payload_hash"], idempotency,
                now, now, attempt, row["id"], row["cooldown_hours"],
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ProposedAction(
        id=retry_id, source=row["source"], action_type=row["action_type"],
        payload=payload, payload_hash=row["payload_hash"], idempotency_key=idempotency,
        account_alias=row["account_alias"], campaign_id=row["campaign_id"],
        attempt=attempt, retry_of=row["id"],
    )


def create_approval(
    db: sqlite3.Connection,
    proposed: ProposedAction,
    *,
    approver: str,
    expires_at: datetime,
    provider: str = "slack",
) -> ApprovalEnvelope:
    created_at = datetime.now(UTC)
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("approval expiry must be timezone-aware")
    expires_at = expires_at.astimezone(UTC)
    if expires_at <= created_at:
        raise ValueError("approval expiry must be in the future")
    if expires_at > created_at + timedelta(minutes=30):
        raise ValueError("approval expiry cannot exceed 30 minutes")
    approval_id = uuid.uuid4().hex
    try:
        db.execute("BEGIN IMMEDIATE")
        authorized = db.execute(
            """SELECT operator_alias FROM authorized_approvers
            WHERE provider=? AND external_user_id=? AND active=1""",
            (provider, approver),
        ).fetchone()
        if authorized is None:
            raise PermissionError("approver is not authorized")
        audit_approver = f"{provider}:{approver}:{authorized['operator_alias']}"
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
            (
                approval_id,
                proposed.id,
                proposed.payload_hash,
                audit_approver,
                iso(created_at),
                iso(expires_at),
            ),
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
        approver=audit_approver,
        expires_at=expires_at,
    )


def get_proposed_action(db: sqlite3.Connection, proposed_action_id: str) -> ProposedAction:
    row = db.execute(
        "SELECT * FROM proposed_actions WHERE id=?", (proposed_action_id,)
    ).fetchone()
    if row is None:
        raise KeyError(proposed_action_id)
    return ProposedAction(
        id=row["id"],
        source=row["source"],
        action_type=row["action_type"],
        payload=json.loads(row["payload_json"]),
        payload_hash=row["payload_hash"],
        idempotency_key=row["idempotency_key"],
        account_alias=row["account_alias"],
        campaign_id=row["campaign_id"],
        attempt=row["attempt"],
        retry_of=row["retry_of"],
    )


def begin_approved_action(
    db: sqlite3.Connection,
    *,
    proposed: ProposedAction,
    current_payload: dict[str, Any],
    approval: ApprovalEnvelope,
    runtime: RuntimeIdentity,
    profile_lock: ProfileLock,
    now: datetime | None = None,
) -> ExecutionReservation:
    """Consume approval and return only the database-owned execution payload."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("execution clock must be timezone-aware")
    now = now.astimezone(UTC)
    profile_lock.assert_owned(runtime.profile_dir)
    action_id = uuid.uuid4().hex
    execution_token = secrets.token_urlsafe(32)
    execution_token_hash = hashlib.sha256(execution_token.encode()).hexdigest()
    try:
        db.execute("BEGIN IMMEDIATE")
        stored_action = db.execute(
            """SELECT source, account_alias, action_type, payload_json, payload_hash,
            idempotency_key
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
        stored_payload_json = canonical_json(json.loads(stored_action["payload_json"]))
        if (
            canonical_json(proposed.payload) != stored_payload_json
            or canonical_json(current_payload) != stored_payload_json
        ):
            raise RuntimeError("executor payload does not match stored approved payload")
        approval_row = db.execute(
            """SELECT proposed_action_id, status, payload_hash, approver, expires_at
            FROM approvals WHERE id=?""",
            (approval.approval_id,),
        ).fetchone()
        if approval_row is None or approval_row["status"] not in {"approved", "consumed"}:
            raise RuntimeError("approval is not available")
        if approval_row["proposed_action_id"] != proposed.id:
            raise RuntimeError("stored approval belongs to a different proposed action")
        if approval_row["payload_hash"] != payload_hash(current_payload):
            raise RuntimeError("stored approval payload hash does not match")
        existing = db.execute(
            """SELECT id, approval_id, status, started_at, payload_json, payload_hash
            FROM actions WHERE idempotency_key=?""",
            (stored_action["idempotency_key"],),
        ).fetchone()
        if existing:
            if existing["approval_id"] != approval.approval_id:
                raise RuntimeError("existing action belongs to a different approval")
            if existing["status"] == "executing":
                policy = db.execute(
                    """SELECT execution_timeout_minutes FROM source_policies
                    WHERE source=? AND account_alias=?""",
                    (stored_action["source"], stored_action["account_alias"]),
                ).fetchone()
                if policy is None:
                    raise RuntimeError("database source policy is missing")
                started_at = _parse_database_timestamp(
                    existing["started_at"], field="actions.started_at"
                )
                timeout = timedelta(minutes=policy["execution_timeout_minutes"])
                if started_at + timeout <= now:
                    db.execute(
                        """UPDATE actions SET status='needs_reconciliation', finished_at=?,
                        execution_token_hash=NULL, error_class='stale_execution',
                        error_detail='execution timeout; verify platform before retry'
                        WHERE id=?""",
                        (iso(now), existing["id"]),
                    )
                    db.execute(
                        """UPDATE proposed_actions SET status='needs_reconciliation',
                        updated_at=? WHERE id=?""",
                        (iso(now), proposed.id),
                    )
                    db.commit()
                    raise RuntimeError("stale execution requires reconciliation")
            db.rollback()
            return ExecutionReservation(
                action_id=existing["id"],
                payload_json=existing["payload_json"],
                payload_hash=existing["payload_hash"],
            )
        if approval_row["status"] != "approved":
            raise RuntimeError("approval is not available for consumption")
        policy = db.execute(
            """SELECT mode, certification_ttl_hours FROM source_policies
            WHERE source=? AND account_alias=?""",
            (stored_action["source"], stored_action["account_alias"]),
        ).fetchone()
        if policy is None:
            raise RuntimeError("database source policy is missing")
        stored_health = db.execute(
            """SELECT status, route, certified_at, runtime_fingerprint, evidence_root
            FROM source_health
            WHERE source=? AND account_alias=?""",
            (stored_action["source"], stored_action["account_alias"]),
        ).fetchone()
        if (
            stored_health is None
            or stored_health["status"] != HealthStatus.HEALTHY.value
            or not stored_health["route"]
            or not stored_health["certified_at"]
            or not stored_health["runtime_fingerprint"]
            or not stored_health["evidence_root"]
        ):
            raise RuntimeError("database source health is not healthy")
        if runtime.fingerprint != stored_health["runtime_fingerprint"]:
            raise RuntimeError("current runtime does not match certified runtime")
        if Path(runtime.evidence_root).resolve() != Path(stored_health["evidence_root"]).resolve():
            raise RuntimeError("current evidence root does not match certification")
        certified_at = _parse_database_timestamp(
            stored_health["certified_at"], field="source_health.certified_at"
        )
        if certified_at > now:
            raise RuntimeError("database source certification is future-dated")
        if certified_at + timedelta(hours=policy["certification_ttl_hours"]) <= now:
            raise RuntimeError("database source certification expired")
        stored_approval = ApprovalEnvelope(
            approval_id=approval.approval_id,
            proposed_action_id=approval_row["proposed_action_id"],
            approved_payload_hash=approval_row["payload_hash"],
            approver=approval_row["approver"],
            expires_at=_parse_database_timestamp(
                approval_row["expires_at"], field="approvals.expires_at"
            ),
        )
        assert_write_allowed(
            mode=OperationMode(policy["mode"]),
            health=HealthStatus(stored_health["status"]),
            proposed_action_id=proposed.id,
            current_payload=current_payload,
            approval=stored_approval,
            now=now,
        )
        db.execute(
            """INSERT INTO actions
            (id, proposed_action_id, approval_id, source, action_type, idempotency_key,
             payload_json, payload_hash, execution_token_hash, status, started_at,
             runtime_fingerprint,
             profile_lock_lease_id, evidence_root)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'executing', ?, ?, ?, ?)""",
            (
                action_id, proposed.id, approval.approval_id, proposed.source,
                proposed.action_type, proposed.idempotency_key, stored_payload_json,
                proposed.payload_hash, execution_token_hash, iso(now),
                runtime.fingerprint, profile_lock.lease_id, runtime.evidence_root,
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
    return ExecutionReservation(
        action_id=action_id,
        payload_json=stored_payload_json,
        payload_hash=stored_action["payload_hash"],
        execution_token=execution_token,
    )


def mark_action_submitting(
    db: sqlite3.Connection,
    reservation: ExecutionReservation,
    *,
    runtime: RuntimeIdentity,
    profile_lock: ProfileLock,
) -> Mapping[str, Any]:
    """Revalidate and return the database-owned payload immediately before submit."""
    if type(reservation) is not ExecutionReservation:
        raise TypeError("execution reservation must use the exact ExecutionReservation type")
    if (
        type(reservation.action_id) is not str
        or type(reservation.payload_json) is not str
        or type(reservation.payload_hash) is not str
        or (
            reservation.execution_token is not None
            and type(reservation.execution_token) is not str
        )
    ):
        raise TypeError("execution reservation fields must use plain built-in types")
    action_id = reservation.action_id
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT status, runtime_fingerprint, profile_lock_lease_id,
            submission_started_at, payload_json, payload_hash, execution_token_hash
            FROM actions WHERE id=?""",
            (action_id,),
        ).fetchone()
        if row is None:
            raise KeyError(action_id)
        if row["status"] != "executing":
            raise RuntimeError(f"action is not executing: {row['status']}")
        profile_lock.assert_owned(
            runtime.profile_dir, lease_id=row["profile_lock_lease_id"]
        )
        if runtime.fingerprint != row["runtime_fingerprint"]:
            raise RuntimeError("action runtime does not match reserved runtime")
        supplied_token_hash = hashlib.sha256(
            (reservation.execution_token or "").encode()
        ).hexdigest()
        if (
            not reservation.should_execute
            or not row["execution_token_hash"]
            or not hmac.compare_digest(supplied_token_hash, row["execution_token_hash"])
        ):
            raise RuntimeError("execution claim is missing or invalid")
        stored_payload = json.loads(row["payload_json"])
        stored_payload_json = canonical_json(stored_payload)
        if (
            row["payload_json"] != stored_payload_json
            or row["payload_hash"] != payload_hash(stored_payload)
            or reservation.payload_json != stored_payload_json
            or reservation.payload_hash != row["payload_hash"]
        ):
            raise RuntimeError("execution reservation payload does not match database snapshot")
        if row["submission_started_at"] is not None:
            raise RuntimeError("action submission was already marked")
        execution_payload = ExecutionReservation(
            action_id=action_id,
            payload_json=stored_payload_json,
            payload_hash=row["payload_hash"],
        ).payload
        db.execute(
            """UPDATE actions SET submission_started_at=?, execution_token_hash=NULL
            WHERE id=?""",
            (iso(), action_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return execution_payload


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
    runtime: RuntimeIdentity,
    profile_lock: ProfileLock,
) -> None:
    if status not in {"succeeded", "failed", "needs_reconciliation"}:
        raise ValueError("invalid terminal action status")
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT a.proposed_action_id, a.source, a.status, a.runtime_fingerprint,
            a.profile_lock_lease_id, a.evidence_root, a.submission_started_at,
            pa.account_alias
            FROM actions AS a JOIN proposed_actions AS pa
            ON pa.id=a.proposed_action_id WHERE a.id=?""",
            (action_id,),
        ).fetchone()
        if row is None:
            raise KeyError(action_id)
        if row["status"] != "executing":
            raise RuntimeError(f"action is not executing: {row['status']}")
        profile_lock.assert_owned(
            runtime.profile_dir, lease_id=row["profile_lock_lease_id"]
        )
        if runtime.fingerprint != row["runtime_fingerprint"]:
            raise RuntimeError("action runtime does not match reserved runtime")
        evidence_root = Path(row["evidence_root"]).resolve()
        if status == "succeeded":
            if row["submission_started_at"] is None:
                raise ValueError("successful action requires durable submission marker")
            if not platform_external_id or not platform_url:
                raise ValueError(
                    "successful action requires evidence, platform ID, and HTTPS platform URL"
                )
            if row["source"] == "craigslist":
                canonicalize_craigslist_url(platform_url)
                url_external_id = craigslist_id_from_url(platform_url)
            elif row["source"] == "facebook_marketplace":
                canonicalize_facebook_url(platform_url)
                url_external_id = facebook_id_from_url(platform_url)
            else:
                raise ValueError(f"no evidence validator for source: {row['source']}")
            if url_external_id != platform_external_id:
                raise ValueError("platform external ID does not match platform URL")
            evidence_sha256 = _validate_action_evidence(
                evidence_path,
                evidence_root=evidence_root,
                expected={
                    "source": row["source"],
                    "account_alias": row["account_alias"],
                    "proposed_action_id": row["proposed_action_id"],
                    "action_id": action_id,
                    "runtime_fingerprint": runtime.fingerprint,
                    "outcome": "succeeded",
                    "platform_external_id": platform_external_id,
                    "platform_url": platform_url,
                },
            )
        elif status == "failed":
            if row["submission_started_at"] is not None:
                raise ValueError("submitted action cannot be recorded as confirmed_no_submit")
            if platform_external_id or platform_url:
                raise ValueError("confirmed_no_submit cannot include platform result identity")
            if error_class != "confirmed_no_submit":
                raise ValueError("failed requires confirmed_no_submit evidence")
            evidence_sha256 = _validate_action_evidence(
                evidence_path,
                evidence_root=evidence_root,
                expected={
                    "source": row["source"],
                    "account_alias": row["account_alias"],
                    "proposed_action_id": row["proposed_action_id"],
                    "action_id": action_id,
                    "runtime_fingerprint": runtime.fingerprint,
                    "outcome": "confirmed_no_submit",
                    "platform_external_id": None,
                    "platform_url": None,
                },
            )
        else:
            if bool(platform_external_id) != bool(platform_url):
                raise ValueError(
                    "reconciliation result identity requires both platform ID and URL"
                )
            if platform_url:
                if row["source"] == "craigslist":
                    canonicalize_craigslist_url(platform_url)
                    url_external_id = craigslist_id_from_url(platform_url)
                elif row["source"] == "facebook_marketplace":
                    canonicalize_facebook_url(platform_url)
                    url_external_id = facebook_id_from_url(platform_url)
                else:
                    raise ValueError(f"no evidence validator for source: {row['source']}")
                if url_external_id != platform_external_id:
                    raise ValueError("platform external ID does not match platform URL")
            if evidence_path:
                evidence_sha256 = _validate_action_evidence(
                    evidence_path,
                    evidence_root=evidence_root,
                    expected={
                        "source": row["source"],
                        "account_alias": row["account_alias"],
                        "proposed_action_id": row["proposed_action_id"],
                        "action_id": action_id,
                        "runtime_fingerprint": runtime.fingerprint,
                        "outcome": "needs_reconciliation",
                        "platform_external_id": platform_external_id,
                        "platform_url": platform_url,
                    },
                )
            else:
                evidence_sha256 = None
            if not error_class:
                error_class = "ambiguous_outcome"
        finished_at = iso()
        db.execute(
            """UPDATE actions SET status=?, platform_external_id=?, platform_url=?,
            evidence_path=?, evidence_sha256=?, finished_at=?, error_class=?,
            error_detail=?, execution_token_hash=NULL WHERE id=?""",
            (
                status, platform_external_id, platform_url, evidence_path, evidence_sha256,
                finished_at, error_class, error_detail, action_id,
            ),
        )
        db.execute(
            "UPDATE proposed_actions SET status=?, updated_at=? WHERE id=?",
            (status, finished_at, row["proposed_action_id"]),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


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
                """SELECT source, account_alias, status, route, checked_at,
                certified_at FROM source_health"""
            ).fetchall()
        ],
    }
