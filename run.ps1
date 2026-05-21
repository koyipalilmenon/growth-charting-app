# Launch the Streamlit app using the venv's Python (no activation needed).

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[run.ps1] .venv is missing. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

& $venvPython -m streamlit run (Join-Path $PSScriptRoot "app.py")
