r"""Measure road right-of-way widths from building footprints.

    python -m modules.roads.pipelines.measure_widths [--city chennai] [--date YYYY-MM-DD]
                                                      [--buildings PATH]

Algorithm (per road segment):
  1. Sample points every STEP_M metres along the centreline.
  2. At each sample point, find all building polygons within SEARCH_M metres.
  3. Cast perpendicular rays (left and right of the road direction).
  4. Width at this sample = distance to nearest building face on each side.
  5. Per segment: median of valid samples (both sides found, width in 3–80 m).
     Confidence = IQR + valid-sample fraction.
  6. Requires MIN_SAMPLES valid samples; otherwise no measurement is recorded.

Measurements are stored as feature_overrides with attribute='width_m_measured'
(never overwrites 'width_m' = verified human entries).  Run apply_widths /
refresh_widths afterward to bake them into the roads layer.
"""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point

from core.layers import registry
from core.store import catalog, paths

TOPIC = "roads"
LAYER_ID = "roads"
BUILDINGS_LICENCE = "Overture Maps Foundation (CDLA Permissive 2.0)"

# Only measure widths for these road classes — residential/unclassified setbacks are too irregular.
ARTERIAL_CLASSES = {"motorway", "motorway_link", "trunk", "trunk_link",
                    "primary", "primary_link", "secondary", "secondary_link",
                    "tertiary", "tertiary_link"}

STEP_M = 15        # sample spacing along the centreline (metres)
SEARCH_M = 50      # radius to look for buildings around each sample
MIN_WIDTH_M = 3.0  # narrower than this = not a road gap (alley / misaligned building)
MAX_WIDTH_M = 80.0 # wider than this = open space / missing buildings on one side
MIN_SAMPLES = 3    # minimum valid samples to trust the measurement


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------- geometry ----------

def _sample_segment(line_utm, step: float) -> list[tuple[Point, float, float]]:
    """Return (point, dx_perp, dy_perp) samples at every `step` metres."""
    total = line_utm.length
    if total < 1.0:
        return []
    positions = (np.arange(step / 2, total, step) if total >= step
                 else np.array([total / 2]))
    samples = []
    for pos in positions:
        pt = line_utm.interpolate(pos)
        # Bearing: tangent at this point via a 1-metre look-ahead/look-back.
        before = line_utm.interpolate(max(0.0, pos - 1.0))
        after = line_utm.interpolate(min(total, pos + 1.0))
        dx_road = after.x - before.x
        dy_road = after.y - before.y
        road_len = (dx_road ** 2 + dy_road ** 2) ** 0.5
        if road_len < 1e-9:
            continue
        # Right perpendicular: rotate road direction 90° clockwise.
        dx_perp = dy_road / road_len
        dy_perp = -dx_road / road_len
        samples.append((pt, dx_perp, dy_perp))
    return samples


def _ray_min_dist(origin: Point, ray: LineString, candidate_indices, geoms) -> float | None:
    """Distance from origin to the nearest building boundary hit along ray."""
    min_d = None
    for idx in candidate_indices:
        boundary = geoms[idx].boundary
        inter = ray.intersection(boundary)
        if inter.is_empty:
            continue
        # inter may be Point, MultiPoint, or mixed GeometryCollection
        pts = [inter] if inter.geom_type == "Point" else [
            g for g in inter.geoms if g.geom_type == "Point"
        ]
        for p in pts:
            d = origin.distance(p)
            if min_d is None or d < min_d:
                min_d = d
    return min_d


def measure_segment(line_utm, tree: STRtree, geoms: list) -> dict | None:
    """Return {width_m, iqr_m, valid_samples, total_samples} or None if too few samples."""
    samples = _sample_segment(line_utm, STEP_M)
    if not samples:
        return None

    widths = []
    for pt, dx_perp, dy_perp in samples:
        # Find candidate buildings once via a circular buffer.
        buf = pt.buffer(SEARCH_M)
        candidates = list(tree.query(buf, predicate="intersects"))
        if not candidates:
            continue

        right_end = Point(pt.x + SEARCH_M * dx_perp, pt.y + SEARCH_M * dy_perp)
        left_end = Point(pt.x - SEARCH_M * dx_perp, pt.y - SEARCH_M * dy_perp)
        right_ray = LineString([pt, right_end])
        left_ray = LineString([pt, left_end])

        right_d = _ray_min_dist(pt, right_ray, candidates, geoms)
        left_d = _ray_min_dist(pt, left_ray, candidates, geoms)

        if right_d is not None and left_d is not None:
            w = right_d + left_d
            if MIN_WIDTH_M <= w <= MAX_WIDTH_M:
                widths.append(w)

    if len(widths) < MIN_SAMPLES:
        return None

    arr = np.array(widths)
    q25, q75 = np.percentile(arr, [25, 75])
    return {
        "width_m": round(float(np.median(arr)), 1),
        "iqr_m": round(float(q75 - q25), 1),
        "valid_samples": len(widths),
        "total_samples": len(samples),
    }


