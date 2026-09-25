# Measure road widths from building footprints, then bake them into the roads layer.
#   .\scripts\measure_widths.ps1                          # city=chennai, today's buildings
#   .\scripts\measure_widths.ps1 --date 2026-09-25        # use existing download for that date
#   .\scripts\measure_widths.ps1 --buildings D:\path.parquet   # explicit file
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")
& ..\.venv\Scripts\python.exe -m modules.roads.pipelines.measure_widths @args
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Widths measured. Rebuilding roads layer..."
    & ..\.venv\Scripts\python.exe -m modules.roads.pipelines.build_roads --date (Get-Date -Format "yyyy-MM-dd")
}
