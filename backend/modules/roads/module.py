"""Roads module: pick a road, get 2-3 standards-based cross-section designs.

M1: road details and search. Design endpoints arrive in M3.
"""
from fastapi import APIRouter, HTTPException, Query

from core.store import catalog, layers

NAME = "roads"
LABEL = "Roads"
LAYER_ID = "roads"

router = APIRouter(prefix="/api/roads", tags=["roads"])


def _require_layer(city_id: str) -> dict:
    layer = catalog.get_layer(city_id, LAYER_ID)
    if layer is None:
        raise HTTPException(404, f"Roads have not been built for '{city_id}'. Run scripts\\build_roads.ps1.")
    return layer


@router.get("/{city_id}/segments/{seg_id}")
def segment(city_id: str, seg_id: str):
    layer = _require_layer(city_id)
    seg = layers.get_feature(city_id, LAYER_ID, "seg_id", seg_id)
    if seg is None:
        raise HTTPException(404, f"No road segment '{seg_id}'")
    road = None
    if seg.get("name"):
        s = layers.group_stats(city_id, LAYER_ID, "name", seg["name"], "length_m")
        road = {"name": seg["name"], "segments": s["count"], "length_m": round(s["sum"], 1), "bbox": s["bbox"]}
    first = layer["sources"][0] if layer["sources"] else None
    return {
        "segment": seg,
        "road": road,
        "geometry_source": first and {
            "name": "OpenStreetMap", "licence": first["licence"], "downloaded": first["received_at"],
        },
    }


@router.get("/{city_id}/search")
def search(city_id: str, q: str = Query(min_length=2), limit: int = Query(20, le=50)):
    _require_layer(city_id)
    rows = layers.search_text(city_id, LAYER_ID, "name", q.strip(), sum_col="length_m",
                              label_cols=("road_class",), limit=limit)
    return [
        {"name": r["value"], "segments": r["count"], "length_m": round(r["total"], 1),
         "road_class": r["road_class"], "bbox": r["bbox"]}
        for r in rows
    ]
