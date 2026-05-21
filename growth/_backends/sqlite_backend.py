"""SQLite-backed persistence for profiles, children, and measurements.

Used for local development and the test suite. The Postgres equivalent
lives in `postgres_backend.py`; the dispatcher in `growth.store` picks
between them at import time based on whether `DATABASE_URL` is set.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from .. import auth
from ._types import Child, Measurement, Profile, Sex

DB_PATH = Path(__file__).resolve().parent.parent.parent / "growth.db"


# The profiles DDL is kept separately so the legacy-data migration can
# create *just* the profiles table without also trying to create the
# index on children(profile_id) — which would fail if `children` is
# still the pre-profile schema.
PROFILES_DDL = """
CREATE TABLE IF NOT EXISTS profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    passcode_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""

SCHEMA = PROFILES_DDL + """
CREATE TABLE IF NOT EXISTS children (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    sex        TEXT NOT NULL CHECK (sex IN ('boy','girl')),
    dob        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measurements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id     INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    taken_on     TEXT NOT NULL,
    weight_kg    REAL,
    length_cm    REAL,
    head_circ_cm REAL
);
CREATE INDEX IF NOT EXISTS idx_children_profile ON children(profile_id);
CREATE INDEX IF NOT EXISTS idx_measurements_child ON measurements(child_id, taken_on);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- schema bootstrap + migration ----------

LEGACY_PROFILE_NAME = "_legacy"
LEGACY_PROFILE_PASSCODE = "legacy"


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _migrate_legacy_children(conn: sqlite3.Connection) -> None:
    """If a `children` table exists from the pre-profile schema (no
    `profile_id` column), create a single legacy profile and reassign all
    existing rows to it so user-entered data isn't lost when the app
    upgrades."""
    if not _table_exists(conn, "children"):
        return
    cols = _columns(conn, "children")
    if "profile_id" in cols:
        return  # already on the new schema

    conn.executescript(PROFILES_DDL)
    cur = conn.execute(
        "INSERT INTO profiles (name, passcode_hash, created_at) VALUES (?, ?, ?)",
        (LEGACY_PROFILE_NAME, auth.hash_passcode(LEGACY_PROFILE_PASSCODE),
         _utc_now_iso()),
    )
    legacy_id = cur.lastrowid

    conn.execute("ALTER TABLE children ADD COLUMN profile_id INTEGER REFERENCES profiles(id)")
    conn.execute("UPDATE children SET profile_id = ? WHERE profile_id IS NULL", (legacy_id,))


def init_db() -> None:
    with connect() as conn:
        _migrate_legacy_children(conn)
        conn.executescript(SCHEMA)


# ---------- profiles ----------

def create_profile(name: str, passcode: str) -> Profile:
    name = (name or "").strip()
    if not name:
        raise ValueError("Profile name is required.")
    auth.validate_passcode(passcode)
    h = auth.hash_passcode(passcode)
    created = _utc_now_iso()
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO profiles (name, passcode_hash, created_at) VALUES (?, ?, ?)",
                (name, h, created),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"A profile named '{name}' already exists.") from e
        return Profile(id=cur.lastrowid, name=name, created_at=created)


def authenticate(name: str, passcode: str) -> Profile | None:
    name = (name or "").strip()
    if not name or not passcode:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, passcode_hash, created_at FROM profiles WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
    if row is None:
        return None
    pid, pname, phash, created = row
    if not auth.verify_passcode(passcode, phash):
        return None
    return Profile(id=pid, name=pname, created_at=created)


def get_profile(profile_id: int) -> Profile | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, created_at FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    if row is None:
        return None
    return Profile(id=row[0], name=row[1], created_at=row[2])


# ---------- children (always scoped to a profile) ----------

def add_child(profile_id: int, name: str, sex: Sex, dob: date) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO children (profile_id, name, sex, dob) VALUES (?, ?, ?, ?)",
            (profile_id, name, sex, dob.isoformat()),
        )
        return cur.lastrowid


def list_children(profile_id: int) -> list[Child]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, profile_id, name, sex, dob FROM children "
            "WHERE profile_id = ? ORDER BY name",
            (profile_id,),
        ).fetchall()
    return [
        Child(id=r[0], profile_id=r[1], name=r[2], sex=r[3], dob=date.fromisoformat(r[4]))
        for r in rows
    ]


def get_child(child_id: int, profile_id: int) -> Child | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, profile_id, name, sex, dob FROM children "
            "WHERE id = ? AND profile_id = ?",
            (child_id, profile_id),
        ).fetchone()
    if row is None:
        return None
    return Child(id=row[0], profile_id=row[1], name=row[2], sex=row[3],
                 dob=date.fromisoformat(row[4]))


def delete_child(child_id: int, profile_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM children WHERE id = ? AND profile_id = ?",
            (child_id, profile_id),
        )


# ---------- measurements ----------

def add_measurement(
    profile_id: int,
    child_id: int,
    taken_on: date,
    weight_kg: float | None,
    length_cm: float | None,
    head_circ_cm: float | None,
) -> int:
    if get_child(child_id, profile_id) is None:
        raise ValueError("Child not found for this profile.")
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO measurements
               (child_id, taken_on, weight_kg, length_cm, head_circ_cm)
               VALUES (?, ?, ?, ?, ?)""",
            (child_id, taken_on.isoformat(), weight_kg, length_cm, head_circ_cm),
        )
        return cur.lastrowid


def list_measurements(profile_id: int, child_id: int) -> list[Measurement]:
    if get_child(child_id, profile_id) is None:
        return []
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, child_id, taken_on, weight_kg, length_cm, head_circ_cm
               FROM measurements WHERE child_id = ? ORDER BY taken_on""",
            (child_id,),
        ).fetchall()
    return [
        Measurement(
            id=r[0], child_id=r[1], taken_on=date.fromisoformat(r[2]),
            weight_kg=r[3], length_cm=r[4], head_circ_cm=r[5],
        )
        for r in rows
    ]


def delete_measurement(profile_id: int, measurement_id: int) -> None:
    with connect() as conn:
        conn.execute(
            """DELETE FROM measurements
               WHERE id = ?
                 AND child_id IN (SELECT id FROM children WHERE profile_id = ?)""",
            (measurement_id, profile_id),
        )
