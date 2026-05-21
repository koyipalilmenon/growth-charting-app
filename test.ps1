# Run the test suite using the venv's pytest (no activation needed).

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[test.ps1] .venv is missing. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

& $venvPython -m pytest @args
