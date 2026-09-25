# City Planning OS

An operating system for city planning in Indian cities (Chennai first). It grows one module at a time.
**Phase 1 is the Roads module:** pick a road on the map and get 2–3 standards-based cross-section
designs, each with a drawing, a plain-language explanation and a citation for every element.

Status: **M3 (design engine)** on top of **M2 (standards to rules)** on top of **M1b (data inbox)**: every Chennai road is on the map, clickable, with an *estimated* width
and its OpenStreetMap + official (Greater Chennai Corporation) name side by side. A data inbox turns
partner files (CSV, Excel, KML, GeoJSON, shapefile, GeoPackage, AutoCAD .dxf) into map layers linked
to the right road, and a road width survey upgrades the roads it covers to *verified*.
See `docs/DECISIONS.md` for what was decided and why, and `docs/PARKED.md` for known gaps we are
deliberately not doing yet.

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

## Build the roads layer
```powershell
.\scripts\build_roads.ps1                     # downloads today's OSM data for Chennai, builds layer + tiles
.\scripts\build_roads.ps1 --date 2026-09-25   # rebuild from an existing download, no network
```
Writes `DATA_DIR\cities\chennai\roads\` (GeoParquet, PMTiles, `roads_build_report.json`) and registers
the raw OSM files in the catalog. Re-running replaces the output cleanly.

## Bring in partner data
Open the **Data inbox** tab in the app. Upload a file (or drop one into `DATA_DIR\raw\<topic>\` and
click Register), pick what it contains (traffic counts, a width survey, bus stops, ...), check the
column mapping, and import. Rows are linked to the right road automatically, by location or by name;
rows that can't be matched are listed so you can link them by hand. Importing a road width survey
upgrades the roads it covers to **verified**.

Try it with the made-up test files in [samples/](samples/) — see `samples/README.md`. Everything
imported from a file named `SAMPLE_...` is labelled "SAMPLE: made-up test data" everywhere it appears
(map, layer list, panels), so it can never be mistaken for real data.

## Design a road
Click any road on the map, then **Design this road**. Optionally change the width (what-if) and tick
context (school, bus route, metro, waterlogging, market). You get up to three options drawn to scale,
each with the rules it obeyed, and a clear list of options that don't fit and why. The layouts come from
a deterministic engine (`backend/modules/roads/design/`), never from the AI. Until the real standards
arrive it uses the UNCITED placeholder rules and an estimated road width, and says so in every result.

## Rules and standards
Open the **Rules** tab. *Rules* lists every rule with its source (cited clause + quote, expert
judgement, or a clearly labelled UNCITED placeholder) and lets you approve/reject AI-proposed ones.
*Documents* takes a standards PDF (mark it active or superseded), embeds it, lets the AI propose rules
for you to review, and answers questions with a relevance-checked citation. *Expert sheet* loads the
If / Then / Because sheet. Try it with `samples\SAMPLE_standards_excerpt.pdf` and `samples\SAMPLE_expert_rules.csv`.
The AI runs on `OLLAMA_HOST` (default local); if it is another machine, the header says so.

## Back up the data
```powershell
.\.venv\Scripts\python.exe scripts\backup.py      # -> D:\citydata_backups\citydata_<time>.zip
```
Skips regenerable files (tiles, embeddings). Restore = unzip to a folder and point `DATA_DIR` at it.

## Test
```powershell
.\.venv\Scripts\python.exe -m pytest    # backend: ~375 tests
cd frontend; npm test                    # frontend: 71 tests
```
Backend tests use a throwaway temporary data folder, never your real `DATA_DIR`. Most build a small
made-up road network (`backend\tests\conftest.py`) through the real pipeline code, so they exercise
the same logic the app uses without downloading anything.

## Layout
```
backend\app\          FastAPI entry point (finds modules automatically)
backend\core\         shared: config, store\ (the only code that touches DuckDB), layer registry,
                       inbox\ (file readers, mapping, validation, import), llm\, text.py, geo.py
backend\modules\      one folder per module (roads\ now)
layers\<topic>\       topic + layer definitions (roads, people, surroundings) and import targets
config\cities\        one YAML per city
frontend\src\core\    map, API client, data inbox UI (core\inbox\)
frontend\src\modules\ module UIs
scripts\              setup, run, pipelines, backup
samples\              made-up test files for trying the data inbox
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
