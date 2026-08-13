from __future__ import annotations

import hashlib
import sqlite3
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from event_lead_ops.db import record_source_health, upsert_source_record
from event_lead_ops.models import HealthStatus, SourceRecord

PUBLIC_001_SHA256 = "e255c2a8fc6bd30aa06dc6c0c81b707b7c83e6abad2d5de916a20820e9da958f"


def record(title: str = "Wedding event help needed") -> SourceRecord:
    return SourceRecord(
        source="craigslist",
        external_id="1234567890",
        record_type="listing",
        canonical_url="https://tampa.craigslist.org/evg/d/tampa-test/1234567890.html",
        title=title,
        location="Tampa",
        posted_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


def test_migration_creates_expected_tables(db):
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"source_records", "proposed_actions", "approvals", "actions", "job_runs"} <= names


def test_migrations_are_recorded_once(db):
    from event_lead_ops.db import init_db

    init_db(db)
    assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 4


def test_public_001_migration_is_immutable():
    from event_lead_ops.db import MIGRATIONS_DIR

    contents = (Path(MIGRATIONS_DIR) / "001_initial.sql").read_bytes()
    assert hashlib.sha256(contents).hexdigest() == PUBLIC_001_SHA256


def test_public_001_database_upgrades_through_current_migrations(tmp_path):
    from event_lead_ops.db import MIGRATIONS_DIR, connect, init_db

    parent = tmp_path / "upgrade"
    parent.mkdir(mode=0o700)
    path = parent / "state.sqlite3"
    baseline = sqlite3.connect(path)
    baseline.executescript((Path(MIGRATIONS_DIR) / "001_initial.sql").read_text())
    baseline.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        ("001_initial", "2026-08-13T00:00:00+00:00"),
    )
    baseline.commit()
    baseline.close()
    path.chmod(0o600)

    upgraded = connect(path)
    init_db(upgraded)
    versions = [
        row[0]
        for row in upgraded.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ]
    action_columns = {
        row[1] for row in upgraded.execute("PRAGMA table_info(actions)")
    }
    assert versions == [
        "001_initial",
        "002_runtime_policy_and_retries",
        "003_runtime_binding_and_cooldowns",
        "004_immutable_action_payload",
    ]
    assert {
        "runtime_fingerprint",
        "profile_lock_lease_id",
        "evidence_sha256",
        "submission_started_at",
        "payload_json",
        "execution_token_hash",
    } <= action_columns


