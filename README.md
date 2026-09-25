# City Planning OS

An operating system for city planning in Indian cities (Chennai first). It grows one module at a time.
**Phase 1 is the Roads module:** pick a road on the map and get 2–3 standards-based cross-section
designs, each with a drawing, a plain-language explanation and a citation for every element.

Status: **M0 (skeleton)**. See `docs/DECISIONS.md` for what was decided and why,
and `docs/PARKED.md` for known gaps we are deliberately not doing yet.

## Principles (short version)
- The LLM never does geometry or arithmetic; a deterministic engine does.
- Every number has provenance (source, page, clause; or estimated / measured / verified).
- Rules are data (YAML), not code. Superseded documents are never cited.
- All data stays on this machine, under `DATA_DIR`, outside the repo.

## Setup (once)
Needs Python 3.12, Node 20+, and (from M2) Ollama with `qwen2.5:7b`.

```powershell
.\scripts\setup.ps1
```
This creates `.venv`, installs backend and frontend packages, and creates `.env` from `.env.example`.
Check `DATA_DIR` in `.env` (default `D:\citydata`).

## Run
```powershell
.\scripts\backend.ps1          # API on http://localhost:8000  (health: /health)
```
```powershell
cd frontend; npm run dev       # UI on http://localhost:5173
```

## Test
```powershell
.\.venv\Scripts\python.exe -m pytest
```
Tests use a throwaway temporary data folder, never your real `DATA_DIR`.

## Layout
```
backend\app\          FastAPI entry point (finds modules automatically)
backend\core\         shared: config, store\ (the only code that touches DuckDB), layer registry
backend\modules\      one folder per module (roads\ now)
layers\<topic>\       topic + layer definitions (roads, people, surroundings)
config\cities\        one YAML per city
frontend\src\core\    map, API client
frontend\src\modules\ module UIs
scripts\              setup, run, pipelines, backup
docs\                 DECISIONS.md, PARKED.md
```

Data lives under `DATA_DIR`, never in the repo:
```
DATA_DIR\
  catalog.duckdb                                  index: cities, sources, layers
  raw\<topic>\<source>\<date>\...                 untouched downloads and partner files
  cities\<city>\<topic>\layers\<layer>.parquet    cleaned GeoParquet
  cities\<city>\<topic>\tiles\<layer>.pmtiles     vector tiles for big layers
  documents\<topic>\...                           standards PDFs, chunks, embeddings
  exports\                                        generated PDFs/reports
```
