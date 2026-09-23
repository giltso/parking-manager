"""Shared setup for every test.

pytest loads this file automatically. Anything defined here as a "fixture" can
be requested by any test simply by naming it as an argument, which is how a test
gets a fresh database without repeating the setup.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from app import clock
from app.db import connect, migrate


@pytest.fixture
def db(tmp_path) -> sqlite3.Connection:
    """A brand-new database file with every migration applied.

    `tmp_path` is pytest's own fixture: a private empty folder for this one
    test, thrown away afterwards. So each test starts from nothing and cannot
    be affected by another test's leftovers.
    """
    connection = connect(str(tmp_path / "test.db"))
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def frozen_clock():
    """Pin the clock at a fixed moment for the duration of one test.

    Returns the moment, so a test can say "30 minutes after this". Time-based
    rules are otherwise untestable without waiting for real time to pass.
    """
    moment = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    clock.freeze(moment)
    yield moment
    clock.unfreeze()
