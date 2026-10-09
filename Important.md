# Important

Notes worth keeping that don't belong in code comments or docs/PARKED.md.

---

## 2026-10-07 — EVR Periyar Salai: unreliable width measurement

A segment of EVR Periyar Salai (39.6 m reported width) was checked against its Street View photo.
The road panel shows: "Measured from building footprints. (6 samples, IQR 11.3 m)".

**What IQR means:** the app measures a road's width at several points (building face to building
face). IQR is how spread out the middle measurements are, after dropping the two most extreme
readings. Small IQR = the measurements agree, trust the width. Large IQR = they disagree, don't
trust it.

**This segment:** IQR 11.3 m on a reported 39.6 m width is about 30% of the total — the six
measurements did not agree. **This width should not be trusted or shown to officials as-is.**

**Also noted from the photo:** this road has a physical median (visible in Street View), which the
app's width measurement and the "Current road" before/after diagram do not account for — the
diagram only ever draws a notional footpath + one undivided carriageway, never a median. This is a
known, documented simplification (see "Current road" note in the app), not specific to this road.

**What was ruled out:** initially guessed this was the "divided road mapped as two one-way
carriageways" gap already listed in docs/PARKED.md. A screenshot of the map showed only one line
for this road at this location, not two parallel ones — so that explanation does not apply here.
The real cause is measurement noise (high IQR), unrelated to the divided-road issue.

**Action needed:** this road needs a real survey or an official record for its width before it's
designed against. Don't treat high-IQR "measured" widths as reliable just because they're not
flagged "estimated" — check the IQR number specifically.

---

## 2026-10-07 — Width confidence bands shipped; CMDA plausibility check tried and mostly reverted

**Shipped:** every "measured" road now carries a `reliable` / `check` / `unreliable` band computed
from IQR ÷ width (≤15% / ≤30% / >30%). This is live in the map colour, the legend, and the road
panel badge — not just the one-off analysis artifact. City-wide: 985 reliable, 1,512 check,
3,640 unreliable, out of 6,137 measured roads.

**Tried:** a second check using CMDA's Second Master Plan road-width categories (secondary
arterial 18–24 m, primary arterial 27–30.5 m) as an upper-bound sanity check per OSM road class —
the idea being a measurement far above its class's legal maximum is probably wrong.

**Result: doesn't work, reverted the hard version.** Tested against real data — it flagged **Anna
Salai (Mount Road)**, **Inner Ring Road**, **OMR**, and the **Chennai Bypass/Ennore Expressways**
as "implausible," all of which are genuinely some of Chennai's widest roads. Even a generous flat
70 m ceiling across all classes still caught OMR (79 m) and the two expressways. Root cause: OSM's
`road_class` tag is too unreliable in Chennai to use as a width ceiling — the same problem already
documented for EVR Periyar Salai above. A "tertiary"-tagged road can legitimately be wider than a
"primary"-tagged one.

**What's live instead:** the plausibility check is kept as a soft, informational note appended to
`width_source_detail` ("Note: this exceeds the plausible maximum for a primary road... may be a
real wide road, not necessarily wrong") — **it does not change the confidence band or map colour.**
3,496 of 6,137 measured roads carry this note; most are very likely false positives (mistagged
class), not real errors. Don't build anything that treats this note as a verdict.

**If this gets revisited:** needs a width signal that isn't derived from OSM's road_class — e.g.
an actual CMDA road inventory (see "how do we fix the reds" notes below), not a classification
hack.
