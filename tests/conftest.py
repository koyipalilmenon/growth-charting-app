"""Shared pytest fixtures."""

from __future__ import annotations

import matplotlib

# Force a non-interactive backend so chart tests work in CI / headless shells.
matplotlib.use("Agg")

import pytest

from growth._backends import sqlite_backend


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point the SQLite backend at a fresh empty DB inside tmp_path.

    Tests always run against SQLite — patching the backend module directly
    (rather than the `growth.store` dispatcher) keeps the fixture
    independent of whether `DATABASE_URL` happens to be set in the dev
    environment."""
    db_file = tmp_path / "test_growth.db"
    monkeypatch.setattr(sqlite_backend, "DB_PATH", db_file)
    sqlite_backend.init_db()
    yield db_file
