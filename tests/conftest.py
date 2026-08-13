from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from event_lead_ops.db import connect, init_db


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "test.sqlite3")
    init_db(connection)
    yield connection
    connection.close()
