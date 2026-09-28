# Phase 1: Roads Module — Milestone Reference

Covers M0 through M7 for the Roads module (Chennai first).
**Status column:** ✅ Done · 🔄 Next · ⬜ Upcoming

---

## M0 — Skeleton ✅

**Goal:** Both servers run, a blank Chennai map appears, `/health` works.

**What was built:**
- Repo structure: `backend/`, `frontend/`, `core/`, `modules/roads/`, `layers/`, `config/cities/`, `docs/`, `scripts/`, `samples/`
- FastAPI backend with a `router` auto-discovery (any `modules/<name>/module.py` with a `router` is mounted automatically)
- React 19 + TypeScript + Vite + Tailwind + MapLibre GL JS frontend
- DuckDB (spatial extension) + GeoParquet storage, accessed only through `core/store/` — nothing else touches DuckDB directly
- `.env.example` with `DATA_DIR`, `OLLAMA_HOST`, `LLM_PROVIDER`; `.env` is gitignored
- `scripts/setup.ps1`, `scripts/backend.ps1`
- `.claude/launch.json` for in-editor preview

**Key decisions:**
- Data root is `DATA_DIR` (default `D:\citydata`), outside the repo, never committed
- DuckDB connections are short-lived (no held-open connections between operations)
- Paths in the catalog are relative to `DATA_DIR` so the folder can move
- Basemap: OpenFreeMap "positron" — free, no API key, light grey so our layers stand out
- MapLibre 6 is excluded from Vite's dep pre-bundling (pre-bundling breaks its web worker path)

---

## M1 — City Map ✅

**Goal:** All Chennai roads on the map, coloured by width confidence, clickable, searchable.

**What was built:**
- Pipeline (`scripts/build_roads.ps1`): downloads Chennai OSM data via osmnx → computes lengths in UTM 44N (EPSG:32644) → assigns estimated widths → stores GeoParquet → builds PMTiles vector tiles
- 100,376 road segments, 7,109 km; tiles: 520 files, 7.5 MB, ~4 s to build
- Width defaults in `backend/modules/roads/width_defaults.yaml` (all UNCITED, labelled clearly)
- `feature_overrides` table in the catalog for verified widths — survives rebuilds
- Side panel: road name, type, length, width + source badge (ESTIMATED / MEASURED / VERIFIED)
- Road search by name
- PMTiles served by FastAPI `FileResponse` with HTTP range requests (206)

