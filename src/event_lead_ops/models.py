from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class OperationMode(StrEnum):
    DISABLED = "disabled"
    OBSERVE = "observe"
    DRAFT = "draft"
    APPROVED_WRITE = "approved_write"
    TEMPLATE_REPLY = "template_reply"


class HealthStatus(StrEnum):
    UNVERIFIED = "unverified"
    HEALTHY = "healthy"
    CHALLENGED = "challenged"
    BLOCKED_AUTH = "blocked_auth"
    RATE_LIMITED = "rate_limited"
    PAUSED = "paused"
    WAITING_FOR_REAUTH = "waiting_for_reauth"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source: str
    external_id: str
    record_type: str
    canonical_url: str
    title: str = ""
    body: str = ""
    location: str = ""
    price_minor: int | None = None
    currency: str | None = None
    posted_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_evidence_path: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    source: str
    status: HealthStatus
    checked_at: datetime
    account_alias: str = "default"
    route: str | None = None
    detail: str | None = None
    evidence_path: str | None = None


@dataclass(frozen=True, slots=True)
class CollectionBatch:
    source: str
    records: tuple[SourceRecord, ...]
    cursor: str | None = None
    evidence_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProposedAction:
    id: str
    source: str
    action_type: str
    payload: dict[str, Any]
    payload_hash: str
    idempotency_key: str
    account_alias: str = "default"
    campaign_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovedAction:
    proposed: ProposedAction
    approval_id: str
    approver: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ActionResult:
    status: str
    platform_external_id: str | None = None
    platform_url: str | None = None
    evidence_path: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    source: str
    external_thread_id: str
    external_message_id: str
    body_redacted: str
    received_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(UTC)
