from __future__ import annotations

import json
from pathlib import Path

import pytest

from event_lead_ops.cli import build_parser, main


def test_validate_config_cli(capsys):
    assert main(["validate-config", "platforms", "config/platforms.example.yaml"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["kind"] == "platforms"


def test_health_cli_accepts_facebook_alias(tmp_path: Path, capsys):
    database = tmp_path / "state.sqlite3"
    assert main(["--db", str(database), "init-db"]) == 0
    capsys.readouterr()
    assert main(["--db", str(database), "health", "facebook"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["health"] == []


def test_cli_registers_approver(tmp_path: Path, capsys):
    database = tmp_path / "state.sqlite3"
    assert main(
        [
            "--db",
            str(database),
            "approver",
            "add",
            "--provider",
            "slack",
            "--external-user-id",
            "U_SYNTHETIC_OWNER",
            "--operator-alias",
            "owner",
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"provider": "slack", "registered": True}


def test_cli_has_no_impersonable_approve_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["approve", "proposal-id", "--approver-external-id", "U_IMPERSONATED"]
        )
