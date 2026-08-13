from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
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
class RuntimeIdentity:
    source: str
    account_alias: str
    route: str
    provider: str
    egress_identity: str
    proxy_identity: str
    profile_dir: str
    browser_major_version: str
    display_mode: str
    viewport: str
    evidence_root: str

    def __post_init__(self) -> None:
        values = self.as_dict()
        if any(not value.strip() for value in values.values()):
            raise ValueError("runtime identity fields must be non-empty")
        for field_name in ("profile_dir", "evidence_root"):
            path = Path(values[field_name])
            if not path.is_absolute():
                raise ValueError("runtime identity paths must be absolute")
            object.__setattr__(self, field_name, str(path.resolve()))

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "account_alias": self.account_alias,
            "route": self.route,
            "provider": self.provider,
            "egress_identity": self.egress_identity,
            "proxy_identity": self.proxy_identity,
            "profile_dir": self.profile_dir,
            "browser_major_version": self.browser_major_version,
            "display_mode": self.display_mode,
            "viewport": self.viewport,
            "evidence_root": self.evidence_root,
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


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
    attempt: int = 1
    retry_of: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovedAction:
    proposed: ProposedAction
    approval_id: str
    approver: str
    expires_at: datetime


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ExecutionReservation:
    action_id: str
    payload_json: str
    payload_hash: str
    execution_token: str | None = field(default=None, repr=False)

    @property
    def should_execute(self) -> bool:
        return self.execution_token is not None

    @property
    def payload(self) -> Mapping[str, Any]:
        decoded = json.loads(self.payload_json)
        if not isinstance(decoded, dict):
            raise ValueError("execution payload must be a JSON object")
        return _freeze_json(decoded)


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


@dataclass(frozen=True, slots=True)
class ResponseBatch:
    source: str
    records: tuple[ResponseRecord, ...]
    cursor: str | None = None
    evidence_paths: tuple[str, ...] = ()


def utc_now() -> datetime:
    return datetime.now(UTC)
