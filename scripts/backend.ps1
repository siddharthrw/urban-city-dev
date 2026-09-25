# Start the API server with auto-reload. Run .\scripts\setup.ps1 once first.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$port = 8000
if (Test-Path ".env") {
    $line = Select-String -Path ".env" -Pattern '^\s*API_PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($line) { $port = [int]$line.Matches[0].Groups[1].Value }
}

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend --port $port
