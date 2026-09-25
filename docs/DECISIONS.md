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

## 2026-09-25: M1b data inbox

- **Official road names, decided (was parked in M1).** Sample-and-vote matching (`core\geo.py`:
  sample points along each OSM segment, each votes for the nearest official line within 8 m; a
  segment needs ≥60% agreement) instead of nearest-line, so a segment near a junction is not named
  by the crossing street. `core\text.py` normalises names (expands abbreviations, unifies ordinals
  "VIIth"/"7"/"7th", joins initials "N.S.K." → "nsk") before comparing, and only calls two names
  "similar" when the shorter one has a distinctive word — "1st Street" never auto-matches "1st Link
  Street" this way, but "Anna Street" matches "Anna Street Padi". Result: named (OSM or official)
  rose from 39% to 87%; where both name a segment, 51% agree (same/similar) after normalising —
  most of the remaining "different" pairs are real differences (a crossing street's name bleeding
  onto a short link, or genuinely different local names), not matching failures.
  `name`, `name_official`, `name_match`, `display_name` (OSM first, else official) are all stored,
  so nothing is silently overwritten. City config gets `official_road_names` (source prefix, field
  names) so a future city can plug in its own official source or have none.
- **Topics organise imports too.** A new import target is one YAML file under `layers\<topic>\`
  (`kind: imported`, `link_to: roads`, its fields with types/aliases). The inbox, mapping, and API
  read every one automatically — adding "cycle counts" later needs no code change.
- **Column mapping: auto-detect first, LLM only fills gaps.** `core\inbox\mapping.py` scores column
  headers against each field's name/label/aliases (fuzzy match); only when asked does it call the
  LLM, and only with column *names and inferred types* — never cell values — so a local Ollama model
  is enough and an external provider never sees partner data. The LLM's answers are validated
  (unknown headers/fields and duplicate columns dropped) before they reach the mapping. A person
  always confirms before import.
- **Linking a row to a road, by kind of geometry:**
  point → nearest segment within 30 m; line → every segment it runs along (same sample-and-vote as
  names, but against many target segments, collecting all of them, not just the best); polygon →
  every segment inside/crossing it; no geometry → road name, normalised then fuzzy-matched. A name
  used by several separate streets (`core\modules\roads\linking.py`: segments >150 m apart cluster
  as different streets) is never guessed — the row is listed "ambiguous" with each candidate street,
  for a person to pick — *unless* one street is ≥5× longer than any namesake, in which case it's
  picked automatically with a note (handles the very common "1st Street" pattern without silently
  guessing on a genuinely ambiguous case).
- **Unmatched rows are fixed in the UI, not the file.** A person types a road name or picks from
  the ambiguous candidates; the choice is stored in `import_links` (keyed by the file's own row
  number) and re-applied on every re-import, so re-uploading a corrected file, or just re-running
  the same import, never loses a hand-fix.
- **Layers from imports are partitioned: one GeoParquet file per import** (`layers\<layer>\<import_id>.parquet`),
  read with a DuckDB glob. Deleting an import deletes its file and re-records the layer from what's
  left (or removes the layer entirely if that was the only import) — no need to touch other imports'
  data.
- **A layer can react to being imported.** `IMPORT_HOOKS` in a module (`modules\roads\hooks.py`) — importing
  `width_surveys` takes the median width per linked segment, writes it to `feature_overrides` (already
  built in M1) keyed by that import's id, and refreshes the roads layer + tiles (~4 s, no download).
  Deleting the import removes exactly those overrides and refreshes again. `IMPORT_LINKERS` similarly
  lets a module supply the "link to my rows" logic for topics that need it (only `roads` for now).
- **PMTiles bake in width, so the frontend reloads the roads vector source (new URL, cache-busted)
  after any import that can change widths**, rather than trying to patch tiles in place.
- **Small imported layers are served as plain GeoJSON, filtered to the map's current view**
  (`/api/cities/{city}/layers/{layer}/features?bbox=...`), not tiled — they're at most a few thousand
  rows, and this keeps them simple and always fresh. Only the big roads layer needs tiles.
- **Every readable format returns the same shape** (`core\inbox\readers.py`): a DataFrame or
  GeoDataFrame with a `_row_no` column matching what a person would see opening the file (spreadsheet
  row number, or feature number), so problems can always be reported in the file's own terms.
  CSV/Excel: the header row is auto-found (government sheets often have title/blank rows above it) by
  looking for the first mostly-text, mostly-full row. KML: GDAL's noise columns
  (`timestamp`,`tessellate`,...) are dropped, and ArcGIS-style KML that puts attributes in an HTML
  table inside `<description>` is parsed out. Formats needing GDAL drivers we don't have installed
  (old `.xls`, AutoCAD `.dwg`) get a specific message telling the person how to convert them, rather
  than a generic error.
- **Sample/test files are opt-in and unmissable.** Any file named `SAMPLE_...` is registered with
  "(SAMPLE: made-up test data)" in its name and licence; every row imported from it carries
  `is_sample: true`, shown as an orange "SAMPLE" badge everywhere (map panel, layer list, import
  result) and drawn dashed/orange-outlined on the map, so it can never be mistaken for real data.
  `samples/` in the repo holds three: a messy traffic-count CSV (title rows, abbreviations, a typo,
  an ambiguous name, a bad number, one row placed by lat/lon), a bus-stop KML (one point that must
  not link to a road), and a width survey (to demo the verified-width upgrade).
- **Tests build a small made-up road network through the real pipeline** (`backend\tests\conftest.py`:
  a `world` fixture — a named street, a crossing street, two separate streets sharing a name, an
  OSM-unnamed street with only an official name, a one-way street with merged OSM classes and a
  width tag), instead of mocking the pipeline's internals. All inbox/roads/pipeline tests run against
  it, so they exercise the same code path the app does, without any network access.
