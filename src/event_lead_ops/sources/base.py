from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from ..models import (
    ActionResult,
    CollectionBatch,
    HealthReport,
    ProposedAction,
    ResponseBatch,
    SourceRecord,
)


class SourceAdapter(ABC):
    source: str

    @abstractmethod
    def health(self) -> HealthReport: ...

    @abstractmethod
    def collect(self, cursor: str | None = None) -> CollectionBatch: ...

    @abstractmethod
    def normalize(self, raw: Any) -> SourceRecord: ...

    @abstractmethod
    def prepare_action(self, record_id: str, campaign_id: str) -> ProposedAction: ...

    @abstractmethod
    def execute_approved_action(self, payload: Mapping[str, Any]) -> ActionResult:
        """Submit only the immutable payload returned by mark_action_submitting()."""
        ...

    @abstractmethod
    def poll_responses(self, cursor: str | None = None) -> ResponseBatch: ...
