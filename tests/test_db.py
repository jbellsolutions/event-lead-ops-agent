from __future__ import annotations

from datetime import UTC, datetime

import pytest

from event_lead_ops.db import record_source_health, upsert_source_record
from event_lead_ops.models import HealthStatus, SourceRecord


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
    assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


def test_healthy_source_requires_route_certification(db):
    with pytest.raises(ValueError, match="route and certification"):
        record_source_health(db, source="craigslist", status=HealthStatus.HEALTHY)


def test_source_upsert_is_idempotent(db):
    assert upsert_source_record(db, record()) == "inserted"
    assert upsert_source_record(db, record()) == "duplicate"
    assert db.execute("SELECT COUNT(*) FROM source_records").fetchone()[0] == 1


def test_source_upsert_detects_update(db):
    assert upsert_source_record(db, record()) == "inserted"
    assert upsert_source_record(db, record("Updated title")) == "updated"
    row = db.execute("SELECT title FROM source_records").fetchone()
    assert row[0] == "Updated title"