def test_action_payload_snapshot_and_capability_are_database_constrained(db):
    triggers = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='actions'"
        )
    }
    assert {
        "actions_payload_required_on_insert",
        "actions_authorization_identity_required",
        "actions_payload_immutable",
        "actions_execution_token_replacement_blocked",
        "actions_reservation_identity_immutable",
        "actions_submission_marker_monotonic",
        "actions_terminal_requires_consumed_capability",
        "actions_terminal_cannot_reopen_execution",
    } <= triggers

    proposal_triggers = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='proposed_actions'"
        )
    }
    approval_triggers = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='approvals'"
        )
    }
    assert "proposed_actions_identity_immutable" in proposal_triggers
    assert "approvals_identity_immutable" in approval_triggers

    with pytest.raises(sqlite3.IntegrityError, match="payload JSON and execution capability"):
        db.execute(
            """INSERT INTO actions
            (id, proposed_action_id, approval_id, source, action_type, idempotency_key,
             payload_json, payload_hash, status, started_at)
            VALUES ('a', 'missing', 'missing', 'craigslist', 'publish_listing', 'key',
                    '{}', 'hash', 'executing', '2026-08-13T00:00:00+00:00')"""
        )

    db.execute(
        """INSERT INTO proposed_actions
        (id, source, account_alias, action_type, payload_json, payload_hash,
         idempotency_key, status, created_at, updated_at)
        VALUES ('proposal', 'craigslist', 'default', 'publish_listing',
                '{"price":500}', 'approved-hash', 'proposal-key', 'approved',
                '2026-08-13T00:00:00+00:00', '2026-08-13T00:00:00+00:00')"""
    )
    db.execute(
        """INSERT INTO approvals
        (id, proposed_action_id, payload_hash, approver, status, created_at, expires_at)
        VALUES ('approval', 'proposal', 'approved-hash', 'U_SYNTHETIC', 'approved',
                '2026-08-13T00:00:00+00:00', '2026-08-13T00:30:00+00:00')"""
    )
    with pytest.raises(
        sqlite3.IntegrityError, match="valid payload JSON and execution capability"
    ):
        db.execute(
            """INSERT INTO actions
            (id, proposed_action_id, approval_id, source, action_type, idempotency_key,
             payload_json, payload_hash, execution_token_hash, status, started_at,
             runtime_fingerprint, profile_lock_lease_id, evidence_root)
            VALUES ('terminal-insert', 'proposal', 'approval', 'craigslist',
                    'publish_listing', 'proposal-key', '{"price":500}', 'approved-hash',
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'failed', '2026-08-13T00:00:00+00:00', 'runtime', 'lease', '/evidence')"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="proposal identity is immutable"):
        db.execute(
            "UPDATE proposed_actions SET payload_json='{}' WHERE id='proposal'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="approval identity is immutable"):
        db.execute("UPDATE approvals SET approver='forged' WHERE id='approval'")
    with pytest.raises(sqlite3.IntegrityError, match="stored proposal"):
        db.execute(
            """INSERT INTO actions
            (id, proposed_action_id, approval_id, source, action_type, idempotency_key,
             payload_json, payload_hash, execution_token_hash, status, started_at)
            VALUES ('mismatch', 'proposal', 'approval', 'craigslist',
                    'publish_listing', 'action-key', '{"price":1}', 'approved-hash',
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'executing', '2026-08-13T00:00:00+00:00')"""
        )

    db.execute(
        """INSERT INTO actions
        (id, proposed_action_id, approval_id, source, action_type, idempotency_key,
         payload_json, payload_hash, execution_token_hash, status, started_at,
         runtime_fingerprint, profile_lock_lease_id, evidence_root)
        VALUES ('valid', 'proposal', 'approval', 'craigslist', 'publish_listing',
                'proposal-key', '{"price":500}', 'approved-hash',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'executing', '2026-08-13T00:00:00+00:00', 'runtime', 'lease', '/evidence')"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="reservation identity is immutable"):
        db.execute("UPDATE actions SET runtime_fingerprint='forged' WHERE id='valid'")
    with pytest.raises(sqlite3.IntegrityError, match="consumed execution capability"):
        db.execute("UPDATE actions SET status='failed' WHERE id='valid'")
    db.execute(
        """UPDATE actions
        SET submission_started_at='2026-08-13T00:01:00+00:00',
            execution_token_hash=NULL
        WHERE id='valid'"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="submission marker"):
        db.execute(
            """UPDATE actions
            SET submission_started_at='2026-08-13T00:02:00+00:00'
            WHERE id='valid'"""
        )
    db.execute("UPDATE actions SET status='succeeded' WHERE id='valid'")
    with pytest.raises(sqlite3.IntegrityError, match="cannot reopen execution"):
        db.execute("UPDATE actions SET status='executing' WHERE id='valid'")


def test_public_003_database_backfills_action_payload_snapshot(tmp_path):
    from event_lead_ops.db import MIGRATIONS_DIR, connect, init_db

    parent = tmp_path / "upgrade-003"
    parent.mkdir(mode=0o700)
    path = parent / "state.sqlite3"
    baseline = sqlite3.connect(path)
    for name in (
        "001_initial.sql",
        "002_runtime_policy_and_retries.sql",
        "003_runtime_binding_and_cooldowns.sql",
    ):
        baseline.executescript((Path(MIGRATIONS_DIR) / name).read_text())
        baseline.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (Path(name).stem, "2026-08-13T00:00:00+00:00"),
        )
    payload_json = '{"price":500,"title":"Synthetic"}'
    baseline.execute(
        """INSERT INTO proposed_actions
        (id, source, account_alias, action_type, payload_json, payload_hash,
         idempotency_key, status, created_at, updated_at)
        VALUES ('p', 'craigslist', 'default', 'publish_listing', ?, 'hash', 'proposal-key',
                'executing', '2026-08-13T00:00:00+00:00', '2026-08-13T00:00:00+00:00')""",
        (payload_json,),
    )
    baseline.execute(
        """INSERT INTO proposed_actions
        (id, source, account_alias, action_type, payload_json, payload_hash,
         idempotency_key, status, created_at, updated_at)
        VALUES ('orphan', 'craigslist', 'default', 'publish_listing', ?, 'hash',
                'orphan-key', 'executing', '2026-08-13T00:00:00+00:00',
                '2026-08-13T00:00:00+00:00')""",
        (payload_json,),
    )
    baseline.execute(
        """INSERT INTO approvals
        (id, proposed_action_id, payload_hash, approver, status, created_at, expires_at)
        VALUES ('approval', 'p', 'hash', 'U_SYNTHETIC', 'consumed',
                '2026-08-13T00:00:00+00:00', '2026-08-13T00:30:00+00:00')"""
    )
    baseline.execute(
        """INSERT INTO actions
        (id, proposed_action_id, approval_id, source, action_type, idempotency_key,
         payload_hash, status, started_at)
        VALUES ('action', 'p', 'approval', 'craigslist', 'publish_listing', 'action-key',
                'hash', 'executing', '2026-08-13T00:00:00+00:00')"""
    )
    baseline.commit()
    baseline.close()
    path.chmod(0o600)

    upgraded = connect(path)
    init_db(upgraded)
    row = upgraded.execute(
        """SELECT payload_json, execution_token_hash, status, error_class
        FROM actions WHERE id='action'"""
    ).fetchone()
    assert row["payload_json"] == payload_json
    assert row["execution_token_hash"] is None
    assert row["status"] == "needs_reconciliation"
    assert row["error_class"] == "migration_interrupted_execution"
    assert upgraded.execute(
        "SELECT status FROM proposed_actions WHERE id='p'"
    ).fetchone()[0] == "needs_reconciliation"
    assert upgraded.execute(
        "SELECT status FROM proposed_actions WHERE id='orphan'"
    ).fetchone()[0] == "needs_reconciliation"
    assert upgraded.execute(
        "SELECT COUNT(*) FROM proposed_actions WHERE status='executing'"
    ).fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        upgraded.execute("UPDATE actions SET payload_json='{}' WHERE id='action'")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        upgraded.execute("UPDATE actions SET payload_hash='changed' WHERE id='action'")
    upgraded.execute(
        "UPDATE actions SET execution_token_hash=NULL WHERE id='action'"
    )
    with pytest.raises(sqlite3.IntegrityError, match="only be consumed"):
        upgraded.execute(
            "UPDATE actions SET execution_token_hash='restored' WHERE id='action'"
        )


def test_healthy_source_requires_route_certification(db):
    with pytest.raises(ValueError, match="route, certification time, runtime, and profile lock"):
        record_source_health(db, source="craigslist", status=HealthStatus.HEALTHY)


def test_database_file_is_private(tmp_path):
    from event_lead_ops.db import connect

    path = tmp_path / "private" / "state.sqlite3"
    connection = connect(path)
    connection.close()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_database_refuses_shared_existing_parent_without_chmod(tmp_path):
    from event_lead_ops.db import connect

    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    with pytest.raises(PermissionError, match="owner-only"):
        connect(shared / "state.sqlite3")
    assert stat.S_IMODE(shared.stat().st_mode) == 0o755


def test_empty_migration_directory_fails_closed(tmp_path, db):
    from event_lead_ops.db import init_db

    with pytest.raises(RuntimeError, match="no database migrations"):
        init_db(db, tmp_path / "empty")


def test_concurrent_initializers_serialize_each_migration(tmp_path):
    from event_lead_ops.db import connect

    parent = tmp_path / "concurrent"
    parent.mkdir(mode=0o700)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_race.sql").write_text(
        "CREATE TABLE race (id INTEGER PRIMARY KEY);"
    )
    path = parent / "state.sqlite3"

    script = tmp_path / "initialize.py"
    script.write_text(
        "from event_lead_ops.db import connect, init_db\n"
        "import sys\n"
        "db = connect(sys.argv[1])\n"
        "init_db(db, sys.argv[2])\n"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, str(script), str(path), str(migrations)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)

    db = connect(path)
    assert db.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE version='001_race'"
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='race'"
    ).fetchone()[0] == 1


def test_source_upsert_is_idempotent(db):
    assert upsert_source_record(db, record()) == "inserted"
    assert upsert_source_record(db, record()) == "duplicate"
    assert db.execute("SELECT COUNT(*) FROM source_records").fetchone()[0] == 1


def test_source_upsert_detects_update(db):
    assert upsert_source_record(db, record()) == "inserted"
    assert upsert_source_record(db, record("Updated title")) == "updated"
    row = db.execute("SELECT title FROM source_records").fetchone()
    assert row[0] == "Updated title"
