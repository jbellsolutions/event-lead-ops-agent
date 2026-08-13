from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from event_lead_ops.models import HealthStatus, OperationMode
from event_lead_ops.policy import (
    ApprovalEnvelope,
    PolicyViolation,
    assert_write_allowed,
    payload_hash,
)

PAYLOAD = {"title": "Approved event package", "price": 500, "location": "Tampa"}


def approval(expires_delta: timedelta = timedelta(minutes=30)) -> ApprovalEnvelope:
    return ApprovalEnvelope(
        approval_id="approval-1",
        proposed_action_id="action-1",
        approved_payload_hash=payload_hash(PAYLOAD),
        approver="operator",
        expires_at=datetime.now(UTC) + expires_delta,
    )


def test_observe_mode_cannot_write():
    with pytest.raises(PolicyViolation, match="mode"):
        assert_write_allowed(
            mode=OperationMode.OBSERVE,
            health=HealthStatus.HEALTHY,
            proposed_action_id="action-1",
            current_payload=PAYLOAD,
            approval=approval(),
        )


def test_unhealthy_source_cannot_write():
    with pytest.raises(PolicyViolation, match="health"):
        assert_write_allowed(
            mode=OperationMode.APPROVED_WRITE,
            health=HealthStatus.CHALLENGED,
            proposed_action_id="action-1",
            current_payload=PAYLOAD,
            approval=approval(),
        )


def test_payload_edit_invalidates_approval():
    edited = dict(PAYLOAD, price=700)
    with pytest.raises(PolicyViolation, match="changed"):
        assert_write_allowed(
            mode=OperationMode.APPROVED_WRITE,
            health=HealthStatus.HEALTHY,
            proposed_action_id="action-1",
            current_payload=edited,
            approval=approval(),
        )


def test_expired_approval_fails_closed():
    with pytest.raises(PolicyViolation, match="expired"):
        assert_write_allowed(
            mode=OperationMode.APPROVED_WRITE,
            health=HealthStatus.HEALTHY,
            proposed_action_id="action-1",
            current_payload=PAYLOAD,
            approval=approval(timedelta(seconds=-1)),
        )
