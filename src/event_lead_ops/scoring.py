from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .models import SourceRecord


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: float
    tier: str
    explanation: tuple[dict[str, Any], ...]


def score_record(
    record: SourceRecord,
    config: dict[str, Any],
    now: datetime | None = None,
) -> ScoreResult:
    now = now or datetime.now(UTC)
    weights = config["weights"]
    text = f"{record.title} {record.body}".lower()
    terms = record.metadata.get("positive_keywords", [])
    explicit = any(str(term).lower() in text for term in terms)
    components: list[dict[str, Any]] = []

    def add(name: str, fraction: float) -> None:
        points = float(weights.get(name, 0)) * max(0.0, min(1.0, fraction))
        components.append({"factor": name, "fraction": fraction, "points": points})

    add("explicit_event_intent", 1.0 if explicit else 0.0)
    if record.posted_at:
        age = max(0, (now - record.posted_at.astimezone(UTC)).days)
        maximum = int(config.get("recency_days", {}).get("maximum", 30))
        full = int(config.get("recency_days", {}).get("full_score_through", 3))
        recency = 1.0 if age <= full else max(0.0, 1 - ((age - full) / max(1, maximum - full)))
    else:
        recency = 0.0
    add("recency", recency)
    add("service_area_fit", float(record.metadata.get("service_area_fit", 0.0)))
    add("offer_fit", float(record.metadata.get("offer_fit", 0.0)))
    add("budget_or_price_signal", float(record.metadata.get("budget_signal", 0.0)))
    add("contactability", float(record.metadata.get("contactability", 0.0)))
    add("cross_source_match", float(record.metadata.get("cross_source_match", 0.0)))
    add("urgency", float(record.metadata.get("urgency", 0.0)))
    score = round(sum(x["points"] for x in components), 2)
    thresholds = config["thresholds"]
    if score >= thresholds["hot"]:
        tier = "hot"
    elif score >= thresholds["qualified"]:
        tier = "qualified"
    elif score >= thresholds["review"]:
        tier = "review"
    else:
        tier = "archive"
    return ScoreResult(score=score, tier=tier, explanation=tuple(components))
