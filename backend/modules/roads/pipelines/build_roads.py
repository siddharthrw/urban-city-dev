r"""Build the roads layer for a city from OpenStreetMap.

    python -m modules.roads.pipelines.build_roads --city chennai [--date YYYY-MM-DD]

Steps: download (or reuse) the raw OSM data -> cut into intersection-to-intersection segments
-> length in UTM metres -> widths (verified > measured > estimated) -> GeoParquet -> PMTiles
-> register everything in the catalog.

Re-runnable. The raw download for a date lives in DATA_DIR\raw\roads\osm\<date>\ and is reused
if present, so re-running with the same --date rebuilds without downloading again.
"""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from pyproj import Geod

from core.layers import registry
from core.store import catalog, layers, paths, tiles
from modules.roads import widths

ROAD_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary",
                "unclassified", "residential", "living_street"]
LINK_CLASSES = [f"{c}_link" for c in ["motorway", "trunk", "primary", "secondary", "tertiary"]]
CLASS_RANK = {c: i for i, c in enumerate(ROAD_CLASSES[:5] + LINK_CLASSES + ROAD_CLASSES[5:])}
OSM_FILTER = (
    '["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street)'
    '(_link)?$"]'
)
LICENCE = "ODbL 1.0 (OpenStreetMap contributors)"
LAYER_ID = "roads"
TOPIC = "roads"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------- download ----------

def download(city: dict, raw: Path):
    """Fetch the boundary and road network. osmnx's cache folder IS the raw archive for this date,
    so a second run for the same date reads from disk instead of Overpass."""
    raw.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(raw / "overpass")
    ox.settings.useful_tags_way = sorted(set(ox.settings.useful_tags_way) | {"sidewalk", "ref", "name:en"})

    boundary_file = raw / "boundary.geojson"
    if boundary_file.exists():
        boundary = gpd.read_file(boundary_file)
    else:
        boundary = ox.geocode_to_gdf(city["osm_boundary_id"], by_osmid=True)
        boundary.to_file(boundary_file, driver="GeoJSON")
    poly = boundary.geometry.iloc[0]

    log("Fetching road network (cached per date)...")
    G = ox.graph_from_polygon(poly, custom_filter=OSM_FILTER, simplify=True,
                              retain_all=True, truncate_by_edge=True)
    return G, boundary_file


def register_raw(city_id: str, raw: Path, day: date) -> list[str]:
    ids = []
    files = [raw / "boundary.geojson"] + sorted((raw / "overpass").glob("*.json"))
    for f in files:
        sid = f"osm-{city_id}-roads-{day.isoformat()}-{f.stem[:12]}"
        catalog.register_source(
            source_id=sid, file=f, city_id=city_id, topic=TOPIC,
            name=f"OSM {'boundary' if f.name == 'boundary.geojson' else 'Overpass response'} ({city_id})",
            origin="https://overpass-api.de / https://nominatim.openstreetmap.org (via osmnx)",
            licence=LICENCE, received_at=day,
        )
        ids.append(sid)
    return ids


# ---------- clean ----------

def _first(v):
    if isinstance(v, list):
        v = [x for x in v if isinstance(x, str) and x.strip()]
        return v[0] if v else None
    return v if isinstance(v, str) and v.strip() else None


def _best_class(v) -> str:
    vals = v if isinstance(v, list) else [v]
    return min(vals, key=lambda c: CLASS_RANK.get(c, 99))


def _lanes(v) -> int | None:
    vals = v if isinstance(v, list) else [v]
    nums = []
    for x in vals:
        try:
            f = float(str(x).strip())
        except (TypeError, ValueError):
            continue
        if f.is_integer() and f > 0:
            nums.append(int(f))
    return max(nums) if nums else None


def _raw_str(v) -> str | None:
    if isinstance(v, list):
        v = [str(x) for x in v if x is not None and str(x) != "nan"]
        return ";".join(v) if v else None
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def _as_bool(v) -> bool:
    vals = v if isinstance(v, list) else [v]
    return any(x is True or str(x).lower() in ("true", "yes", "1") for x in vals)


def to_segments(G, city: dict) -> gpd.GeoDataFrame:
    Gu = ox.convert.to_undirected(G)
    e = ox.graph_to_gdfs(Gu, nodes=False).reset_index()
    col = lambda name: e[name] if name in e.columns else pd.Series([None] * len(e))

    seg = gpd.GeoDataFrame(
        {
            "city_id": city["city_id"],
            "seg_id": [f"{min(u, v)}-{max(u, v)}-{k}" for u, v, k in zip(e["u"], e["v"], e["key"])],
            "osm_way_ids": [[int(x) for x in (o if isinstance(o, list) else [o])] for o in e["osmid"]],
            "name": [_first(x) for x in col("name")],
            "ref": [_first(x) for x in col("ref")],
            "road_class": [_best_class(x) for x in e["highway"]],
            "oneway": [_as_bool(x) for x in col("oneway")],
            "lanes_osm": pd.array([_lanes(x) for x in col("lanes")], dtype="Int64"),
            "osm_width_hint": [_raw_str(x) for x in col("width")],
            "sidewalk_osm": [_raw_str(x) for x in col("sidewalk")],
        },
        geometry=e.geometry.values,
        crs=e.crs,
    ).to_crs(4326)

    if not seg["seg_id"].is_unique:
        dups = seg["seg_id"][seg["seg_id"].duplicated()].head().tolist()
        raise RuntimeError(f"seg_id not unique, e.g. {dups}")

    # Length in metres, in the city's UTM zone.
    seg["length_m"] = seg.to_crs(city["utm_epsg"]).length.round(2)
    return seg


