# M6: Test Roads + Pondy Bazaar Benchmark

**Date:** 2026-09-28  
**Status:** M6 complete — three test roads validated, Pondy Bazaar comparison written.

---

## Three test roads

All three were run through the full pipeline: measured width → design engine → cross-section options.

### 1. Anna Salai (Mount Road)
**Segment:** `247714535-256039826-0` (547 m, primary, one-way, 4 OSM lanes)  
**Width:** 48.8 m **MEASURED** (Overture Maps building footprints)  
**Context tested:** bus_route

| Option | Lanes | Lane width | Footpath | Cycle | Trees | Notes |
|--------|-------|-----------|----------|-------|-------|-------|
| Balanced (cycle + shade) | 2 | 3.5 m | 8.2 m/side | ✓ | ✓ | |
| Traffic priority | 3 | 3.5 m | 8.6 m/side | — | ✓ | Bus bays added |
| Walking & bus | 1 | 3.0 m | 11.5 m/side | — | ✓ | |

All three options fit within 48.8 m. Engine sums to 4880 cm exactly. No options dropped.

**What the test revealed:**
- Measured width is plausible: Anna Salai is a major divided arterial with wide setbacks. 48.8 m for a one-way carriageway segment (one direction of a divided road) is on the high side but not impossible given wide frontage roads and service lanes on this corridor.
- Bus route context correctly triggers bus bays in Traffic priority.
- All outputs carry the UNCITED placeholder warning (see Gaps section).

---

### 2. South Usman Road
**Segment:** `13284331471-13284331478-0` (1,040 m — longest single segment, secondary, two-way)  
**Width:** 34.2 m **MEASURED**  
**Context tested:** market (T. Nagar shopping district)

| Option | Lanes | Lane width | Footpath | Cycle | Trees |
|--------|-------|-----------|----------|-------|-------|
| Balanced (cycle + shade) | 4 | 3.5 m | 4.0 m/side | ✓ | ✓ |
| Traffic priority | 4 | 3.5 m | 3.8 m/side | — | ✓ |
| Walking & shade | 2 | 3.0 m | 8.6 m/side | — | ✓ |

All three options fit. Engine sums to 3420 cm exactly. No options dropped.

**What the test revealed:**
- Market context triggers wider footpath target, visible in Walking & shade option (8.6 m versus what the engine would allocate without context).
- 4-lane two-way secondary with 4 m footpaths in Balanced is a common urban arterial cross-section. Reasonable.
- The 34.2 m measured width is consistent with the actual road: South Usman Road is a major shopping corridor.

---

### 3. Ennore High Road
**Segment:** `7825217431-9886838375-0` (1,653 m, secondary, two-way)  
**Width:** 19.1 m **MEASURED**  
**Context tested:** none

| Option | Lanes | Lane width | Footpath | Cycle | Trees |
|--------|-------|-----------|----------|-------|-------|
| Balanced (cycle + shade) | 2 | 3.5 m | 2.5 m/side | ✓ (2.0 m) | ✓ (1.5 m) |
| Traffic priority | 4 | 3.2 m | **1.9 m/side** | — | ✓ (1.2 m) |
| Walking & shade | 2 | 3.0 m | 4.5 m/side | — | ✓ (2.0 m) |

All three options fit. Engine sums to 1910 cm exactly. No options dropped.

**What the test revealed — design concern flagged:**

Traffic priority squeezes 4 lanes onto a 19.1 m two-way road. The result is technically valid per the placeholder rules (footpath 1.89 m ≥ 1.8 m minimum; lanes 3.23 m ≥ 3.0 m minimum), but 4 lanes at 3.23 m with 1.89 m footpaths is not a sensible urban cross-section. A 19.1 m road realistically supports 2 lanes comfortably, not 4.

**Root cause:** the lane default is "2 per direction for a secondary road" (UNCITED). On a 19.1 m two-way road, that means 4 lanes, and Traffic priority tries to fit them all rather than shedding lanes. Walking & shade is better here (2 lanes at 3.0 m + 4.5 m footpath).

**Fix needed (parked for M6.1 or M7):** Cap the lane default based on available width, or add a constraint that Traffic priority sheds a lane pair when the footpath drops below 2.0 m. Tracked in the Gaps section below.

---

## Pondy Bazaar benchmark

