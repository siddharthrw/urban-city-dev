# Plan: Live 3D Corridor (M17 option 2 — built in M19)

**Status: built.** See `docs/phase1.md` M19 for what actually shipped and where it differs from
this plan (kept below as the design record, not edited to match in hindsight). M17/M18 shipped
first (Flow Map + a road-dashboard page carrying the old straight 3D snapshot); this plan was
picked back up once the straight snapshot read as "flat" in review.

## What it is

A street-level driving view down the segment: the cross-section swept along the road's real
curve (not a straight 40 m stand-in), cars actually travelling along the lanes, the road
surface itself tinted by congestion, and a slowly drifting camera. The closest of the four M17
options to "a simulation you can walk into" — and the most expensive to build correctly.

## Why it's parked

[road-sim-detailed.html mockup](https://claude.ai/artifact/VieQ4hpccZVhW756mGP6mv) (option 02)
prototypes the look. Chosen instead: Flow Map (cheap, curve-accurate, reads as congestion
immediately) plus a dashboard page for the existing straight-schematic 3D snapshot. This option
remains the natural "tier 3" addition on top of that if the demo ever needs the extra weight.

## Build plan, when picked up

### Backend
- Decide where the lon/lat &rarr; local-metre projection happens. Two options:
  1. **Client-side flat approximation** (what Flow Map already does) &mdash; no backend change.
     Fine at segment scale (~tens to low hundreds of metres); the same approximation this
     project already accepts for schematic drawings.
  2. **Server-side, via the existing UTM transform** (`city["utm_epsg"]`, used in
     `backend/modules/roads/pipelines/build_roads.py` for length calculations) &mdash; more
     "correct" at scale, but a new endpoint, new pipeline code, and new tests for something the
     client-side approximation already handles at this feature's scale.
  - **Recommendation: reuse the client-side projection Flow Map already has.** Revisit only if
    a segment's curvature turns out to make the flat approximation visibly wrong.

### Frontend
- Rewrite `RoadScene3D.tsx`'s geometry step: build a `THREE.CatmullRomCurve3` from the
  projected segment points, then sweep each cross-section element (footpath, lane, cycle
  track, ...) along it as a ribbon, mitering the joints at bends instead of the current
  straight `BoxGeometry` per element. This is genuinely new geometry code, not a tweak.
- Animate cars along the curve's arc length with `curve.getPointAt(t)`; speed and spacing
  driven by `impact.before.vc_ratio` / `impact.after.vc_ratio`, same mapping already used by
  Flow Map's dots.
- Switch trees to `THREE.InstancedMesh` &mdash; a swept road has many more tree positions than
  the old straight 40 m stretch.
- Tint the road surface material by `vc_ratio` (cheap, same number Flow Map already colors by).
- **Shared-renderer refactor.** We already hit the WebGL-context ceiling once with the
  *current*, lightweight straight-box scene (M17 fix: lazy-mount per `<details>`). A
  curve-swept scene with instancing is heavier per context, and the road-dashboard page may
  want a large version open at the same time as a card's inline one. Before this ships, the
  app needs either a single shared `THREE.WebGLRenderer` reused across mounted scenes, or a
  hard cap on how many corridor scenes can be live at once. Treat this as required
  infrastructure, not a nice-to-have.

### Testing
- jsdom has no WebGL (confirmed in M17's test suite), so the curve-sweep geometry itself needs
  either a pure-function unit test (sample points in, ribbon vertices out, assert no
  self-intersection at a sharp bend) separate from the React component, or a browser-driven
  check — jsdom tests alone won't catch a broken sweep.

## Effort and risk

**Effort:** High. **Risk:** Medium-high &mdash; curve-bend geometry correctness, and
performance on whatever machine this is demoed on (this sandboxed browser's WebGL-context
ceiling is low; production browsers are more forgiving but not unlimited).

Everything Flow Map and the road-dashboard page already ship (congestion color mapping,
`impact` data, the dashboard page's layout) carries over unchanged &mdash; this option replaces
only the geometry and rendering inside the 3D snapshot, so picking it up later is additive, not
a rewrite.
