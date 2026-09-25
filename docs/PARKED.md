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
