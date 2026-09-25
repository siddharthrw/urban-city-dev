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

## 2026-09-25: M1 city map

- **Boundary pinned to OSM relation 1766358** ("Chennai" admin boundary, 431 km² in UTM; GCC is ~426 km²),
  in `config\cities\chennai.yaml`, so a geocoder change can't silently swap the area.
- **Road classes:** motorway, trunk, primary, secondary, tertiary, unclassified, residential,
  living_street and their `_link` roads. Service roads, tracks and footways are excluded.
- **Unit = intersection-to-intersection segment** (osmnx simplified graph, made undirected so a two-way
  street is one segment). `seg_id = <smaller OSM node>-<larger OSM node>-<key>`: built from OSM node ids,
  so it stays stable across refreshes and verified widths keyed on it survive rebuilds.
  Result (OSM 2026-09-25): 100,376 segments from 49,867 OSM ways, 7,109 km. The brief's 37,025 was a
  different count (probably ways, possibly a different class list); both are in the build report.
- **Length is computed in UTM 44N (EPSG:32644).** Checked against the exact WGS84 ellipsoid length:
  median difference 0.03% (the UTM scale factor this far from the zone's central meridian). osmnx's
  own length uses a sphere and is off by ~0.2%, so it is not used.
- **Level-1 widths from `backend\modules\roads\width_defaults.yaml`, all UNCITED.** They are guesses at
  typical *existing* Chennai widths, not standards. IRC:86 planned ROW ranges are noted for reference only
  (existing roads are mostly narrower). Where OSM gives a lane count on a two-way road, the estimate is
  `lanes × 3.5 m + 2 × side allowance`, still labelled estimated. On one-way segments of major roads the
  lane count is ignored and the detail warns the segment may be one carriageway of a divided road.
- **OSM `width` tag: hint only** (0.3% of segments), shown in the panel, never used as ROW.
- **Verified widths live in `feature_overrides`** in the catalog (generic: any layer, any attribute),
  and every build applies them on top. Rebuilding never loses a human-entered value.
  No UI to enter them yet (M5).
- **Vector tiles are built in Python**: DuckDB `ST_AsMVT` + the `pmtiles` writer, zoom 10–15, with only
  bigger roads at low zooms. Chennai roads: 520 tiles, 7.5 MB, ~4 s. Every one of the 100,376 segments is
  present at z15 (checked). tippecanoe isn't needed.
- **PMTiles are served by FastAPI `FileResponse`** (HTTP range requests, 206).
- **The map adds our layers on `style.load`, not `load`.** `load` waits for every basemap tile, so a slow
  basemap would keep our roads off the map.
- **Raw OSM archive = osmnx's Overpass cache**, pointed at `raw\roads\osm\<date>\overpass\`.
  Each file is registered in the manifest with checksum and ODbL licence. Re-running with the same
  `--date` rebuilds with no network.
- **GCC road centerline KML inspected** (downloaded 35 MB, registered in the manifest, not used in any layer):
  34,042 lines, 7,141 km, fields `road_id, road_name, objectid, st_length`. **No widths, no road class.**
  Its value is names: every line is named (29,303 unique). A nearest-line match within 10 m would raise
  named segments from 39% to ~89%. But where both are named, only 24% match exactly: many are spelling
  variants ("Karuneegar" vs "KARNEEGAR"), some are wrong matches to a crossing street. Merging needs
  direction-aware matching. Parked pending a decision.
- **Backups:** `scripts\backup.py` zips DATA_DIR minus tiles/embeddings into `<DATA_DIR>_backups\`.
- **Frontend module wiring is explicit for now:** `App.tsx` imports the roads UI directly. A frontend
  module registry can wait until there is a second module.
