# Parked

Ideas and known gaps we are deliberately not doing yet.

## Scope (from the Phase 1 plan)
- Live traffic / phone-data feeds, bus fleet planning, parking revenue, tenders, flood analysis,
  3D, pavement/material engineering, user accounts.
- Modules after Roads: trees & shade, flooding/sponge parks, buses & parking, public spaces/schools/housing,
  master plan & tenders.

## Technical
- **Offline basemap.** The basemap comes from OpenFreeMap over the internet. A self-hosted Chennai
  basemap extract (PMTiles) would make the app fully offline.
- **PostGIS.** Only if we outgrow one machine; `backend\core\store\` is the swap point.
- **Test warning:** Starlette warns that `httpx` with its TestClient is deprecated. Harmless for now.
- **Frontend module registry.** `App.tsx` imports the roads UI directly; make modules pluggable on the
  frontend when a second module arrives.

## Roads data (known gaps)
- **Divided roads.** Major roads mapped as two one-way OSM carriageways appear as two parallel segments.
  Each carries the whole-road width estimate plus a warning. Pairing them into one road is needed before
  designing them (M3) and measuring them (M5).
- **Width defaults are UNCITED.** Replace with cited values when the standards document arrives.
- **Road = same `display_name`.** "Whole road" and search group segments by exact display name, so a
  segment named only by OSM and one named only by the official source never merge even if they're the
  same street physically. Revisit with the official `road_id` once GCC name matching has been in use
  a while and we trust it more.
- **Tiles bake in widths.** A verified width import triggers a tile rebuild (~4 s) so colours update;
  there's a brief window where the roads vector source is swapped (new URL) which could show a flash
  of the old tiles on a slow connection.

## Data inbox (known gaps)
- **PDF tables and photos.** Registered and stored, but not read automatically yet — someone has to
  copy the numbers into a CSV/Excel sheet. The brief listed "photos" among survey formats; OCR/table
  extraction from PDFs is real work, parked until a partner actually sends one.
- **AutoCAD `.dwg`.** GDAL can't read it directly; the inbox asks for `.dxf` (an AutoCAD export) instead.
- **Old `.xls`.** Needs a legacy Excel reader we haven't added; the inbox asks for `.xlsx`.
- **No de-duplication across imports.** Importing the same survey twice from two different files (e.g.
  a partner resends a CSV with one new row) creates two import records; nothing merges or flags the
  overlap. Fine while there are few imports; revisit if this becomes a real workflow.
- **`width_surveys` overrides by median, no confidence tracking yet.** Multiple survey rows on one
  segment collapse to their median; the brief's "sample count + spread" confidence score for measured
  widths is for level-2 (M5), not surveyed/verified widths, which are meant to be exact.
- **CRS-less files (DXF, some old shapefiles) need the EPSG code typed in.** No CRS-guessing from the
  coordinate range; if that turns out to be common, add a heuristic (e.g. values in the low thousands
  are very likely UTM 44N for Chennai).

## Design engine (known gaps, M3)
- **No layout for very narrow roads.** Below 9.6 m (two-way) / 6.6 m (one-way) no option satisfies the
  placeholder minimums, so the result is empty with reasons. A shared-street / one-sided-footpath option
  for lanes and alleys is a later addition.
- **Not modelled:** parking, on-street vending, crossings and speed tables (school/market only widen
  footpaths), turning lanes/junctions, drainage or sponge elements (waterlogging is only noted),
  cycle tracks on one side only, kerb details, bus-bay length/taper.
- **All preference numbers are UNCITED** (`design_defaults.yaml`): PCU factors, lane capacity, pedestrian
  flow, class lane defaults. Replace with cited values with the standards.
- **Design is per segment,** not per whole named road; divided roads (two one-way carriageways) are still
  designed as one carriageway each (see divided-roads note above).
- **Pedestrian counts are assumed to be peak-hour counts** (the sheet has a free-text period).
- **Only three named options.** Adding an option means adding an entry in `design_defaults.yaml` plus
  the one line naming it in `engine.design`.
