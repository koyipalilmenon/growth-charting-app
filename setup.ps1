# One-shot setup: verify a real Python interpreter, create .venv, install deps.
# Re-runnable: if .venv already exists, just installs/updates deps.
#
# Usage:
#   .\setup.ps1               # prompts before running winget if Python is missing
#   .\setup.ps1 -AutoInstall  # installs Python via winget without prompting

param(
    [switch]$AutoInstall
)

$ErrorActionPreference = "Stop"

function Fail($msg) {
    Write-Host ""
    Write-Host "[setup.ps1] ERROR: $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Find-RealPython {
    # Returns @{ Exe = <path-or-name>; Args = @(...) } if a real interpreter is
    # found, otherwise $null. Rejects the Microsoft Store launcher stub.
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = "py"; Args = @("-3") }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    if ($cmd.Source -like "*\WindowsApps\python.exe") {
        # The Store launcher stub. Treat as "not found."
        return $null
    }
    $verOutput = & $cmd.Source --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $verOutput -notmatch "^Python\s+\d") {
        return $null
    }
    return @{ Exe = $cmd.Source; Args = @() }
}

function Open-PythonDownloadsAndExit {
    $url = "https://www.python.org/downloads/windows/"
    Write-Host ""
    Write-Host "[setup.ps1] Opening $url in your default browser ..." -ForegroundColor Yellow
    try { Start-Process $url } catch { }
    Write-Host ""
    Write-Host "Install Python 3.10+ from python.org (any recent 3.10/3.11/3.12/3.13 is fine)." -ForegroundColor Yellow
    Write-Host "On the installer's first screen, tick 'Add python.exe to PATH'." -ForegroundColor Yellow
    Write-Host "Once it finishes, CLOSE this PowerShell window, open a NEW one," -ForegroundColor Yellow
    Write-Host "and re-run:  .\setup.ps1" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

function Refresh-PathFromRegistry {
    # Pull the current Machine + User PATH from the registry into this
    # process. winget installs Python under one of these, but spawned
    # shells don't pick up PATH changes until they restart -- doing this
    # explicitly avoids forcing the user to close and reopen PowerShell.
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = ($machinePath, $userPath | Where-Object { $_ }) -join ";"
}

function Format-WingetExitCode($code) {
    # PowerShell can't cast a signed int32 like -1978335189 to uint32
    # directly. Mask with 0xFFFFFFFFL to get the unsigned bit pattern as
    # an Int64, then format as hex. Returns "-1978335189 (0x8A15002B)".
    $unsigned = [int64]$code -band 0xFFFFFFFFL
    return "$code (0x$('{0:X8}' -f $unsigned))"
}

function Install-PythonViaWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "[setup.ps1] winget is not available on this system." -ForegroundColor Yellow
        Open-PythonDownloadsAndExit
    }

    # Step 1: refresh the winget source manifest. On older / fresh winget
    # installs, --accept-*-agreements flags don't take effect until the
    # source is current; this is a common cause of error 0x8A15002B.
    Write-Host "[setup.ps1] Refreshing winget source ..." -ForegroundColor Cyan
    & winget source update 2>&1 | Out-Null

    # Step 2: install. Capture output so we can recognize the
    # already-installed cases winget reports with a nonzero exit code.
    Write-Host "[setup.ps1] Running: winget install -e --id Python.Python.3.12" -ForegroundColor Cyan
    $wingetOutput = & winget install -e --id Python.Python.3.12 `
        --source winget `
        --accept-source-agreements `
        --accept-package-agreements `
        --silent 2>&1 | Out-String
    $code = $LASTEXITCODE
    Write-Host $wingetOutput

    $alreadyInstalled =
        $wingetOutput -match "already installed" -or
        $wingetOutput -match "No available upgrade found" -or
        $wingetOutput -match "No newer package versions are available"

    if ($code -ne 0 -and -not $alreadyInstalled) {
        Write-Host ""
        Write-Host "[setup.ps1] winget install failed (exit $(Format-WingetExitCode $code))." -ForegroundColor Red
        if ($code -eq -1978335189) {
            Write-Host "[setup.ps1] That code can mean 'agreements not accepted' OR 'no upgrade" -ForegroundColor Red
            Write-Host "[setup.ps1] applicable'. Since the output didn't say 'already installed'," -ForegroundColor Red
            Write-Host "[setup.ps1] falling back to the python.org installer." -ForegroundColor Red
        } else {
            Write-Host "[setup.ps1] Falling back to the python.org installer." -ForegroundColor Red
        }
        Open-PythonDownloadsAndExit
    }

    if ($alreadyInstalled) {
        Write-Host "[setup.ps1] winget reports Python is already installed." -ForegroundColor Cyan
    } else {
        Write-Host "[setup.ps1] Python installed." -ForegroundColor Green
    }

    # Step 3: refresh PATH and look again. If Python is now visible we can
    # continue in this same shell.
    Refresh-PathFromRegistry
    $rediscovered = Find-RealPython
    if ($rediscovered) {
        Write-Host "[setup.ps1] Python found on PATH after refresh: $($rediscovered.Exe)" -ForegroundColor Green
        return $rediscovered
    }

    Write-Host ""
    Write-Host "[setup.ps1] Python is installed but isn't visible to this shell yet." -ForegroundColor Yellow
    Write-Host "[setup.ps1] CLOSE this PowerShell window, open a NEW one, then re-run:" -ForegroundColor Yellow
    Write-Host "              .\setup.ps1" -ForegroundColor Yellow
    exit 0
}

# --- locate Python, offering to install if missing ----------------------------

$python = Find-RealPython
if (-not $python) {
    Write-Host "[setup.ps1] No real Python interpreter found on PATH." -ForegroundColor Yellow

    $doInstall = $AutoInstall
    if (-not $doInstall) {
        $response = Read-Host "Install Python 3.12 now via winget? [Y/n]"
        if ($response -eq "" -or $response -match "^[Yy]") {
            $doInstall = $true
        }
    }

    if ($doInstall) {
        $python = Install-PythonViaWinget
        if (-not $python) {
            # Install-PythonViaWinget already printed instructions before
            # exiting, so this branch is just a defensive fallback.
            Fail "Python install ran but the interpreter still isn't visible. Open a new PowerShell and re-run .\setup.ps1."
        }
    } else {
        Fail @"
Aborted. Install Python 3.10+ and re-run setup.ps1 in a fresh PowerShell:
    winget install Python.Python.3.12
"@
    }
}

Write-Host "[setup.ps1] Using Python at: $($python.Exe) $($python.Args -join ' ')" -ForegroundColor Cyan

# --- create venv if missing ---------------------------------------------------

$venvPath = Join-Path $PSScriptRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "[setup.ps1] Creating virtual environment at .venv ..." -ForegroundColor Cyan
    & $python.Exe @($python.Args) -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { Fail "venv creation failed (exit $LASTEXITCODE)." }
} else {
    Write-Host "[setup.ps1] .venv already exists, reusing it." -ForegroundColor Cyan
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Fail "Expected $venvPython after venv creation but it wasn't there."
}

# --- install deps using the venv's Python directly ----------------------------
# (Avoids the Activate.ps1 execution-policy gotcha entirely.)

Write-Host "[setup.ps1] Installing dependencies ..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed." }
& $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { Fail "Dependency install failed." }

Write-Host ""
Write-Host "[setup.ps1] Done. Run the app with: .\run.ps1" -ForegroundColor Green
Write-Host "[setup.ps1] Run the tests with:  .\test.ps1" -ForegroundColor Green
