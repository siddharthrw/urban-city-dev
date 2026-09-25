"""What happens to the roads layer when certain layers are imported.

width_surveys -> every linked segment gets a VERIFIED width (feature_overrides), then the roads
layer's widths and tiles are refreshed. Removing the import removes its verified widths again.
"""
import statistics

import geopandas as gpd

from core.store import catalog
from modules.roads.pipelines import build_roads


def apply_width_surveys(city_id: str, import_id: str, rows: gpd.GeoDataFrame | None, source_name: str) -> dict:
    values: dict[str, tuple[float, str]] = {}
    if rows is not None and len(rows):
        per_seg: dict[str, list] = {}
        for r in rows.itertuples():
            for sid in (r.seg_ids or []):
                per_seg.setdefault(sid, []).append(r)
        for sid, rs in per_seg.items():
            w = round(statistics.median(float(r.width_m) for r in rs), 2)
            first = rs[0]
            when = getattr(first, "survey_date", None)
            by = getattr(first, "surveyed_by", None)
            detail = (f"Verified from survey: {source_name}, row {first.row_no}"
                      + (f", {when}" if when else "") + (f", by {by}" if by else "")
                      + (f" (median of {len(rs)} rows)" if len(rs) > 1 else "") + ".")
            values[sid] = (w, detail)
    catalog.replace_overrides(city_id, "roads", "width_m", import_id, values)
    refreshed = build_roads.refresh_widths(city_id)
    return {"verified_segments": len(values), "roads_widths": refreshed["width_source_counts"]}
