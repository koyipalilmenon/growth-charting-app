"""Shared pytest fixtures."""

from __future__ import annotations

import matplotlib

# Force a non-interactive backend so chart tests work in CI / headless shells.
matplotlib.use("Agg")

import pytest

from growth import store


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point the store at a fresh empty SQLite DB inside tmp_path."""
    db_file = tmp_path / "test_growth.db"
    monkeypatch.setattr(store, "DB_PATH", db_file)
    store.init_db()
    yield db_file
