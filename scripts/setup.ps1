# One-time setup (safe to re-run): Python venv + backend deps, frontend deps, .env.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python 3.12 virtual environment in .venv ..."
    py -3.12 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Check DATA_DIR in it."
}

Push-Location frontend
npm install
Pop-Location

Write-Host "`nSetup done. Start the backend with .\scripts\backend.ps1 and the frontend with: cd frontend; npm run dev"
