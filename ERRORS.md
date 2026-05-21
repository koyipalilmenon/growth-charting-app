# Error log

Running record of bugs encountered while running the app, what fixed them,
and the regression test added so the same bug can't return.

When you hit an error: paste the traceback / what you did, and I'll add an
entry here, write a test in `tests/` that fails on the bug, and fix the
underlying code.

Format:

> ## YYYY-MM-DD — short title
>
> **What I ran:** …
>
> **Error:**
>
> ```text
> traceback / message
> ```
>
> **Root cause:** …
>
> **Fix:** commit / files changed
>
> **Regression test:** `tests/test_xxx.py::test_yyy`

---

## 2026-05-19 — Windows Store Python stub blocks `python -m venv`

**What I ran:** the setup commands from README (in PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Error:**

```text
Python was not found; run without arguments to install from the Microsoft
Store, or disable this shortcut from Settings > Apps > Advanced app
settings > App execution aliases.
.\.venv\Scripts\Activate.ps1 : The term '.\.venv\Scripts\Activate.ps1' is
not recognized as the name of a cmdlet, function, script file, or operable
program. ...
pip : The term 'pip' is not recognized ...
```

**Root cause:** On a stock Windows 11 box, `C:\Users\<user>\AppData\Local\
Microsoft\WindowsApps\python.exe` is a "Store launcher" stub, not a real
interpreter. Running it silently opens the Store instead of executing
Python, so `python -m venv .venv` exits without creating the `.venv`
directory. The next two commands then fail because the venv never existed
and `pip` isn't on PATH.

**Fix:** Install Python first, then open a *new* PowerShell window (so
PATH refreshes). Added a `setup.ps1` script that detects the stub and
fails loudly with the install instructions, and rewrote the README setup
section to make this prerequisite blindingly obvious.

```powershell
winget install Python.Python.3.12   # one-time
# close this terminal, open a fresh PowerShell
.\setup.ps1                          # creates venv + installs deps
.\run.ps1                            # launches the app
```

**Regression test:** None — this is an environment/setup issue, not a
code bug, so there's nothing to assert against. The mitigation is the
`setup.ps1` doctor check, which short-circuits with a clear error
message instead of producing confusing failures three commands later.

## 2026-05-19 — `setup.ps1` reports "No Python interpreter found" after disabling the Store stub

**What I ran:** disabled the `python.exe` / `python3.exe` entries under
Settings -> Apps -> Advanced app settings -> App execution aliases (so the
Store stub no longer launches), then ran:

```powershell
.\setup.ps1
```

**Error:**

```text
[setup.ps1] ERROR: No Python interpreter found. Install Python 3.10+ and
re-run this script:

    winget install Python.Python.3.12

After installing, close this PowerShell window and open a fresh one before
running setup.ps1 again (PATH only refreshes in new shells).
```

**Root cause:** Disabling the Store aliases removed the launcher stub but
didn't install a real Python interpreter. `setup.ps1` correctly detected
that no `py` launcher and no real `python.exe` were on PATH, and bailed.
The user read this as a new bug rather than as the script's actual
required next step.

**Fix:** Made `setup.ps1` more proactive: if no Python is found *and*
`winget` is available, it now offers to run
`winget install Python.Python.3.12` directly (with a Y/n prompt). After
the install it tells the user to close the shell and reopen it, since
PATH only refreshes in new processes. Pass `-AutoInstall` to skip the
prompt entirely. README rewritten to point at `.\setup.ps1` as the
one-command entry point.

**Regression test:** None — still an environment/setup issue, not a code
bug. The mitigation lives in `setup.ps1`.

## 2026-05-19 — `winget install` exits -1978335189 (agreements not accepted)

**What I ran:**

```powershell
.\setup.ps1   # accepted the Y prompt to install Python via winget
```

**Error:**

```text
[setup.ps1] ERROR: winget install exited with code -1978335189.
Try installing manually from https://www.python.org/downloads/windows/.
```

**Root cause:** `-1978335189` is the signed-decimal form of winget error
`0x8A15002B = APPINSTALLER_CLI_ERROR_PACKAGE_AGREEMENTS_NOT_ACCEPTED`.
Even though `setup.ps1` passed `--accept-package-agreements` and
`--accept-source-agreements`, those flags only apply once the local
winget source manifest is current. On a winget client whose source
cache is stale (or which has never been refreshed), the flags are
rejected before they're applied and the install fails.

**Fix:** Reworked `setup.ps1`'s winget path to:

1. Run `winget source update` first so the source manifest is current
   before any install flags are evaluated.
2. Retry `winget install -e --id Python.Python.3.12` with the
   accept-agreements flags.
3. If winget still fails for any reason, open
   <https://www.python.org/downloads/windows/> in the default browser
   and instruct the user to install manually, then re-run setup in a
   fresh shell.

**Regression test:** None — environment/setup issue. Mitigation in
`setup.ps1`.

## 2026-05-19 — setup.ps1 crashes formatting hex of negative exit code

**What I ran:**

```powershell
.\setup.ps1
```

**Error:**

```text
Found an existing package already installed. Trying to upgrade the
installed package...
No available upgrade found.
No newer package versions are available from the configured sources.

Cannot convert value "-1978335189" to type "System.UInt32". Error: "Value
was either too large or too small for a UInt32."
At C:\Users\...\setup.ps1:80 char:76
+ ... all failed (exit $code, hex 0x$('{0:X}' -f [int][uint32]$code))." -Fo ...
+                                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : InvalidArgument: (:) [], ParentContainsErrorRecordException
    + FullyQualifiedErrorId : InvalidCastIConvertible
```

**Root cause:** Two problems stacked:

1. winget reported "Found an existing package already installed" —
   Python is actually on this machine; winget couldn't upgrade and
   surfaced exit code `-1978335189`. Conceptually the install succeeded
   (or was a no-op), but the script treated any nonzero exit as fatal.
2. The diagnostic line `'{0:X}' -f [int][uint32]$code` tries to cast the
   raw signed int32 `-1978335189` to `uint32` via a direct cast, which
   PowerShell rejects. The correct PowerShell idiom for "show the
   unsigned bit pattern of a signed int32" is `($code -band
   0xFFFFFFFFL)`, which produces an Int64 with the right bits and
   formats cleanly.

**Fix:** [setup.ps1](setup.ps1) updated to:

- Capture winget output and treat the phrases "already installed",
  "No available upgrade found", and "No newer package versions are
  available" as success regardless of the exit code.
- Refresh PATH from the registry **in this process** after a winget
  install/upgrade, then re-run `Find-RealPython`. If Python is now
  visible, the script continues straight into venv creation — no need
  to close and reopen the terminal.
- Use `($code -band 0xFFFFFFFFL)` for hex formatting so the negative
  exit code can no longer crash the script.

**Regression test:** None — these are PowerShell script issues, not
Python code. The pytest suite has no PowerShell counterpart, and adding
Pester just for this would be overkill. The mitigations live in the
script itself.

## 2026-05-20 — Legacy-schema migration crashes on `CREATE INDEX`

**What I ran:**

```powershell
.\test.ps1
```

**Error:**

```text
>       conn.executescript(SCHEMA)
E       sqlite3.OperationalError: no such column: profile_id

