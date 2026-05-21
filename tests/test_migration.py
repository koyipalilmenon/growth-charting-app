"""Auto-migration from the pre-profile schema.

The 1.0 schema had `children` rows owned directly by the database (no
`profile_id`). When the app upgrades, existing rows must not vanish —
they're reassigned to a single `_legacy` profile so the user can still
sign in and see them. This module verifies that path."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from growth import store


OLD_SCHEMA = """
CREATE TABLE children (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sex  TEXT NOT NULL CHECK (sex IN ('boy','girl')),
    dob  TEXT NOT NULL
);
CREATE TABLE measurements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id     INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    taken_on     TEXT NOT NULL,
    weight_kg    REAL,
    length_cm    REAL,
    head_circ_cm REAL
);
"""


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """A SQLite file containing the pre-profile schema with one child + one
    measurement already in it."""
    db = tmp_path / "legacy_growth.db"
    conn = sqlite3.connect(db)
    conn.executescript(OLD_SCHEMA)
    conn.execute("INSERT INTO children (name, sex, dob) VALUES ('Legacy Lou', 'boy', '2025-01-01')")
    conn.execute(
        "INSERT INTO measurements (child_id, taken_on, weight_kg, length_cm, head_circ_cm)"
        " VALUES (1, '2025-06-01', 7.5, 68.0, 43.0)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(store, "DB_PATH", db)
    return db


class TestLegacyMigration:
    def test_init_db_creates_legacy_profile(self, legacy_db):
        store.init_db()
        # The _legacy profile should now exist and be sign-in-able with the
        # documented default passcode.
        profile = store.authenticate(store.LEGACY_PROFILE_NAME,
                                     store.LEGACY_PROFILE_PASSCODE)
        assert profile is not None
        assert profile.name == store.LEGACY_PROFILE_NAME

    def test_legacy_children_attach_to_legacy_profile(self, legacy_db):
        store.init_db()
        profile = store.authenticate(store.LEGACY_PROFILE_NAME,
                                     store.LEGACY_PROFILE_PASSCODE)
        assert profile is not None
        children = store.list_children(profile.id)
        assert len(children) == 1
        assert children[0].name == "Legacy Lou"
        assert children[0].dob == date(2025, 1, 1)

    def test_legacy_measurements_still_attached(self, legacy_db):
        store.init_db()
        profile = store.authenticate(store.LEGACY_PROFILE_NAME,
                                     store.LEGACY_PROFILE_PASSCODE)
        assert profile is not None
        child = store.list_children(profile.id)[0]
        meas = store.list_measurements(profile.id, child.id)
        assert len(meas) == 1
        assert meas[0].weight_kg == 7.5

    def test_running_init_db_twice_is_safe(self, legacy_db):
        """init_db should be idempotent — re-running shouldn't duplicate the
        legacy profile or re-touch already-migrated rows."""
        store.init_db()
        store.init_db()
        profile = store.authenticate(store.LEGACY_PROFILE_NAME,
                                     store.LEGACY_PROFILE_PASSCODE)
        assert profile is not None
        # Still one legacy child, not two.
        assert len(store.list_children(profile.id)) == 1
