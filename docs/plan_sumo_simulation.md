# Plan: real traffic simulation with SUMO

Status: first slice proven, nothing wired into the app yet. Branched from `feature/3d-road-view`
at commit 59b1511 so the sample-data impact estimate (`backend/modules/roads/design/impact.py`,
BPR-curve based) keeps shipping on that branch untouched while this is built out separately.

## First slice: done

`eclipse-sumo` (the PyPI package) bundles the real SUMO binaries for Windows — no separate
installer needed. Installed and proven end to end:

```
pip install eclipse-sumo traci sumolib
python -m modules.roads.design.sumo_poc.run_poc   # from backend/
```

`backend/modules/roads/design/sumo_poc/run_poc.py` builds the smallest network that produces a
meaningful result (two nodes, one edge, standing in for a road segment — not real OSM geometry
yet), generates demand from the *same* `sample_demand_pcu()` call `impact.py` already uses (so
it's an apples-to-apples comparison, not a different sample number), runs headless `sumo` twice
(5 lanes/direction vs 1), and reads the mean travel time per vehicle back from SUMO's own
`tripinfo.xml`. Output on this machine:

```
Today (5 lanes/direction): 1800 vehicles completed, mean travel time 0.93 min
Narrowed option (1 lane/direction): 1698 vehicles completed, mean travel time 1.15 min
```

Narrower road → fewer vehicles get through in the same window and the ones that do take longer —
a real emergent congestion effect from the simulator, not a formula. This is **not** wired into
`impact.py`/`module.py` and `eclipse-sumo` is **not** added to `backend/requirements.txt` (it's a
~270MB download; making it a hard dependency would break the normal app/CI for everyone, including
the collaborator who only touches `data/`/`docs/`/`rules/`). It's an opt-in proof of concept only.

## Why a separate branch

## Why a separate branch

The current before/after travel-time numbers are a deterministic formula (BPR curve, sample
demand), clearly labeled `is_sample: True`. That's honest and good enough to ship the visual
tools. A real microsimulation is a different kind of system — it needs a road network graph, an
OD (origin-destination) demand matrix, and a simulator — and is worth building as its own
vertical slice without blocking everything else on it.

## What "done" looks like

Given a segment and a redesign option (the same `elements` cross-section the engine already
produces), return actual simulated travel times for "today" vs "this option" instead of the BPR
estimate — same API shape (`impact.before`/`impact.after`), so the frontend doesn't change,
just the `sample_data` flag flips to `False` and `note` changes.

## Components

1. **SUMO** (Simulation of Urban MObility) — open-source microscopic traffic simulator.
   Install via the `sumo` + `traci` Python package (`pip install sumolib traci`), plus the SUMO
   binaries themselves (`netconvert`, `sumo`/`sumo-gui`) — not pip-installable, needs the SUMO
   distribution (eclipse-sumo on PyPI bundles the binaries now, worth checking first).

2. **Network generation** — convert the real road geometry (already in DuckDB/GeoParquet) plus
   OSM context into a SUMO `.net.xml`. `netconvert` can take OSM directly; the cleaner path is
   probably: pull the relevant OSM extract for the segment's bounding box once, feed it through
   `netconvert`, cache the result keyed by `(city_id, seg_id)`.

3. **Demand** — SUMO needs an OD matrix or route flows, not just "vc_ratio". Cheapest honest
   starting point: keep using the same `sample_demand_pcu()` logic from `impact.py` to generate
   a flow (vehicles/hour) on the segment, expressed as a SUMO `.rou.xml` random-trips file
   (`randomTrips.py`, ships with SUMO) rather than inventing a whole OD matrix by hand. Still
   labeled sample demand — only the *simulation of how that demand behaves* becomes real, not
   the demand itself (that needs actual traffic counts, a separate and larger effort).

4. **Running it** — a Python service (new `backend/modules/roads/design/simulate.py` or a
   separate process if SUMO's dependencies make it awkward to share FastAPI's venv) that:
   - writes the generated `.net.xml` / `.rou.xml` to a temp dir
   - runs `sumo` headless (`--no-gui`) via `traci` or subprocess, with the "today" cross-section
     network and then the "option" cross-section network (different lane counts/widths change
     the `.net.xml` edge definitions)
   - reads back mean travel time per vehicle from SUMO's trip output (`tripinfo.xml`)
   - returns `{before_s, after_s}` in the same shape `impact.py` returns today

5. **Wiring in**: `module.py`'s `_attach_impact()` currently always calls the BPR estimator.
   Make that a strategy — try the SUMO path, fall back to BPR estimate with a note if SUMO
   isn't available/installed in the current environment (keeps `main`/other branches working
   without a SUMO install).

## Open questions (decide with Siddharth before building)

- Is installing the real SUMO binaries acceptable in the deploy target, or does this need to
  stay a local/dev-only enhancement with BPR as the production fallback?
- Where does demand data come from long-term — is there an actual Chennai traffic count dataset
  to import, or does this stay `sample_demand_pcu()`-driven indefinitely?
- Per-request simulation latency: SUMO runs are not instant. Likely needs to move from
  "synchronous API call" to "kick off a simulation job, poll/stream the result" — a real API
  shape change the frontend would need to handle (loading state, not instant response).

## Next slice

With the toolchain proven, the next step up is network generation from the *real* segment
geometry (item 2 above) instead of a straight two-node stand-in, and only then wiring a strategy
switch into `module.py` (item 5) — both still open questions above (deploy-target feasibility,
and the sync-vs-job API shape) should get a real answer from Siddharth before that wiring work
starts, since they change the shape of the API response the frontend consumes.
