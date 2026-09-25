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
- **GCC names.** Use the GCC centerline KML as an official-name source (`name_gcc` next to the OSM name,
  both labelled). Needs direction-aware matching (overlap along the segment, not a nearest midpoint),
  plus fuzzy name comparison. Would take named segments from 39% to roughly 89%.
- **Divided roads.** Major roads mapped as two one-way OSM carriageways appear as two parallel segments.
  Each carries the whole-road width estimate plus a warning. Pairing them into one road is needed before
  designing them (M3) and measuring them (M5).
- **Width defaults are UNCITED.** Replace with cited values when the standards document arrives.
- **Road = same name.** "Whole road" groups segments by exact OSM name, so spelling variants split a road
  and different streets sharing a common name ("1st Street") merge in search. Fine for M1; revisit with
  GCC road_id.
- **Tiles bake in widths.** A verified width entered in M5 needs a tile rebuild (~4 s) to change colour.
