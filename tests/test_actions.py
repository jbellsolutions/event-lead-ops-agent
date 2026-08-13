from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from event_lead_ops.db import (
    begin_approved_action,
    create_approval,
    create_proposed_action,
    finish_action,
    record_source_health,
)
from event_lead_ops.models import HealthStatus, OperationMode, ProposedAction

PAYLOAD = {
    "title": "Tampa event package",
    "description": "A synthetic test payload.",
    "price": 500,
    "location": "Tampa, FL",
}


def test_approved_action_executes_exactly_once(db):
    record_source_health(
        db,
        source="craigslist",
        status=HealthStatus.HEALTHY,
        route="direct-vps",
        certified_at=datetime.now(UTC),
    )
    proposed = create_proposed_action(
        db,
        source="craigslist",
        action_type="publish_listing",
        payload=PAYLOAD,
    )
    approval = create_approval(
        db,
        proposed,
        approver="operator",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    action_id, should_execute = begin_approved_action(
        db,
        proposed=proposed,
        current_payload=PAYLOAD,
        approval=approval,
        mode=OperationMode.APPROVED_WRITE,
        health=HealthStatus.HEALTHY,
    )
    assert should_execute is True
    finish_action(db, action_id, status="succeeded", platform_external_id="synthetic-1")

    duplicate_id, should_execute_again = begin_approved_action(
        db,
        proposed=proposed,
        current_payload=PAYLOAD,
        approval=approval,
        mode=OperationMode.APPROVED_WRITE,
        health=HealthStatus.HEALTHY,
    )
    assert duplicate_id == action_id
    assert should_execute_again is False
    assert db.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 1


def test_forged_proposed_action_cannot_be_approved(db):
    proposed = create_proposed_action(
        db,
        source="craigslist",
        action_type="publish_listing",
        payload=PAYLOAD,
    )
    forged = ProposedAction(
        id=proposed.id,
        source=proposed.source,
        action_type=proposed.action_type,
        payload={**PAYLOAD, "price": 1},
        payload_hash="forged",
        idempotency_key=proposed.idempotency_key,
    )
    with pytest.raises(RuntimeError, match="stored payload"):
        create_approval(
            db,
            forged,
            approver="operator",
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )


def test_database_health_cannot_be_forged_by_caller(db):
    proposed = create_proposed_action(
        db,
        source="craigslist",
        action_type="publish_listing",
        payload=PAYLOAD,
    )
    approval = create_approval(
        db,
        proposed,
        approver="operator",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    with pytest.raises(RuntimeError, match="database source health"):
        begin_approved_action(
            db,
            proposed=proposed,
            current_payload=PAYLOAD,
            approval=approval,
            mode=OperationMode.APPROVED_WRITE,
            health=HealthStatus.HEALTHY,
        )
