from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

SOURCE_ALIASES = {
    "craigslist": "craigslist",
    "facebook": "facebook_marketplace",
    "facebook-marketplace": "facebook_marketplace",
    "facebook_marketplace": "facebook_marketplace",
}
MODES = {"disabled", "observe", "draft", "approved_write", "template_reply"}
EXPECTED_HOSTS = {
    "craigslist": "craigslist.org",
    "facebook_marketplace": "facebook.com",
}
SCORING_WEIGHTS = {
    "explicit_event_intent",
    "recency",
    "service_area_fit",
    "offer_fit",
    "budget_or_price_signal",
    "contactability",
    "cross_source_match",
    "urgency",
}
CRON_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def load_yaml(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a YAML mapping: {path}")
    return value


def canonical_source(value: str) -> str:
    key = value.strip().lower()
    try:
        return SOURCE_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unknown source: {value}") from exc


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _positive_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _validate_business(config: dict[str, Any]) -> None:
    business = _mapping(config.get("business"), "business")
    for field in ("name", "market", "timezone"):
        if not isinstance(business.get(field), str) or not business[field].strip():
            raise ValueError(f"business.{field} is required")
    try:
        ZoneInfo(business["timezone"])
    except ZoneInfoNotFoundError as exc:
        raise ValueError("business.timezone must be a valid IANA timezone") from exc
    offers = config.get("offers")
    if not isinstance(offers, list) or not offers:
        raise ValueError("offers must be a non-empty list")
    ids = []
    for index, offer in enumerate(offers):
        offer = _mapping(offer, f"offers[{index}]")
        offer_id = offer.get("id")
        if not isinstance(offer_id, str) or not offer_id.strip():
            raise ValueError(f"offers[{index}].id is required")
        ids.append(offer_id)
    if len(ids) != len(set(ids)):
        raise ValueError("offer IDs must be unique")


def _validate_base_url(source: str, value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{source}.base_url is required")
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    expected = EXPECTED_HOSTS[source]
    if parts.scheme != "https" or not (host == expected or host.endswith(f".{expected}")):
        raise ValueError(f"{source}.base_url must use HTTPS on {expected}")


def _validate_platforms(config: dict[str, Any]) -> None:
    defaults = _mapping(config.get("defaults"), "defaults")
    if defaults.get("external_writes_require_approval") is not True:
        raise ValueError("external writes must require approval")
    approval_ttl = _positive_integer(
        defaults.get("approval_ttl_minutes"), "defaults.approval_ttl_minutes"
    )
    if approval_ttl > 30:
        raise ValueError("defaults.approval_ttl_minutes cannot exceed 30")
    for source in ("craigslist", "facebook_marketplace"):
        platform = _mapping(config.get(source), source)
        mode = platform.get("mode")
        if mode not in MODES:
            raise ValueError(f"invalid mode for {source}: {mode}")
        _validate_base_url(source, platform.get("base_url"))
        posting = _mapping(platform.get("posting"), f"{source}.posting")
        if posting.get("require_confirmation_artifact") is not True:
            raise ValueError(f"{source} must require a confirmation artifact")
        _positive_integer(
            posting.get("duplicate_cooldown_days"),
            f"{source}.posting.duplicate_cooldown_days",
        )
        account = _mapping(platform.get("account"), f"{source}.account")
        if account.get("posting_enabled") is not False:
            raise ValueError(f"{source}.account.posting_enabled must default false")


def _validate_scoring(config: dict[str, Any]) -> None:
    weights = _mapping(config.get("weights"), "weights")
    thresholds = _mapping(config.get("thresholds"), "thresholds")
    if not weights or not thresholds:
        raise ValueError("weights and thresholds are required")
    if set(weights) != SCORING_WEIGHTS or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in weights.values()
    ):
        raise ValueError(
            "scoring weights must be the exact required set of non-negative integers"
        )
    if sum(weights.values()) != 100:
        raise ValueError("scoring weights must sum to 100")
    required = ("hot", "qualified", "review", "archive_below")
    if set(thresholds) != set(required) or any(
        not isinstance(thresholds[name], int)
        or isinstance(thresholds[name], bool)
        or not 0 <= thresholds[name] <= 100
        for name in required
    ):
        raise ValueError("scoring thresholds must be integers between 0 and 100")
    values = tuple(thresholds[name] for name in required)
    if values != tuple(sorted(values, reverse=True)):
        raise ValueError("thresholds must satisfy hot >= qualified >= review >= archive_below")
    if thresholds["archive_below"] != thresholds["review"]:
        raise ValueError("archive_below must equal review")
    recency = _mapping(config.get("recency_days"), "recency_days")
    maximum = _positive_integer(recency.get("maximum"), "recency_days.maximum")
    full = recency.get("full_score_through")
    if not isinstance(full, int) or isinstance(full, bool) or not 0 <= full < maximum:
        raise ValueError(
            "recency_days.full_score_through must be non-negative and less than maximum"
        )


def _validate_cron(expression: str, name: str) -> None:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(f"{name} must be a five-field cron expression")
    for field, (minimum, maximum) in zip(fields, CRON_RANGES, strict=True):
        for part in field.split(","):
            base, separator, step = part.partition("/")
            if separator and (not step.isdigit() or int(step) <= 0):
                raise ValueError(f"{name} has an invalid cron step")
            if base == "*":
                continue
            bounds = base.split("-")
            if len(bounds) not in {1, 2} or any(not item.isdigit() for item in bounds):
                raise ValueError(f"{name} has an invalid cron field")
            numbers = [int(item) for item in bounds]
            if any(number < minimum or number > maximum for number in numbers):
                raise ValueError(f"{name} cron value is out of range")
            if len(numbers) == 2 and numbers[0] > numbers[1]:
                raise ValueError(f"{name} cron range is reversed")


def _validate_schedules(config: dict[str, Any]) -> None:
    timezone = config.get("timezone")
    if not isinstance(timezone, str):
        raise ValueError("timezone is required")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    jobs = config.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("jobs must be a non-empty list")
    ids: set[str] = set()
    for index, job in enumerate(jobs):
        job = _mapping(job, f"jobs[{index}]")
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id or job_id in ids:
            raise ValueError("schedule job IDs must be unique non-empty strings")
        ids.add(job_id)
        if not isinstance(job.get("schedule"), str) or not job["schedule"]:
            raise ValueError(f"jobs[{index}].schedule is required")
        _validate_cron(job["schedule"], f"jobs[{index}].schedule")
        if job.get("mode") not in {"observe", "draft"}:
            raise ValueError("scheduled jobs may only use observe or draft mode")


def load_and_validate_config(path: str | Path, *, kind: str) -> dict[str, Any]:
    config = load_yaml(path)
    validators = {
        "business": _validate_business,
        "platforms": _validate_platforms,
        "scoring": _validate_scoring,
        "schedules": _validate_schedules,
    }
    try:
        validator = validators[kind]
    except KeyError as exc:
        raise ValueError(f"unknown config kind: {kind}") from exc
    validator(config)
    return config