# ---------- pipeline ----------

def load_buildings(parquet: Path, utm_epsg: int) -> tuple[STRtree, list]:
    """Load buildings, project to UTM, return (STRtree, list of geometries)."""
    log(f"Loading buildings from {parquet.name} ...")
    # geopandas reads just the geometry column from Overture's GeoParquet efficiently.
    bdf = gpd.read_parquet(parquet, columns=["geometry"])
    log(f"Loaded {len(bdf):,} buildings; projecting to UTM {utm_epsg}...")
    bdf_utm = bdf.to_crs(utm_epsg)
    geoms_utm = list(bdf_utm.geometry)
    log("Building spatial index...")
    tree = STRtree(geoms_utm)
    return tree, geoms_utm


def run(city_id: str, buildings_parquet: Path) -> dict:
    city = registry.city_config(city_id)
    utm_epsg = city["utm_epsg"]

    # Load roads layer.
    layer = catalog.get_layer(city_id, LAYER_ID)
    if layer is None:
        raise RuntimeError(f"Roads layer not built for '{city_id}'. Run build_roads.ps1 first.")
    roads = gpd.read_parquet(layer["path"])
    arterials = roads[roads["road_class"].isin(ARTERIAL_CLASSES)].copy()
    log(f"Roads: {len(roads):,} total, {len(arterials):,} arterials to measure")

    # Project roads to UTM for measurement.
    arterials_utm = arterials.to_crs(utm_epsg)

    tree, geoms = load_buildings(buildings_parquet, utm_epsg)

    # Measure each segment.
    log("Measuring widths ...")
    results: dict[str, dict] = {}
    n = len(arterials_utm)
    for i, (_, row) in enumerate(arterials_utm.iterrows()):
        if i % 500 == 0:
            log(f"  {i:,}/{n:,} segments processed ({len(results):,} measured so far)...")
        m = measure_segment(row.geometry, tree, geoms)
        if m:
            results[row["seg_id"]] = m

    log(f"Measured {len(results):,}/{len(arterials_utm):,} arterial segments")

    # Register the buildings source in the catalog.
    source_id = f"buildings-overture-{city_id}-{buildings_parquet.parent.name}"
    catalog.register_source(
        source_id=source_id, file=buildings_parquet, city_id=city_id, topic="buildings",
        name=f"Overture Maps buildings ({city_id})",
        origin="https://overturemaps.org (via overturemaps CLI, bbox-filtered)",
        licence=BUILDINGS_LICENCE, received_at=date.today(),
    )

    # Write to feature_overrides (attribute = "width_m_measured", distinct from "width_m" verified).
    overrides: dict[str, tuple[float, str]] = {}
    for seg_id, m in results.items():
        detail_json = json.dumps({
            "source": "Overture Maps buildings (building-to-building gap)",
            "valid_samples": m["valid_samples"],
            "total_samples": m["total_samples"],
            "iqr_m": m["iqr_m"],
        })
        overrides[seg_id] = (m["width_m"], detail_json)
    catalog.replace_overrides(city_id, LAYER_ID, "width_m_measured", source_id, overrides)
    log(f"Saved {len(overrides):,} measured widths to catalog")

    # Coverage stats.
    measured_classes: dict[str, int] = {}
    for _, row in arterials[arterials["seg_id"].isin(results)].iterrows():
        measured_classes[row["road_class"]] = measured_classes.get(row["road_class"], 0) + 1
    coverage = {k: {"measured": v, "total": int((arterials["road_class"] == k).sum())}
                for k, v in sorted(measured_classes.items())}

    return {
        "arterials_total": len(arterials),
        "arterials_measured": len(results),
        "coverage_pct": round(100 * len(results) / max(len(arterials), 1), 1),
        "by_class": coverage,
        "buildings_source_id": source_id,
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", default="chennai")
    ap.add_argument("--date", default=date.today().isoformat(),
                    help="Date folder under DATA_DIR/raw/buildings/overture/ (default: today)")
    ap.add_argument("--buildings",
                    help="Explicit path to a buildings .parquet (overrides --date)")
    args = ap.parse_args(argv)

    catalog.init_data_dir()

    if args.buildings:
        parquet = Path(args.buildings)
    else:
        parquet = paths.raw_dir("buildings", "overture", args.date) / "chennai_buildings.parquet"

    if not parquet.exists():
        print(f"ERROR: buildings file not found: {parquet}", file=sys.stderr)
        print("Download first with: .venv\\Scripts\\overturemaps download --bbox=80.12,12.83,80.35,13.22"
              " -f geoparquet --type=building -r 2026-08-19.0 --no-stac -o <path>", file=sys.stderr)
        sys.exit(1)

    rep = run(args.city, parquet)
    print(json.dumps(rep, indent=2))
    log("Done. Now run: .\\scripts\\build_roads.ps1 --date <today> to bake widths into the map.")


if __name__ == "__main__":
    sys.exit(main())
