from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from ..models import (
    ActionResult,
    ApprovedAction,
    CollectionBatch,
    HealthReport,
    ResponseRecord,
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
    def prepare_action(self, record_id: str, campaign_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def execute_approved_action(self, action: ApprovedAction) -> ActionResult: ...

    @abstractmethod
    def poll_responses(self, cursor: str | None = None) -> Iterable[ResponseRecord]: ...