growth\store.py:123: OperationalError

FAILED tests/test_migration.py::TestLegacyMigration::test_init_db_creates_legacy_profile
FAILED tests/test_migration.py::TestLegacyMigration::test_legacy_children_attach_to_legacy_profile
FAILED tests/test_migration.py::TestLegacyMigration::test_legacy_measurements_still_attached
FAILED tests/test_migration.py::TestLegacyMigration::test_running_init_db_twice_is_safe
4 failed, 89 passed
```

**Root cause:** The migration helper `_migrate_legacy_children` called
`conn.executescript(SCHEMA)` early to make sure the `profiles` table
existed before it tried to insert a legacy profile. But `SCHEMA` also
contains `CREATE INDEX IF NOT EXISTS idx_children_profile ON
children(profile_id)`. At that point in the migration, `children` is
still the pre-profile table (no `profile_id` column), so the index
creation raises `no such column: profile_id` before the migration's
`ALTER TABLE children ADD COLUMN profile_id` has a chance to run.

This was a sequencing bug, not a data bug — the four existing migration
tests catch it, so once the fix lands they're the regression coverage.

Also surfaced in the same run: a `DeprecationWarning: datetime.utcnow()
is deprecated`. Cleaned that up at the same time by switching to
`datetime.now(timezone.utc)`.

**Fix:** Split `SCHEMA` into `PROFILES_DDL` + the rest. The migration
creates *only* the `profiles` table via `PROFILES_DDL`, then does its
ALTER + backfill. `init_db()` then runs the full `SCHEMA` afterwards,
which is now safe because the `profile_id` column exists by the time
the index is created.

**Regression test:** `tests/test_migration.py::TestLegacyMigration`
(all four cases) — these were already in place and were failing exactly
on this bug; they pass now.
