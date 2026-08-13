from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from event_lead_ops.config import (
    canonical_source,
    load_and_validate_config,
    load_yaml,
)


def test_example_configs_parse():
    for path in Path("config").glob("*.example.yaml"):
        assert load_yaml(path)


def test_source_aliases_are_deterministic():
    assert canonical_source("facebook") == "facebook_marketplace"
    assert canonical_source("facebook-marketplace") == "facebook_marketplace"
    assert canonical_source("facebook_marketplace") == "facebook_marketplace"
    assert canonical_source("craigslist") == "craigslist"
    with pytest.raises(ValueError, match="unknown source"):
        canonical_source("social")


def test_platform_config_rejects_external_writes_without_approval(tmp_path):
    config = yaml.safe_load(Path("config/platforms.example.yaml").read_text())
    config["defaults"]["external_writes_require_approval"] = False
    path = tmp_path / "platforms.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="external writes must require approval"):
        load_and_validate_config(path, kind="platforms")


def test_platform_config_rejects_approval_ttl_over_30_minutes(tmp_path):
    config = yaml.safe_load(Path("config/platforms.example.yaml").read_text())
    config["defaults"]["approval_ttl_minutes"] = 31
    path = tmp_path / "platforms.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="cannot exceed 30"):
        load_and_validate_config(path, kind="platforms")


def test_platform_config_rejects_invalid_source_mode(tmp_path):
    config = yaml.safe_load(Path("config/platforms.example.yaml").read_text())
    config["craigslist"]["mode"] = "unattended_write"
    path = tmp_path / "platforms.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="invalid mode"):
        load_and_validate_config(path, kind="platforms")


def test_platform_config_requires_https_allowlisted_base_urls(tmp_path):
    config = yaml.safe_load(Path("config/platforms.example.yaml").read_text())
    config["facebook_marketplace"]["base_url"] = "http://localhost/marketplace"
    path = tmp_path / "platforms.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="base_url"):
        load_and_validate_config(path, kind="platforms")


def test_business_config_requires_unique_offer_ids(tmp_path):
    config = yaml.safe_load(Path("config/business.example.yaml").read_text())
    config["offers"].append(dict(config["offers"][0]))
    path = tmp_path / "business.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="offer IDs must be unique"):
        load_and_validate_config(path, kind="business")


def test_business_config_rejects_invalid_timezone(tmp_path):
    config = yaml.safe_load(Path("config/business.example.yaml").read_text())
    config["business"]["timezone"] = "Not/A_Zone"
    path = tmp_path / "business.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="IANA timezone"):
        load_and_validate_config(path, kind="business")


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("weights", "urgency", True, "non-negative integers"),
        ("thresholds", "hot", 101, "between 0 and 100"),
        ("thresholds", "qualified", True, "between 0 and 100"),
    ],
)
def test_scoring_config_rejects_invalid_numeric_semantics(
    tmp_path, section, key, value, message
):
    config = yaml.safe_load(Path("config/scoring.example.yaml").read_text())
    config[section][key] = value
    path = tmp_path / "scoring.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match=message):
        load_and_validate_config(path, kind="scoring")


def test_scoring_config_requires_descending_thresholds(tmp_path):
    config = yaml.safe_load(Path("config/scoring.example.yaml").read_text())
    config["thresholds"]["qualified"] = 80
    path = tmp_path / "scoring.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="hot >= qualified >= review >= archive_below"):
        load_and_validate_config(path, kind="scoring")


def test_scoring_config_rejects_scale_recency_and_archive_mismatch(tmp_path):
    config = yaml.safe_load(Path("config/scoring.example.yaml").read_text())
    config["weights"]["urgency"] = 200
    path = tmp_path / "scoring.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="sum to 100"):
        load_and_validate_config(path, kind="scoring")

    config = yaml.safe_load(Path("config/scoring.example.yaml").read_text())
    config["recency_days"]["full_score_through"] = 31
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="less than maximum"):
        load_and_validate_config(path, kind="scoring")

    config = yaml.safe_load(Path("config/scoring.example.yaml").read_text())
    config["thresholds"]["archive_below"] = 30
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="must equal review"):
        load_and_validate_config(path, kind="scoring")


def test_schedule_config_rejects_invalid_timezone_and_cron(tmp_path):
    config = yaml.safe_load(Path("config/schedules.example.yaml").read_text())
    config["timezone"] = "Not/A_Zone"
    path = tmp_path / "schedules.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="IANA timezone"):
        load_and_validate_config(path, kind="schedules")

    config = yaml.safe_load(Path("config/schedules.example.yaml").read_text())
    config["jobs"][0]["schedule"] = "not cron"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="five-field cron"):
        load_and_validate_config(path, kind="schedules")


def test_all_example_configs_validate():
    for kind in ("business", "platforms", "scoring", "schedules"):
        config = load_and_validate_config(Path("config") / f"{kind}.example.yaml", kind=kind)
        assert config
