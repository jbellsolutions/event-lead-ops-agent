from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/1234567890.html",
        "https://localhost/evg/d/test/1234567890.html",
        "https://craigslist.org.evil.example/evg/d/test/1234567890.html",
    ],
)
def test_craigslist_rejects_untrusted_urls(url):
    with pytest.raises(ValueError):
        normalize_craigslist({"url": url, "id": "1234567890"})


@pytest.mark.parametrize(
    "url",
    [
        "https://facebook.com/settings/",
        "https://evil.example/marketplace/item/987654321/",
        "https://facebook.com/marketplace/create/",
    ],
)
def test_facebook_rejects_non_item_urls(url):
    with pytest.raises(ValueError):
        normalize_facebook({"url": url, "id": "987654321"})


def test_supplied_ids_must_match_urls():
    with pytest.raises(ValueError, match="does not match"):
        normalize_craigslist(
            {
                "url": "https://tampa.craigslist.org/evg/d/test/1234567890.html",
                "id": "9999999999",
            }
        )
    with pytest.raises(ValueError, match="does not match"):
        normalize_facebook(
            {
                "url": "https://facebook.com/marketplace/item/987654321/",
                "id": "123456789",
            }
        )
