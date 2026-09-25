# Build (or rebuild) the roads layer from OpenStreetMap.
#   .\scripts\build_roads.ps1                      # city=chennai, today's download
#   .\scripts\build_roads.ps1 --date 2026-09-25    # rebuild from an existing download, no network
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")
& ..\.venv\Scripts\python.exe -m modules.roads.pipelines.build_roads @args
