# Growth Charts (WHO 0–24 months)

A Streamlit app to track infant growth and plot measurements against the
WHO Child Growth Standards (0–24 months):

- Length-for-age
- Weight-for-age
- Weight-for-length
- Head circumference-for-age

Each child you add has their own measurement history (date, weight, length,
head circumference). The latest entry is highlighted on every chart with its
z-score and percentile.

## Profiles (per-user data isolation)

The first time you open the app, create a **profile**: pick a name and a
passcode (≥ 6 characters). All children and measurements you add are stored
under that profile — other users of the same deployment can't see them, and
you can't see theirs. The passcode is stored as a PBKDF2-SHA256 hash, not in
plain text.

There is **no email-based recovery**. If you forget your passcode the data
under that profile is unrecoverable.

If you're upgrading from an earlier version of the app, your existing
children/measurements are auto-migrated into a profile named `_legacy` with
the passcode `legacy`. Sign in with those credentials once, then create a
real profile and copy values across by hand if you want to keep them.

## Setup

Python 3.10+ is required. On a stock Windows machine the `python` command on
PATH is a Microsoft Store launcher stub, not a real interpreter — so step 1
below is **mandatory** even if `python --version` "seems to work."

```powershell
# Just run setup.ps1. It will:
#   - detect the Microsoft Store stub and reject it
#   - offer to `winget install Python.Python.3.12` if Python is missing
#   - create .venv and install all deps
.\setup.ps1

# If Python was installed during setup, CLOSE this terminal, open a NEW one,
# and run .\setup.ps1 again. (PATH only refreshes in new shells.)

.\run.ps1       # launches the Streamlit app
.\test.ps1      # runs the pytest suite
```

`setup.ps1` accepts `-AutoInstall` to skip the winget confirmation prompt.

The app opens at <http://localhost:8501>. Data persists in `growth.db` (SQLite)
next to `app.py`; delete it to start over.

### Troubleshooting

If `.\setup.ps1` is blocked with "running scripts is disabled on this
system", allow local scripts for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## How the percentile math works

Each WHO table provides Lambda/Mu/Sigma (LMS) parameters at fine x-axis
resolution (1 day for age, 0.1 cm for length). The app linearly interpolates
L, M, S at the exact x value, then computes:

```text
z = ((X / M) ** L - 1) / (L * S)        # L != 0
z = ln(X / M) / S                       # L == 0
percentile = standard-normal CDF of z
```

Percentile curves drawn on each chart correspond to z = ±1.881 (3rd / 97th),
±1.036 (15th / 85th), and 0 (50th / median).

## Deploying to Streamlit Cloud (with Neon Postgres)

Streamlit Community Cloud's free tier has an ephemeral filesystem, so a
local SQLite file would be wiped on every container restart. The app
ships with a second backend (Postgres via psycopg3) that activates
automatically when the `DATABASE_URL` environment variable is set.
Locally the SQLite backend is used; in the cloud, point `DATABASE_URL`
at a free Neon Postgres database and your profiles + measurements
persist across restarts.

### 1. Create a Neon database

1. Sign up at <https://neon.tech> (GitHub OAuth works).
2. Click **New project**. Region — pick whatever's closest. Postgres
   version — default is fine.
3. After creation, Neon shows a **connection string** that looks like:

   ```text
   postgresql://<user>:<password>@<host>/<db>?sslmode=require
   ```

   Copy the *pooled* one (Neon labels it "Pooled connection") — the
   free tier's autosuspend works better with the pooler.

### 2. Deploy on Streamlit Community Cloud

1. <https://share.streamlit.io> → **Sign in with GitHub** → **New app**.
2. Repository `koyipalilmenon/growth-charting-app`, branch `main`,
   main file path `app.py`.
3. Before clicking **Deploy**, expand **Advanced settings →
   Secrets**, and paste:

   ```toml
   DATABASE_URL = "postgresql://<user>:<password>@<host>/<db>?sslmode=require"
   ```

4. **Deploy.** First build takes 2–3 minutes (pip installs streamlit,
   matplotlib, psycopg).
5. When the app boots it calls `init_db()`, which creates the schema in
   Neon on first run. From then on, every push to `main` triggers an
   automatic redeploy; your data survives because it's in Neon, not
   in the container's filesystem.

### Switching backends

The dispatcher in `growth/store.py` picks a backend at import time:

- **When `DATABASE_URL` is unset** (local dev, tests): SQLite, file
  `growth.db` next to `app.py`, driver `sqlite3` from the stdlib.
- **When `DATABASE_URL` is set** (Streamlit Cloud, Neon, anything else):
  Postgres, driver `psycopg[binary]>=3.1`.

The two implementations live in `growth/_backends/sqlite_backend.py`
and `growth/_backends/postgres_backend.py`. Public function signatures
are identical, so `app.py` and the test suite don't need to know which
one is active. Tests always run against SQLite — they patch
`growth._backends.sqlite_backend.DB_PATH` to point at a tmp file.

## Project layout

```text
app.py                  Streamlit UI (sign-in screen + per-profile charts)
growth/
  lms.py                LMS math (z-score, percentile, inverse)
  data.py               Load WHO LMS tables, interpolate L/M/S at x
  charts.py             Matplotlib chart rendering
  auth.py               PBKDF2 passcode hashing
  store.py              Backend dispatcher (picks SQLite vs Postgres)
  _backends/
    _types.py           Shared Profile/Child/Measurement dataclasses
    sqlite_backend.py   SQLite implementation (local dev, tests)
    postgres_backend.py Postgres implementation (cloud / DATABASE_URL set)
data/who/               WHO LMS reference tables (CSV, extracted from WHO xlsx)
```

## Data provenance

The CSVs in `data/who/` were extracted from the WHO Child Growth Standards
"z-score expanded tables" (xlsx) published at
<https://www.who.int/tools/child-growth-standards/standards>. Only the
Day/Length and L, M, S columns are kept; the per-z-score measurement values
are recomputed by the app on the fly. The tables are limited to the 0–24
month range (0–730 days) for the age-based indicators, and 45–110 cm for
weight-for-length.