**Key decisions:**
- Boundary pinned to OSM relation 1766358 (431 km², covers GCC's ~426 km²)
- `seg_id = <smaller node>-<larger node>-<key>` — stable across OSM refreshes
- OSM `width` tag (0.3% of segments) is shown as a hint only, never used as right-of-way
- GCC road centerline KML (35 MB, 34,042 lines) was inspected: no widths, no road class, only names. Name-matching needs direction-aware logic. Parked.

---

## M1b — Data Inbox ✅

**Goal:** Import any file format the partner sends (CSV, Excel, KML, shapefile, GeoJSON, DXF, GeoPackage) → link rows to roads → verified widths upgrade road markers.

**What was built:**
- File readers (`core/inbox/readers.py`): all formats return the same DataFrame shape with a `_row_no` column matching what a person would see opening the file
- Auto-detect column headers (government sheets have title rows above the real header)
- KML: GDAL noise columns dropped; ArcGIS-style HTML-in-description parsed out
- Column mapping: fuzzy-match first, LLM fills gaps using only column names/types (never cell values — partner data stays off the LLM)
- Row-to-road linking by geometry type: point → nearest segment ≤30 m; line → sample-and-vote; polygon → all segments inside/crossing; no geometry → normalised name match
- Ambiguous names (e.g. "1st Street" on multiple roads) are listed for manual resolution, except when one road is ≥5× longer than any namesake
- `import_links` table stores hand-fixes — re-importing the same file never loses them
- Official road names from the GCC KML: sample-and-vote (each sampled point votes for nearest official line within 8 m; ≥60% agreement required). Named segments rose from 39% to 87%
- `name`, `name_official`, `name_match`, `display_name` all stored; nothing silently overwritten
- `IMPORT_HOOKS`: importing a `width_surveys` layer writes verified widths to `feature_overrides` and rebuilds tiles (~4 s)
- Imported layers are one GeoParquet file per import; deleting one import touches nothing else
- Small imported layers served as bbox-filtered GeoJSON (not tiled)
- `SAMPLE_...` files get an orange "SAMPLE: made-up test data" badge everywhere — can't be mistaken for real data
- Sample files in `samples/`: messy traffic CSV, bus-stop KML, width survey

**Key decisions:**
- Topics (`roads`, `people`, `surroundings`) organise both data folders and import targets; a new topic is a YAML file, no code change
- LLM mapping uses only column names/types — partner data never leaves the machine via the LLM path
- PMTiles cache-busted (new URL) after any width-changing import

---

## M2 — Standards to Rules ✅

**Goal:** Rules live as YAML data, not code. A PDF standards document can have rules proposed from it for human review.

**What was built:**
- Rule schema: `dimension` (min/max metres per element) and `conditional` (If/Then/Because)
- Loader + validator (`core/rules/loader.py`, `rules_loader.py`)
- `rules/active/` (reviewed) and `rules/proposed/` (pending review)
- Seed set: 7 UNCITED placeholder rules in `road_elements_placeholder.yaml`, clearly labelled
- LLM extraction: PDF → page-numbered chunks (pypdf) → embeddings (all-MiniLM-L6-v2, ~90 MB, downloaded once) → similarity search → LLM proposes rules with quotes checked near-verbatim against source chunks → lands in `rules/proposed/`
- Expert sheet loader: If/Then/Because CSV/XLSX via the inbox's readers + column mapping, goes straight to `active` (no LLM review)
- Relevance check: top similarity hit is checked by LLM; if it doesn't apply, answer is "No applicable provision found" — not a wrong citation
- Superseded documents are excluded outright from extraction and retrieval
- Rules page in the UI: lists every rule with source (cited clause + quote, or UNCITED badge)

**Key decisions:**
- Rules are in the repo (versioned, reviewable), not in `DATA_DIR`
- Every rule has a `source.authority`: `primary` (real citation), `expert` (partner judgement), `placeholder`, or `superseded`
- Validator rejects any placeholder whose statement doesn't say "UNCITED" or "placeholder"
- A remote Ollama host (`OLLAMA_HOST` not localhost) is treated as external — UI shows the warning; tests pin it to localhost

---

## M3 — Design Engine + Cross-Section Drawing ✅

**Goal:** Click a road → get 2–3 cross-section options drawn to scale, each summing exactly to the right-of-way, with rules cited.

**What was built:**
- Pure Python engine in `backend/modules/roads/design/` — no I/O, no LLM, deterministic
- Works in whole centimetres (integers) — "sums exactly" is literally guaranteed
- Three named options: **Balanced** (footpath + trees + cycle track + lanes), **Traffic priority** (footpath + as many lanes as fit), **Walking & shade** (wide footpaths + trees + optional bus bays)
- Optional elements (median, bus bay, sometimes trees) are shed in order when road is narrow; lanes drop to minimum. If required minimums still don't fit, option is DROPPED with the width it needs and the reason
- Progressive filling allocation: every element starts at its rule minimum → all grow toward targets → spare width distributed by weights to soft maxima → overflow into "sink" elements
- Demand integration (`demand.py`): linked traffic counts set lane count; linked pedestrian counts set footpath width; linked bus stops count as a bus route. All with provenance (data / default / user / map)
- Warnings: estimated width, placeholder rules, waterlogging (noted but not modelled yet), manual width
- Hypothesis property tests: 250 random roads × all classes × all contexts — exact sums, no rule broken, symmetry within 1 cm, valid lane counts, determinism
- SVG cross-section drawing in the frontend, drawn to scale

**Key decisions:**
- LLM never does geometry or arithmetic — this is enforced by architecture, not convention
- `design_defaults.yaml` holds preferences only; they are always clamped by rules' min/max and can never override a rule
- Two-way roads always get an even lane count (minimum 2); one-way roads minimum 1
- Rules' `applies_to` supports `road_class` and `context`; unknown keys mean the rule is skipped

---

## M4 — LLM Explanations + PDF Export ✅

**Goal:** Each design option gets a plain-English explanation in the planner's voice, with every cited rule validated. One-page PDF exportable for showing to officials.

**What was built:**
- `backend/modules/roads/design/explain.py`: builds a structured prompt from the design result, calls the LLM, validates that any rule IDs cited by the LLM appear in the engine's used-rules dict
- Unknown citations are flagged with a warning but the text is kept
- Graceful fallback: `LLMError` returns empty explanations — design panel and PDF still work
- `POST /{city}/segments/{seg_id}/design/explain` endpoint
- `backend/modules/roads/design/pdf.py` (fpdf2): one-page PDF with coloured cross-section rectangles, legend, metrics, explanations (if available), rules applied with authority badges, warnings. Footer: "Not a statutory document"
- `GET /{city}/segments/{seg_id}/design/pdf` endpoint (calls explain best-effort, always returns PDF)
- `_design_for()` helper in `module.py` deduplicates validation + engine + segment logic shared by three endpoints
- Frontend: "Explain options" button → AI Recommendation section (comparison text + per-option blue text); "Export PDF" button → browser download. Both reset when design updates
- 33 new backend tests, 71 frontend tests

**Key decisions:**
- Explanations are a separate on-demand step (design is fast; LLM is slow — don't slow down every design call)
- LLM may only cite rule IDs the engine actually used — validated post-LLM by regex
- Monkeypatching rule: patch `modules.roads.design.explain.chat_json` (where the name is *used*), not `core.llm.client.chat_json` (where it is *defined*)
- fpdf2 compresses to ~2 KB; test threshold is 1,500 B

**Known gap:** No design option exists for roads narrower than ~9.6 m. The engine correctly reports "NOT POSSIBLE AT THIS WIDTH" but leaves narrow residential streets (8 m and under) with no output. A "Narrow shared street" option is needed. Parked for M7.

---

## M5 — Better Widths ✅

**Goal:** Most arterial and sub-arterial roads get `measured` widths from building footprints, with a confidence score. Manual override (`verified`) works from the UI.

**What was built:**
- 973,414 Overture Maps building polygons downloaded (124 MB, release 2026-08-19.0)
- `backend/modules/roads/pipelines/measure_widths.py`: sample points every 15 m along each arterial centreline, cast perpendicular rays 50 m each side, take median of valid (both-sided, 3–80 m) samples per segment
- 6,142 / 18,318 arterial segments measured (33.5%); segments near junctions or open areas get no measurement (expected)
- Stored as `feature_overrides` attribute `"width_m_measured"` — never overwrites `"width_m"` (verified)
- Width priority: verified > measured > estimated. Detail string shows sample count + IQR for transparency
- `refresh_widths()` fast-path: re-apply widths + rebuild tiles without re-downloading OSM
- `POST /roads/{city}/segments/{id}/width/verify` endpoint: saves human-entered verified width, triggers `refresh_widths()`
- DesignPanel: "Set as verified ✓" button wired to the endpoint; updates badge without requiring parent re-fetch
- 19 new tests (measure_widths pipeline + verify endpoint), all passing
- `scripts/measure_widths.ps1` convenience script

**Key decisions:**
- `gpd.read_parquet(parquet, columns=["geometry"])` rather than DuckDB fetchall — much faster for 973k rows
- Overture Maps `--no-stac --release 2026-08-19.0` flags required (STAC catalog did not index the 2026-09 release for this bbox)
- Cycle tracks on each side of a two-way road are each one-directional; the 2.0 m one-way minimum applies per side

---

## M6 — Test Roads + Pondy Bazaar Benchmark ✅

**Goal:** Three real Chennai roads tested end-to-end, and the Pondy Bazaar redesign reproduced and compared to what was actually built.

**What was built:**
- Ran all three test roads through design endpoint; all produce correct, complete outputs
- Pondy Bazaar benchmark written: `docs/pondy_bazaar_benchmark.md`

**Test roads:**
| Road | Class | Width | Source | Options |
|------|-------|-------|--------|---------|
| Anna Salai (Mount Road) | primary | 48.8 m | measured | 3 options, 0 dropped |
| South Usman Road | secondary | 34.2 m | measured | 3 options, 0 dropped |
| Ennore High Road | secondary | 19.1 m | measured | 3 options, 0 dropped |

**Gaps revealed (see `docs/pondy_bazaar_benchmark.md`):**
1. UNCITED placeholder rules warn on every output — needs real cited rules (IRC / Chennai SDP)
2. Traffic priority on Ennore (19.1 m two-way): 4-lane default leaves 1.89 m footpath (technically above 1.8 m placeholder minimum, but sub-optimal). Root cause: uncited "2 per direction" default for secondary. Parked — fixing requires real demand data or rule update.
3. No linked traffic/pedestrian counts for these segments — all demand inputs use UNCITED defaults

**Pondy Bazaar result:** Engine's "Walking & shade" option (1 lane × 3 m + 13.3 m footpath/side) structurally matches what was built in 2019. Comparison is in `docs/pondy_bazaar_benchmark.md`.

---

## M7 — Narrow Road Options ✅

**Goal:** Roads under ~9.6 m get at least one valid design option instead of "NOT POSSIBLE AT THIS WIDTH".

**What to build:**
- New engine option: **Narrow shared street** (applicable to roads 5–9.5 m)
  - Required elements: carriageway + at least one footpath (one side, fallback minimum ~1.2 m)
  - Optional: second footpath if width allows
  - No cycle track, no median, no bus bay
  - Context: waterlogging noted (drain element if width allows), school nearby → wider footpath target
- Rule set for narrow streets (currently missing — placeholder rules don't cover this range)
- Label clearly as a fallback with a warning ("Below the minimum for a standard two-footpath layout")
- Property tests: extend hypothesis suite to cover 5–9.5 m range

**Done when:** Clicking an 8 m residential street produces at least one design option, correctly labelled as a narrow-street fallback.

---

---

## M8 — Per-option Inline Explanations ✅

**Goal:** Each design option shows an LLM explanation in its own card, below the cross-section diagram, loaded on demand per option.

**What was built:**
- `explain_one(result, option_id)` in `explain.py`: builds a focused single-option prompt, calls the LLM, validates citations. Faster than the full explain (one LLM call for one option, not all options).
- `POST /{city}/segments/{seg_id}/design/explain/{option_id}` endpoint: runs design, checks option exists, calls `explain_one`. Returns `{explanation: str, warnings: [str]}`.
- Removed global "Explain options" button from DesignPanel.
- Each `OptionCard` now has its own "Explain this option" button below the rules section.
- Explanation renders below the CrossSection diagram (not above it) with a "Regenerate explanation" link once loaded.
- Per-option LLM errors and citation warnings shown inline in the card.
- 8 new backend tests (build_prompt_one, explain_one unit, per-option endpoint); 4 frontend tests updated/added.

**Key decisions:**
- Per-option rather than all-at-once: slower total if you explain everything, but faster for one option and closer to where you are looking.
- Explanation state is local to `OptionCard` so switching roads resets it automatically.
- Global `/design/explain` endpoint kept for the PDF export path.

---

## Guiding principles (all milestones)

1. The LLM never does geometry or arithmetic — the deterministic engine does.
2. Every number has provenance: `width_source` (estimated / measured / verified), every rule has a source doc + clause.
3. Rules are data (YAML), not code. Changing a standard = editing YAML.
4. Superseded documents are never cited.
5. Missing data never blocks — fall back to an estimate and label it clearly everywhere.
6. All data stays on this machine, under `DATA_DIR`, outside the repo. Partner data never enters LLM prompts.
7. Estimated and placeholder data must be labelled everywhere it appears.
8. `llm_is_external` = true for a non-localhost Ollama host or NVIDIA NIM — shows warning in the UI header.
