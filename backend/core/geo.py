"""Geometry matching helpers. All inputs must be in a metric CRS (e.g. the city's UTM zone).

The trick used throughout: instead of asking "which line is nearest to this line?" (which picks
the crossing street at an intersection), sample points ALONG the source line and let each point
vote for its nearest target. A crossing street only collects votes near the junction; the street
running along the source collects most of them.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import line_interpolate_point

DEFAULT_FRACTIONS = (0.2, 0.35, 0.5, 0.65, 0.8)


def _sample_at_fractions(lines: gpd.GeoSeries, fractions) -> gpd.GeoDataFrame:
    geoms = np.asarray(lines.values)
    pts, idx = [], []
    for f in fractions:
        pts.append(line_interpolate_point(geoms, f, normalized=True))
        idx.append(np.arange(len(geoms)))
    return gpd.GeoDataFrame(
        {"src": np.concatenate(idx)}, geometry=np.concatenate(pts), crs=lines.crs
    )


def _sample_every(lines: gpd.GeoSeries, spacing_m: float) -> gpd.GeoDataFrame:
    """Points every spacing_m along each line (at least 3: start-ish, middle, end-ish)."""
    pts, idx = [], []
    for i, g in enumerate(lines.values):
        if g is None or g.is_empty:
            continue
        n = max(3, int(g.length // spacing_m) + 1)
        dists = np.linspace(0.05, 0.95, n) * g.length
        pts.extend(g.interpolate(d) for d in dists)
        idx.extend([i] * n)
    return gpd.GeoDataFrame({"src": idx}, geometry=pts, crs=lines.crs)


def best_line_match(
    src: gpd.GeoSeries, targets: gpd.GeoDataFrame, target_id: str, *,
    max_dist_m: float = 8.0, min_share: float = 0.6, fractions=DEFAULT_FRACTIONS,
) -> pd.DataFrame:
    """For each source line, the target line that runs along it.

    Returns one row per matched source position: src (0-based position), target_id, share
    (fraction of sample points whose nearest target is this one). Sources below min_share are dropped.
    """
    pts = _sample_at_fractions(src, fractions)
    j = gpd.sjoin_nearest(pts, targets[[target_id, "geometry"]], max_distance=max_dist_m, how="inner")
    # One vote per sample point (ties at equal distance: keep the first).
    j = j[~j.index.duplicated(keep="first")]
    votes = j.groupby(["src", target_id]).size().rename("votes").reset_index()
    votes["share"] = votes["votes"] / len(fractions)
    best = votes.sort_values(["src", "votes"], ascending=[True, False]).drop_duplicates("src")
    return best[best["share"] >= min_share][["src", target_id, "share"]].reset_index(drop=True)


def lines_to_segments(
    src: gpd.GeoSeries, segments: gpd.GeoDataFrame, seg_id: str, *,
    max_dist_m: float = 12.0, spacing_m: float = 10.0, min_votes: int = 2,
) -> pd.DataFrame:
    """For each source line (e.g. an imported KML road), ALL segments it runs along.

    Returns src, seg_ids (list, most votes first), share (fraction of samples that found any segment).
    """
    pts = _sample_every(src, spacing_m)
    total = pts.groupby("src").size()
    j = gpd.sjoin_nearest(pts, segments[[seg_id, "geometry"]], max_distance=max_dist_m, how="inner")
    j = j[~j.index.duplicated(keep="first")]
    votes = j.groupby(["src", seg_id]).size().rename("votes").reset_index()
    rows = []
    for s, grp in votes.groupby("src"):
        need = min_votes if total[s] > min_votes else 1
        keep = grp[grp["votes"] >= need].sort_values("votes", ascending=False)
        if len(keep):
            rows.append({"src": s, "seg_ids": keep[seg_id].tolist(),
                         "share": float(keep["votes"].sum() / total[s])})
    return pd.DataFrame(rows, columns=["src", "seg_ids", "share"])


def points_to_segments(
    src: gpd.GeoSeries, segments: gpd.GeoDataFrame, seg_id: str, *, max_dist_m: float = 30.0,
) -> pd.DataFrame:
    """Nearest segment for each point, within max_dist_m. Returns src, seg_id, distance_m."""
    pts = gpd.GeoDataFrame({"src": np.arange(len(src))}, geometry=src.values, crs=src.crs)
    j = gpd.sjoin_nearest(pts, segments[[seg_id, "geometry"]], max_distance=max_dist_m,
                          how="inner", distance_col="distance_m")
    j = j[~j.index.duplicated(keep="first")]
    return j[["src", seg_id, "distance_m"]].reset_index(drop=True)


def polygons_to_segments(src: gpd.GeoSeries, segments: gpd.GeoDataFrame, seg_id: str) -> pd.DataFrame:
    """Segments intersecting each polygon (e.g. a waterlogging zone). Returns src, seg_ids."""
    polys = gpd.GeoDataFrame({"src": np.arange(len(src))}, geometry=src.values, crs=src.crs)
    j = gpd.sjoin(segments[[seg_id, "geometry"]], polys, predicate="intersects", how="inner")
    out = j.groupby("src")[seg_id].apply(list).rename("seg_ids").reset_index()
    return out
