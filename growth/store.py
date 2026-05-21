"""Persistence layer for the app.

Picks SQLite or Postgres at import time based on whether `DATABASE_URL`
is set in the environment. SQLite is used for local development and the
test suite; Postgres is used when the app is deployed (e.g. Streamlit
Cloud with a Neon connection string in its secrets).

Public API surface is identical across backends — `app.py` and the test
suite import from this module and don't care which backend is live.
"""

from __future__ import annotations

import os

from ._backends._types import Child, Measurement, Profile, Sex

_USE_POSTGRES = bool(os.environ.get("DATABASE_URL"))

if _USE_POSTGRES:
    from ._backends.postgres_backend import (
        add_child,
        add_measurement,
        authenticate,
        create_profile,
        delete_child,
        delete_measurement,
        get_child,
        get_profile,
        init_db,
        list_children,
        list_measurements,
    )

    # Symbols only the SQLite backend defines — referenced by the migration
    # tests, which only run against SQLite. Exposed as None for backends
    # that don't have them so `from growth import store` never breaks.
    LEGACY_PROFILE_NAME = None
    LEGACY_PROFILE_PASSCODE = None
else:
    from ._backends.sqlite_backend import (
        LEGACY_PROFILE_NAME,
        LEGACY_PROFILE_PASSCODE,
        add_child,
        add_measurement,
        authenticate,
        create_profile,
        delete_child,
        delete_measurement,
        get_child,
        get_profile,
        init_db,
        list_children,
        list_measurements,
    )

__all__ = [
    "Child",
    "Measurement",
    "Profile",
    "Sex",
    "add_child",
    "add_measurement",
    "authenticate",
    "create_profile",
    "delete_child",
    "delete_measurement",
    "get_child",
    "get_profile",
    "init_db",
    "list_children",
    "list_measurements",
    "LEGACY_PROFILE_NAME",
    "LEGACY_PROFILE_PASSCODE",
]
