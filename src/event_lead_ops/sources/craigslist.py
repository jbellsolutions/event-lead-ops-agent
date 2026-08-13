from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..models import SourceRecord

_ID_PATTERN = re.compile(r"/(\d{8,})\.html(?:$|[?#])")
_PRICE_PATTERN = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)")
_HOST_PATTERN = re.compile(r"(^|\.)craigslist\.org$", re.I)


def canonicalize_url(value: str) -> str:
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or not _HOST_PATTERN.search(host):
        raise ValueError("Craigslist URL must use HTTPS on craigslist.org")
    canonical = urlunsplit(("https", parts.netloc.lower(), parts.path, "", ""))
    listing_id_from_url(canonical)
    return canonical


def listing_id_from_url(value: str) -> str:
    match = _ID_PATTERN.search(value)
    if not match:
        raise ValueError("Craigslist URL does not contain a listing ID")
    return match.group(1)


def parse_price_minor(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return round(float(value) * 100)
    match = _PRICE_PATTERN.search(str(value))
    return round(float(match.group(1).replace(",", "")) * 100) if match else None


def normalize_listing(raw: dict[str, Any]) -> SourceRecord:
    url = canonicalize_url(str(raw["url"]))
    url_id = listing_id_from_url(url)
    supplied_id = str(raw.get("id") or url_id)
    if supplied_id != url_id:
        raise ValueError("Craigslist listing ID does not match URL")
    external_id = url_id
    posted_at = raw.get("posted_at")
    if isinstance(posted_at, str):
        posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    return SourceRecord(
        source="craigslist",
        external_id=external_id,
        record_type="listing",
        canonical_url=url,
        title=str(raw.get("title", "")).strip(),
        body=str(raw.get("description", raw.get("body", ""))).strip(),
        location=str(raw.get("location", "")).strip(),
        price_minor=parse_price_minor(raw.get("price")),
        currency="USD" if raw.get("price") not in (None, "") else None,
        posted_at=posted_at,
        metadata={
            "category": raw.get("category"),
            "image_urls": list(raw.get("image_urls", [])),
            "reply_path": raw.get("reply_path"),
        },
        raw_evidence_path=raw.get("evidence_path"),
    )
