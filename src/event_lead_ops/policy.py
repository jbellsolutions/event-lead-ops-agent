from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .models import HealthStatus, OperationMode


class PolicyViolation(RuntimeError):
    """Raised when a fail-closed policy blocks an action."""


BLOCKING_HEALTH = {
    HealthStatus.UNVERIFIED,
    HealthStatus.CHALLENGED,
    HealthStatus.BLOCKED_AUTH,
    HealthStatus.RATE_LIMITED,
    HealthStatus.PAUSED,
    HealthStatus.WAITING_FOR_REAUTH,
    HealthStatus.ERROR,
}


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def make_idempotency_key(
    source: str,
    account_alias: str,
    action_type: str,
    payload: dict[str, Any],
) -> str:
    material = "\n".join((source, account_alias, action_type, payload_hash(payload)))
    return hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalEnvelope:
    approval_id: str
    proposed_action_id: str
    approved_payload_hash: str
    approver: str
    expires_at: datetime
    status: str = "approved"


def assert_read_allowed(mode: OperationMode, health: HealthStatus) -> None:
    if mode not in {OperationMode.OBSERVE, OperationMode.DRAFT, OperationMode.APPROVED_WRITE}:
        raise PolicyViolation(f"read blocked in mode={mode}")
    if health in BLOCKING_HEALTH:
        raise PolicyViolation(f"source health blocks read: {health}")


def assert_write_allowed(
    *,
    mode: OperationMode,
    health: HealthStatus,
    proposed_action_id: str,
    current_payload: dict[str, Any],
    approval: ApprovalEnvelope,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    if mode is not OperationMode.APPROVED_WRITE:
        raise PolicyViolation(f"external write blocked in mode={mode}")
    if health is not HealthStatus.HEALTHY:
        raise PolicyViolation(f"external write blocked by source health={health}")
    if approval.status != "approved":
        raise PolicyViolation(f"approval status is {approval.status}")
    if approval.proposed_action_id != proposed_action_id:
        raise PolicyViolation("approval belongs to a different proposed action")
    if approval.expires_at <= now:
        raise PolicyViolation("approval expired")
    if approval.approved_payload_hash != payload_hash(current_payload):
        raise PolicyViolation("payload changed after approval")
