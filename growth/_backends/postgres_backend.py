"""Postgres-backed persistence for profiles, children, and measurements.

Used on Streamlit Community Cloud (and anywhere `DATABASE_URL` is set).
Public API mirrors `sqlite_backend.py` so swapping backends requires no
changes in `app.py` or `growth.store`.

`psycopg` (v3) is the driver. The Neon free tier autosuspends after a
few minutes of inactivity; psycopg's default behaviour of opening a
fresh connection per call is fine for this — Neon resumes in ~1s, and
the connection cost is trivial compared with chart rendering.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date
from typing import TYPE_CHECKING, Iterator

from .. import auth
from ._types import Child, Measurement, Profile, Sex

if TYPE_CHECKING:
    from psycopg import Connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    passcode_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Case-insensitive uniqueness on `name` (matches the SQLite COLLATE NOCASE).
CREATE UNIQUE INDEX IF NOT EXISTS profiles_name_lower_unique ON profiles (LOWER(name));

CREATE TABLE IF NOT EXISTS children (
    id         SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    sex        TEXT NOT NULL CHECK (sex IN ('boy','girl')),
    dob        DATE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_children_profile ON children(profile_id);

CREATE TABLE IF NOT EXISTS measurements (
    id           SERIAL PRIMARY KEY,
    child_id     INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    taken_on     DATE NOT NULL,
    weight_kg    REAL,
    length_cm    REAL,
    head_circ_cm REAL
);
CREATE INDEX IF NOT EXISTS idx_measurements_child ON measurements(child_id, taken_on);
"""


@contextmanager
def connect() -> "Iterator[Connection]":
    # Import lazily so that `import growth.store` doesn't require psycopg
    # to be installed when running with the SQLite backend (e.g. tests).
    import psycopg

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set; Postgres backend cannot connect.")
    conn = psycopg.connect(dsn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)


# ---------- profiles ----------

def create_profile(name: str, passcode: str) -> Profile:
    import psycopg
    name = (name or "").strip()
    if not name:
        raise ValueError("Profile name is required.")
    auth.validate_passcode(passcode)
    h = auth.hash_passcode(passcode)
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO profiles (name, passcode_hash) VALUES (%s, %s) "
                    "RETURNING id, created_at::text",
                    (name, h),
                )
            except psycopg.errors.UniqueViolation as e:
                raise ValueError(f"A profile named '{name}' already exists.") from e
            new_id, created = cur.fetchone()
    return Profile(id=new_id, name=name, created_at=created)


def authenticate(name: str, passcode: str) -> Profile | None:
    name = (name or "").strip()
    if not name or not passcode:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, passcode_hash, created_at::text "
                "FROM profiles WHERE LOWER(name) = LOWER(%s)",
                (name,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    pid, pname, phash, created = row
    if not auth.verify_passcode(passcode, phash):
        return None
    return Profile(id=pid, name=pname, created_at=created)


def get_profile(profile_id: int) -> Profile | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, created_at::text FROM profiles WHERE id = %s",
                (profile_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return Profile(id=row[0], name=row[1], created_at=row[2])


# ---------- children ----------

def add_child(profile_id: int, name: str, sex: Sex, dob: date) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO children (profile_id, name, sex, dob) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (profile_id, name, sex, dob),
            )
            return cur.fetchone()[0]


def list_children(profile_id: int) -> list[Child]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, profile_id, name, sex, dob FROM children "
                "WHERE profile_id = %s ORDER BY name",
                (profile_id,),
            )
            rows = cur.fetchall()
    return [
        Child(id=r[0], profile_id=r[1], name=r[2], sex=r[3], dob=r[4])
        for r in rows
    ]


def get_child(child_id: int, profile_id: int) -> Child | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, profile_id, name, sex, dob FROM children "
                "WHERE id = %s AND profile_id = %s",
                (child_id, profile_id),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return Child(id=row[0], profile_id=row[1], name=row[2], sex=row[3], dob=row[4])


def delete_child(child_id: int, profile_id: int) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM children WHERE id = %s AND profile_id = %s",
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
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO measurements
                   (child_id, taken_on, weight_kg, length_cm, head_circ_cm)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (child_id, taken_on, weight_kg, length_cm, head_circ_cm),
            )
            return cur.fetchone()[0]


def list_measurements(profile_id: int, child_id: int) -> list[Measurement]:
    if get_child(child_id, profile_id) is None:
        return []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, child_id, taken_on, weight_kg, length_cm, head_circ_cm
                   FROM measurements WHERE child_id = %s ORDER BY taken_on""",
                (child_id,),
            )
            rows = cur.fetchall()
    return [
        Measurement(
            id=r[0], child_id=r[1], taken_on=r[2],
            weight_kg=r[3], length_cm=r[4], head_circ_cm=r[5],
        )
        for r in rows
    ]


def delete_measurement(profile_id: int, measurement_id: int) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM measurements
                   WHERE id = %s
                     AND child_id IN (SELECT id FROM children WHERE profile_id = %s)""",
                (measurement_id, profile_id),
            )
