"""Link imported rows (a traffic count, a bus stop, a survey) to road segments.

By location when the row has one:
  point    -> nearest segment within 30 m
  line     -> every segment it runs along (sample-and-vote, see core.geo)
  polygon  -> every segment inside/crossing it
By name when it doesn't: the row's road name vs. OSM + official names (normalised, then fuzzy).
A name used by several separate streets ("1st Street") is NOT guessed: the row is listed as
unmatched with the candidates, for a person to pick.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from rapidfuzz import fuzz, process
from shapely.ops import unary_union

from core import geo
from core.layers import registry
from core.store import catalog
from core.text import is_distinctive, normalize_name

POINT_MAX_M = 30.0
FUZZY_MIN = 90
SEPARATE_STREETS_GAP_M = 150.0  # segments further apart than this are different streets
DOMINANT_FACTOR = 5.0  # a street this many times longer than any namesake is "the" street


@dataclass
class Roads:
    segs: gpd.GeoDataFrame        # UTM, columns: seg_id, display_name, name, name_official, geometry
    by_key: dict[str, list[int]]  # normalised name -> segment positions
    keys: list[str]
    utm: int


@lru_cache(maxsize=4)
def _load(path: str, mtime: float, utm: int) -> Roads:
    g = gpd.read_parquet(path, columns=["seg_id", "display_name", "name", "name_official", "geometry"])
    g = g.to_crs(utm).reset_index(drop=True)
    by_key: dict[str, list[int]] = {}
    for i, (n, o) in enumerate(zip(g["name"], g["name_official"])):
        for k in {normalize_name(n) if isinstance(n, str) else "", normalize_name(o) if isinstance(o, str) else ""}:
            if k:
                by_key.setdefault(k, []).append(i)
    return Roads(g, by_key, list(by_key), utm)


def load_roads(city_id: str) -> Roads | None:
    layer = catalog.get_layer(city_id, "roads")
    if layer is None:
        return None
    p: Path = layer["path"]
    return _load(str(p), p.stat().st_mtime, registry.city_config(city_id)["utm_epsg"])


def _groups(roads: Roads, positions: list[int]) -> list[list[int]]:
    """Split segments into physically separate streets (clusters more than 150 m apart)."""
    geoms = roads.segs.geometry.iloc[positions]
    blobs = unary_union(geoms.buffer(SEPARATE_STREETS_GAP_M / 2).values)
    parts = list(getattr(blobs, "geoms", [blobs]))
    if len(parts) == 1:
        return [positions]
    out = [[] for _ in parts]
    for pos, g in zip(positions, geoms):
        for k, part in enumerate(parts):
            if part.intersects(g):
                out[k].append(pos)
                break
    return [grp for grp in out if grp]


def _describe(roads: Roads, grp: list[int]) -> dict:
    seg = roads.segs.iloc[grp]
    c = gpd.GeoSeries([unary_union(seg.geometry.values).centroid], crs=roads.utm).to_crs(4326).iloc[0]
    names = seg["display_name"].dropna()
    return {"road_name": names.mode().iloc[0] if len(names) else None,
            "seg_ids": seg["seg_id"].tolist(), "length_m": round(float(seg.length.sum()), 1),
            "lon": round(c.x, 6), "lat": round(c.y, 6)}


def match_name(roads: Roads, name: str) -> dict:
    """{status: matched|ambiguous|not_found, ...}."""
    key = normalize_name(name)
    if not key:
        return {"status": "not_found", "reason": "empty road name", "candidates": []}
    positions = roads.by_key.get(key)
    method, score = "name", 100.0
    if positions is None:
        best = process.extract(key, roads.keys, scorer=fuzz.ratio, limit=5)
        good = [b for b in best if b[1] >= FUZZY_MIN]
        if good and is_distinctive(key) and (len(good) == 1 or good[0][1] - good[1][1] >= 3):
            positions, score, method = roads.by_key[good[0][0]], good[0][1], "name_fuzzy"
        else:
            cands = [_describe(roads, roads.by_key[b[0]]) | {"score": round(b[1])} for b in best[:3] if b[1] >= 70]
            return {"status": "not_found", "reason": f"no road named '{name}'", "candidates": cands}
    groups = _groups(roads, positions)
    note = None
    if len(groups) > 1:
        cands = sorted((_describe(roads, g) for g in groups), key=lambda c: -c["length_m"])
        # One long main road plus a few short namesakes: take the main road, but say so.
        if is_distinctive(key) and cands[0]["length_m"] >= DOMINANT_FACTOR * cands[1]["length_m"]:
            note = (f"{len(groups) - 1} much shorter street(s) share this name; "
                    f"linked to the main one ({cands[0]['length_m'] / 1000:.1f} km).")
            return {"status": "matched", "method": method, "score": round(score), "note": note, **cands[0]}
        return {"status": "ambiguous", "candidates": cands[:8],
                "reason": f"'{name}' is the name of {len(groups)} separate streets; pick one"}
    d = _describe(roads, groups[0])
    return {"status": "matched", "method": method, "score": round(score), "note": note, **d}


def link_rows(city_id: str, gdf: gpd.GeoDataFrame, road_names: pd.Series | None,
              manual: dict[int, dict]) -> pd.DataFrame:
    """One output row per input row (same order): link_method, seg_ids, road_name_matched,
    link_distance_m, link_note, candidates, road_geometry (EPSG:4326, for name/manual links)."""
    roads = load_roads(city_id)
    n = len(gdf)
    out = pd.DataFrame({
        "link_method": [None] * n, "seg_ids": [[] for _ in range(n)], "road_name_matched": [None] * n,
        "link_distance_m": [None] * n, "link_note": [None] * n, "candidates": [None] * n,
        "road_geometry": [None] * n,
    })
    if roads is None:
        out["link_note"] = "Roads layer not built; rows were not linked."
        return out
    segs = roads.segs
    seg_pos = {s: i for i, s in enumerate(segs["seg_id"])}

    geom = gdf.geometry.to_crs(roads.utm) if gdf.crs else gdf.geometry
    has = geom.notna() & ~geom.is_empty
    kinds = geom.geom_type.where(has)

    def road_geom(seg_ids):
        g = unary_union(segs.geometry.iloc[[seg_pos[s] for s in seg_ids if s in seg_pos]].values)
        return gpd.GeoSeries([g], crs=roads.utm).to_crs(4326).iloc[0]

    pts = kinds.isin(["Point"])
    if pts.any():
        idx = pts[pts].index
        m = geo.points_to_segments(geom[idx], segs, "seg_id", max_dist_m=POINT_MAX_M)
        for src, sid, d in m.itertuples(index=False):
            r = idx[src]
            out.at[r, "seg_ids"], out.at[r, "link_distance_m"] = [sid], round(float(d), 1)
    lines = kinds.isin(["LineString", "MultiLineString"])
    if lines.any():
        idx = lines[lines].index
        m = geo.lines_to_segments(geom[idx], segs, "seg_id")
        for src, sids, share in m.itertuples(index=False):
            out.at[idx[src], "seg_ids"] = sids
    polys = kinds.isin(["Polygon", "MultiPolygon"])
    if polys.any():
        idx = polys[polys].index
        m = geo.polygons_to_segments(geom[idx], segs, "seg_id")
        for src, sids in m.itertuples(index=False):
            out.at[idx[src], "seg_ids"] = sids
    for r in has[has].index:
        out.at[r, "link_method"] = "location"
        if not out.at[r, "seg_ids"]:
            out.at[r, "link_note"] = f"No road within {POINT_MAX_M:.0f} m of this location."

    if road_names is not None:
        for r in has[~has].index:
            name = road_names.iloc[r] if r < len(road_names) else None
            if not isinstance(name, str) or not name.strip():
                out.at[r, "link_note"] = "No location and no road name."
                continue
            res = match_name(roads, name)
            if res["status"] == "matched":
                out.at[r, "link_method"] = res["method"]
                out.at[r, "seg_ids"] = res["seg_ids"]
                out.at[r, "road_name_matched"] = res["road_name"]
                out.at[r, "road_geometry"] = road_geom(res["seg_ids"])
                notes = [res.get("note")]
                if res["method"] == "name_fuzzy":
                    notes.insert(0, f"Spelling differs; matched '{res['road_name']}' ({res['score']}%).")
                out.at[r, "link_note"] = " ".join(n for n in notes if n) or None
            else:
                out.at[r, "link_note"] = res["reason"]
                out.at[r, "candidates"] = res["candidates"]

    for i, row_no in enumerate(gdf["row_no"]):
        fix = manual.get(int(row_no))
        if fix and fix["seg_ids"]:
            out.at[i, "link_method"] = "manual"
            out.at[i, "seg_ids"] = fix["seg_ids"]
            out.at[i, "road_name_matched"] = fix.get("road_name")
            out.at[i, "link_note"] = "Linked by hand."
            out.at[i, "candidates"] = None
            if not has.iloc[i]:
                out.at[i, "road_geometry"] = road_geom(fix["seg_ids"])
    # Name labels for location links too.
    for i in range(n):
        if out.at[i, "seg_ids"] and out.at[i, "road_name_matched"] is None:
            names = segs["display_name"].iloc[[seg_pos[s] for s in out.at[i, "seg_ids"] if s in seg_pos]].dropna()
            out.at[i, "road_name_matched"] = names.mode().iloc[0] if len(names) else None
    return out
