"""Road names: OSM name + official (e.g. Greater Chennai Corporation) name, side by side.

Neither overwrites the other. display_name is what the map and search use: the OSM name if there
is one, otherwise the official name. name_match records how the two compare.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

from core import geo
from core.text import compare_names, normalize_name

MATCH_LABEL = {"only_a": "osm_only", "only_b": "official_only"}  # compare_names -> our wording


def read_official_lines(path: Path, name_field: str, id_field: str) -> gpd.GeoDataFrame:
    """Official centerline file -> one row per simple line, with name + id."""
    g = gpd.read_file(path)
    g = g[[id_field, name_field, "geometry"]].rename(columns={id_field: "official_id", name_field: "official_name"})
    g["official_id"] = g["official_id"].astype("string").str.strip()
    g["official_name"] = g["official_name"].astype("string").str.strip().replace("", pd.NA)
    g = g.explode(index_parts=False)
    g = g[g.geom_type == "LineString"].reset_index(drop=True)
    g["oidx"] = range(len(g))
    return g


def add_official_names(seg: gpd.GeoDataFrame, official: gpd.GeoDataFrame | None, utm_epsg: int) -> tuple[gpd.GeoDataFrame, dict]:
    seg = seg.copy()
    seg["name_official"] = pd.Series([None] * len(seg), dtype="object")
    seg["official_road_id"] = pd.Series([None] * len(seg), dtype="object")
    if official is not None and len(official):
        m = geo.best_line_match(
            seg.geometry.to_crs(utm_epsg), official.to_crs(utm_epsg), "oidx",
            max_dist_m=8.0, min_share=0.6,
        )
        lookup = official.set_index("oidx")
        pos = m["src"].to_numpy()
        seg.iloc[pos, seg.columns.get_loc("name_official")] = lookup.loc[m["oidx"], "official_name"].astype(object).to_numpy()
        seg.iloc[pos, seg.columns.get_loc("official_road_id")] = lookup.loc[m["oidx"], "official_id"].astype(object).to_numpy()
        seg["name_official"] = seg["name_official"].where(seg["name_official"].notna(), None)

    seg["name_match"] = [MATCH_LABEL.get(c, c) for c in map(compare_names, seg["name"], seg["name_official"])]
    seg["display_name"] = seg["name"].where(seg["name"].notna(), seg["name_official"])
    seg["display_name_source"] = [
        "osm" if isinstance(n, str) else ("official" if isinstance(o, str) else None)
        for n, o in zip(seg["name"], seg["name_official"])
    ]
    seg["search_key"] = [
        " | ".join(k for k in (normalize_name(n), normalize_name(o)) if k) or None
        for n, o in zip(seg["name"], seg["name_official"])
    ]
    stats = {
        "named_osm_share": round(seg["name"].notna().mean(), 3),
        "named_any_share": round(seg["display_name"].notna().mean(), 3),
        "name_match_counts": seg["name_match"].value_counts().to_dict(),
    }
    return seg, stats
