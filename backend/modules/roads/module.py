"""Roads module: pick a road, get 2-3 standards-based cross-section designs.

M1: road details and search. M1b: links imported data to roads; width surveys -> verified widths.
Design endpoints arrive in M3.
"""
from fastapi import APIRouter, HTTPException, Query

from core.layers import registry
from core.store import catalog, layers
from core.text import normalize_name
from modules.roads import hooks, linking

NAME = "roads"
LABEL = "Roads"
LAYER_ID = "roads"

# Used by the data inbox (core.inbox.importer): layers with `link_to: roads` are linked by
# linking.link_rows; importing into `width_surveys` upgrades widths to verified.
IMPORT_LINKERS = {"roads": linking.link_rows}
IMPORT_HOOKS = {"width_surveys": hooks.apply_width_surveys}

router = APIRouter(prefix="/api/roads", tags=["roads"])


def _require_layer(city_id: str) -> dict:
    layer = catalog.get_layer(city_id, LAYER_ID)
    if layer is None:
        raise HTTPException(404, f"Roads have not been built for '{city_id}'. Run scripts\\build_roads.ps1.")
    return layer


def _linked_data(city_id: str, seg_id: str) -> list[dict]:
    """Records from imported layers (traffic counts, surveys, ...) linked to this segment."""
    out = []
    for d in registry.import_layer_defs():
        if d.get("link_to") != "roads" or catalog.get_layer(city_id, d["layer_id"]) is None:
            continue
        rows = layers.rows_linked_to(city_id, d["layer_id"], seg_id)
        if rows:
            fields = d.get("fields", {})
            out.append({
                "layer_id": d["layer_id"], "label": d["label"], "color": d.get("color"),
                "summary_fields": [{"field": f, "label": fields.get(f, {}).get("label", f)}
                                   for f in d.get("summary_fields", [])],
                "rows": rows,
            })
    return out


@router.get("/{city_id}/segments/{seg_id}")
def segment(city_id: str, seg_id: str):
    layer = _require_layer(city_id)
    seg = layers.get_feature(city_id, LAYER_ID, "seg_id", seg_id)
    if seg is None:
        raise HTTPException(404, f"No road segment '{seg_id}'")
    road = None
    if seg.get("display_name"):
        s = layers.group_stats(city_id, LAYER_ID, "display_name", seg["display_name"], "length_m")
        road = {"name": seg["display_name"], "segments": s["count"], "length_m": round(s["sum"], 1), "bbox": s["bbox"]}
    osm = next((s for s in layer["sources"] if s["source_id"].startswith("osm-")), None)
    official_cfg = registry.city_config(city_id).get("official_road_names") or {}
    official = next((s for s in layer["sources"]
                     if official_cfg and s["source_id"].startswith(official_cfg["source_prefix"])), None)
    return {
        "segment": seg,
        "road": road,
        "geometry_source": osm and {"name": "OpenStreetMap", "licence": osm["licence"], "downloaded": osm["received_at"]},
        "official_name_source": official and {"name": official_cfg["label"], "licence": official["licence"],
                                              "received": official["received_at"]},
        "linked_data": _linked_data(city_id, seg_id),
    }


@router.get("/{city_id}/streets")
def streets(city_id: str, name: str = Query(min_length=2)):
    """Physically separate streets for a name, each with its segment ids. Used to fix unmatched
    import rows: '1st Street' returns each 1st Street separately so a person can pick the right one."""
    _require_layer(city_id)
    roads = linking.load_roads(city_id)
    res = linking.match_name(roads, name)
    if res["status"] == "matched":
        keep = ("road_name", "seg_ids", "length_m", "lon", "lat")
        return {"status": "matched", "note": res.get("note"), "streets": [{k: res[k] for k in keep}]}
    return {"status": res["status"], "note": res["reason"], "streets": res["candidates"]}


@router.get("/{city_id}/search")
def search(city_id: str, q: str = Query(min_length=2), limit: int = Query(20, le=50)):
    _require_layer(city_id)
    pattern = normalize_name(q.strip())
    if not pattern:
        return []
    rows = layers.search_text(city_id, LAYER_ID, "display_name", pattern, match_col="search_key",
                              sum_col="length_m", label_cols=("road_class",), limit=limit)
    return [
        {"name": r["value"], "segments": r["count"], "length_m": round(r["total"], 1),
         "road_class": r["road_class"], "bbox": r["bbox"]}
        for r in rows
    ]
