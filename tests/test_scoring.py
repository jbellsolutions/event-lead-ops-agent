from __future__ import annotations

from datetime import UTC, datetime

from event_lead_ops.models import SourceRecord
from event_lead_ops.scoring import score_record


def test_scoring_is_explainable():
    config = {
        "weights": {
            "explicit_event_intent": 30,
            "recency": 15,
            "service_area_fit": 15,
            "offer_fit": 15,
            "budget_or_price_signal": 10,
            "contactability": 5,
            "cross_source_match": 5,
            "urgency": 5,
        },
        "thresholds": {"hot": 75, "qualified": 55, "review": 35},
        "recency_days": {"maximum": 30, "full_score_through": 3},
    }
    record = SourceRecord(
        source="craigslist",
        external_id="1",
        record_type="listing",
        canonical_url="https://example.test/1",
        title="Wedding event vendor needed this weekend",
        posted_at=datetime(2026, 8, 11, tzinfo=UTC),
        metadata={
            "positive_keywords": ["wedding", "event"],
            "service_area_fit": 1,
            "offer_fit": 1,
            "budget_signal": 0.5,
            "contactability": 1,
            "urgency": 1,
        },
    )
    result = score_record(record, config, now=datetime(2026, 8, 12, tzinfo=UTC))
    assert result.score == 90
    assert result.tier == "hot"
    assert {item["factor"] for item in result.explanation} == set(config["weights"])
