from __future__ import annotations

from event_lead_ops.sources.craigslist import normalize_listing as normalize_craigslist
from event_lead_ops.sources.facebook_marketplace import normalize_listing as normalize_facebook


def test_craigslist_normalization():
    record = normalize_craigslist(
        {
            "url": "https://tampa.craigslist.org/evg/d/tampa-event-help/1234567890.html?x=1",
            "title": "Event help wanted",
            "location": "Tampa",
            "price": "$1,250",
            "category": "evg",
        }
    )
    assert record.external_id == "1234567890"
    assert record.canonical_url.endswith("1234567890.html")
    assert record.price_minor == 125000


def test_facebook_normalization():
    record = normalize_facebook(
        {
            "url": "https://m.facebook.com/marketplace/item/987654321/?ref=search",
            "title": "Wedding decor package",
            "location": "Tampa, Florida",
            "price": "US$500",
        }
    )
    assert record.external_id == "987654321"
    assert record.canonical_url == "https://www.facebook.com/marketplace/item/987654321/"
    assert record.price_minor == 50000
