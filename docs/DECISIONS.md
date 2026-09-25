# Decisions

Short log: what we decided, and why. Newest at the bottom.

## 2026-09-25: M0 skeleton

- **Stack:** React + TypeScript + Vite + MapLibre + Tailwind frontend; Python 3.12 + FastAPI backend;
  DuckDB (spatial) + GeoParquet storage. Decided in the project brief.
- **Data root `D:\citydata`, outside the repo.** All data under one folder: portable (copy the folder,
  change one setting). The backend refuses to start if `DATA_DIR` is inside the repo.
- **Data is organised by topic** (`roads`, `people`, `surroundings`, more later), both under
  `DATA_DIR\cities\<city>\<topic>\` and in the repo's `layers\<topic>\`. Topics are not modules:
  people data (traffic counts, footfall) feeds Roads now and Buses later. Modules read whichever
  topics they need. A topic = a folder with `_topic.yaml`; adding one needs no code change.
- **Modules are discovered, not listed.** Any `backend\modules\<name>\module.py` with a `router`
  is mounted automatically.
- **Short-lived DuckDB connections.** DuckDB allows one writing process per file, so neither the API
  nor pipeline scripts hold a connection open between operations.
- **Paths in the catalog are relative to `DATA_DIR`**, so the folder can move.
- **Python setup: plain `venv` + pip** with `backend\requirements.txt` (no `uv`, no packaging).
  `pyproject.toml` only holds tool config.
- **Basemap: OpenFreeMap "positron"** (free, no key, light grey so our coloured layers stand out).
  The browser fetches basemap tiles from it; none of our data is sent anywhere.
- **Git: local only**, no remote, for now.
- **MapLibre 6 is excluded from Vite's dependency pre-bundling** because pre-bundling breaks the path
  to its web worker file (the map rendered blank otherwise).

## Agreed for M1 (not built yet)
- OSM `width` tag (87 roads): shown as a hint only, not used as right-of-way, because it often means
  carriageway width. OSM `lanes` may refine the level-1 estimate, labelled as such.
- Inspect the GCC road centerline KML (~35 MB, OpenCity) and report whether it adds anything over OSM.
