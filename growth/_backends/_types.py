"""Public dataclasses shared by both the SQLite and Postgres backends.

Kept in a separate module so that `growth.store.Profile` is the *same*
class regardless of which backend is loaded — e.g. `isinstance(p, Profile)`
works for objects from either backend, and code that imports types from
`growth.store` doesn't break when the backend switches at deploy time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Sex = Literal["boy", "girl"]


@dataclass
class Profile:
    id: int
    name: str
    created_at: str


@dataclass
class Child:
    id: int
    profile_id: int
    name: str
    sex: Sex
    dob: date


@dataclass
class Measurement:
    id: int
    child_id: int
    taken_on: date
    weight_kg: float | None
    length_cm: float | None
    head_circ_cm: float | None

    def age_days(self, dob: date) -> int:
        return (self.taken_on - dob).days