def apply_widths(seg: gpd.GeoDataFrame, city_id: str) -> gpd.GeoDataFrame:
    defaults = widths.load_defaults()
    overrides = catalog.get_overrides(city_id, LAYER_ID, "width_m")
    out_w, out_src, out_det = [], [], []
    for sid, cls, lanes, oneway in zip(seg["seg_id"], seg["road_class"], seg["lanes_osm"], seg["oneway"]):
        est = widths.estimate(cls, None if pd.isna(lanes) else int(lanes), bool(oneway), defaults)
        ver = None
        if sid in overrides:
            o = overrides[sid]
            ver = widths.Width(o["value"], "verified", o["detail"] or "Verified (manual entry)")
        w = widths.resolve(est, verified=ver)
        out_w.append(w.width_m)
        out_src.append(w.source)
        out_det.append(w.detail)
    seg["width_m"] = out_w
    seg["width_source"] = out_src
    seg["width_source_detail"] = out_det
    return seg


# ---------- report ----------

def report(seg: gpd.GeoDataFrame) -> dict:
    n = len(seg)
    ways = {w for ids in seg["osm_way_ids"] for w in ids}
    # Sanity check: UTM length vs exact WGS84 ellipsoidal length. Expect ~0.03% median
    # (UTM scale factor near the zone edge); the max is dominated by cm-rounding on tiny segments.
    geod = Geod(ellps="WGS84")
    ell = np.array([geod.geometry_length(g) for g in seg.geometry])
    rel = np.abs(seg["length_m"].to_numpy() - ell) / np.clip(ell, 1, None)
    return {
        "segments": n,
        "osm_ways": len(ways),
        "total_km": round(seg["length_m"].sum() / 1000, 1),
        "named_share": round(seg["name"].notna().mean(), 3),
        "lanes_share": round(seg["lanes_osm"].notna().mean(), 3),
        "osm_width_share": round(seg["osm_width_hint"].notna().mean(), 4),
        "sidewalk_share": round(seg["sidewalk_osm"].notna().mean(), 4),
        "width_source_counts": seg["width_source"].value_counts().to_dict(),
        "by_class": seg["road_class"].value_counts().to_dict(),
        "length_check_vs_ellipsoid_median_rel_diff": round(float(np.median(rel)), 6),
        "length_check_vs_ellipsoid_max_rel_diff": round(float(rel.max()), 5),
    }


# ---------- main ----------

def build(city_id: str, day: date) -> dict:
    city = registry.city_config(city_id)
    ldef = registry.layer_def(LAYER_ID)
    raw = paths.raw_dir(TOPIC, "osm", day.isoformat())

    G, _ = download(city, raw)
    source_ids = register_raw(city_id, raw, day)
    log(f"Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} directed edges")

    seg = apply_widths(to_segments(G, city), city_id)
    rep = report(seg)
    log(f"Segments: {rep['segments']:,} from {rep['osm_ways']:,} OSM ways, {rep['total_km']:,} km")

    out = paths.layer_path(city_id, TOPIC, LAYER_ID)
    layers.write_geoparquet(seg, out)
    catalog.record_layer(
        city_id=city_id, layer_id=LAYER_ID, topic=TOPIC, file=out,
        geometry_type=ldef["geometry_type"], feature_count=len(seg),
        build_script=ldef["build_script"], source_ids=source_ids,
    )

    log("Building vector tiles...")
    t = ldef["tiles"]
    tinfo = tiles.build_pmtiles(
        parquet=out, out=paths.tiles_path(city_id, TOPIC, LAYER_ID), layer_name=LAYER_ID,
        properties=t["properties"], minzoom=t["minzoom"], maxzoom=t["maxzoom"],
        zoom_filter={int(k): v for k, v in t["zoom_filter"].items()},
    )
    rep["tiles"] = tinfo
    rep["raw_date"] = day.isoformat()
    (paths.city_topic_dir(city_id, TOPIC) / "roads_build_report.json").write_text(
        json.dumps(rep, indent=2, default=str), encoding="utf-8")
    log(f"Tiles: {tinfo['tiles']:,} tiles, {tinfo['bytes'] / 1e6:.1f} MB")
    return rep


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", default="chennai")
    ap.add_argument("--date", type=date.fromisoformat, default=date.today(),
                    help="Raw download date folder to use/create (default: today)")
    args = ap.parse_args(argv)
    catalog.init_data_dir()
    rep = build(args.city, args.date)
    print(json.dumps(rep, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main())