**What was actually built (2019–2020):**  
The Pondy Bazaar pedestrianisation project, led by GCC with ITDP technical assistance under the Chennai Smart City programme, converted the Panagal Park road (the one-way secondary loop around Panagal Park in T. Nagar) into a demonstration pedestrian-priority street. Key changes:
- Carriageway reduced to a single access lane (deliveries + emergency access)
- Wide pedestrian plazas created on both sides
- Street trees, benches, vendor kiosks, and paved walkways installed
- Junction improvements to slow motor traffic entering the street

This is the most prominent publicly documented pedestrian-priority street intervention in Chennai to date, and a comparable reference for what a "walking priority" option looks like on a wide secondary road.

**Segment used in our engine:**  
`2001005478-2197215546-0` — Panagal Park, secondary, one-way, 50.2 m MEASURED  
Context: market

| Option | Lanes | Lane width | Footpath | Cycle | Trees | Total check |
|--------|-------|-----------|----------|-------|-------|-------------|
| Balanced (cycle + shade) | 2 | 3.5 m | 10.1 m/side | ✓ (3.0 m) | ✓ (8.6 m) | 5020 cm ✓ |
| Traffic priority | 2 | 3.5 m | 11.3 m/side | — | ✓ (10.3 m) | 5020 cm ✓ |
| **Walking & shade** | **1** | **3.0 m** | **13.3 m/side** | — | ✓ (10.3 m) | 5020 cm ✓ |

**Comparison:**

| Attribute | What was built (2019) | Walking & shade option | Match? |
|-----------|----------------------|----------------------|--------|
| Carriageway | ~1 minimal-access lane | 1 lane × 3.0 m | ✓ Yes |
| Pedestrian space | Wide plaza, est. 10–15 m/side | 13.3 m footpath + 10.3 m trees | ✓ Close |
| Trees / greening | Street trees + planting | Tree strip modelled | ✓ Yes |
| Cycle track | None in the 2019 design | None in this option | ✓ Yes |
| Bus bays | Not applicable (one-way, market) | Not present | ✓ Yes |

**What matches:**  
The engine's "Walking & shade" option is structurally aligned with the Pondy Bazaar outcome. Both converge on: minimal carriageway (1 access lane), very wide pedestrian zones (>10 m), street trees. The engine reaches this on the basis of market context + available width, without any knowledge of the 2019 project — which is the point.

**What differs:**  
The 2019 project created a unified plaza (carriageway flush or nearly flush with the pedestrian surface) with removable bollards, rather than a raised footpath. The engine models a conventional raised-kerb cross-section. This is a cosmetic/construction-detail difference, not a design intent difference.

The 2019 project also included vendor kiosk allocation and junction treatments outside the scope of the cross-section engine.

**Verdict:**  
The engine correctly identifies the pedestrian-priority option for a wide market street. Given real cited rules (which would set higher footpath minimums and lower lane-count defaults for commercial streets), the Walking & shade option would likely be the top recommendation. With only placeholder rules, the engine hedges — it does not nominate a top option, that is the LLM explanation's role.

---

## Gaps revealed by M6

| # | Gap | Severity | Suggested fix |
|---|-----|----------|---------------|
| 1 | All outputs warn "UNCITED placeholder rules" | High — blocks showing to officials | Replace placeholder rules with cited IRC or Chennai SDP provisions. This is the primary task for rule addition (ongoing). |
| 2 | Traffic priority on narrow two-way secondary (Ennore 19.1 m): 4 lanes leaves 1.89 m footpath | Medium — not useful design | Add a constraint: if Traffic priority footpath drops below 2.0 m, drop a lane pair and retry. Or cap default lanes to 1/direction for secondary roads < 24 m. |
| 3 | No demand data for any of the three test roads | Low — defaults are labelled | Link actual traffic counts to these segments once partner provides data. |
| 4 | Measured width for Anna Salai may include the full divided carriageway gap | Low — labelled as measured | Field verify: if our measurement spans the median, the per-carriageway width is lower. Verify override can be set from the UI. |

Gaps 2 is the only one requiring a code change; gaps 1, 3, 4 require data/rules input from the partner.

---

## Summary

Three test roads produce correct, consistent outputs with full provenance trails. The Pondy Bazaar comparison confirms the engine reaches the right design intent (pedestrian priority for a wide market street) without any hard-coded knowledge of the 2019 project. The placeholder-rules warning is the dominant outstanding issue and is not a code bug — it is waiting for real standards to be loaded via the Rules workflow.

**M6 done when:** all three produce complete outputs ✓ and this note is written ✓.
