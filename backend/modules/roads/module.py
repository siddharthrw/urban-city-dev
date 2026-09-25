"""Roads module: pick a road, get 2-3 standards-based cross-section designs.

M1: road details and search. M1b: links imported data to roads; width surveys -> verified widths.
Design endpoints arrive in M3.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.layers import registry
from core.rules import loader as rules_loader
from core.rules.schema import RuleError
from core.store import catalog, layers
from core.text import normalize_name
from modules.roads import hooks, linking
from modules.roads.design import engine
from modules.roads.design.demand import Demand, build_demand

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


# ---------- design (M3) ----------

ROW_MIN_M, ROW_MAX_M = 3.0, 150.0


class DesignBody(BaseModel):
    context: list[str] = []
    row_m: float | None = None  # what-if width; default is the road's own width


def _demand_for(city_id: str, seg_id: str, cfg: dict) -> Demand:
    def rows(layer_id: str) -> list[dict]:
        return layers.rows_linked_to(city_id, layer_id, seg_id, limit=200) if catalog.get_layer(city_id, layer_id) else []
    return build_demand(rows("traffic_counts"), rows("footfall"), rows("bus_stops"), cfg["pcu_factors"])


@router.post("/{city_id}/segments/{seg_id}/design")
def design_segment(city_id: str, seg_id: str, body: DesignBody = DesignBody()):
    """2-3 standards-based layouts for this segment. The engine (not an LLM) does all the arithmetic."""
    _require_layer(city_id)
    seg = layers.get_feature(city_id, LAYER_ID, "seg_id", seg_id)
    if seg is None:
        raise HTTPException(404, f"No road segment '{seg_id}'")
    unknown = sorted(set(body.context) - set(engine.CONTEXT_FLAGS))
    if unknown:
        raise HTTPException(422, f"Unknown context: {', '.join(unknown)}. Allowed: {', '.join(engine.CONTEXT_FLAGS)}")
    row_m, source = seg["width_m"], seg["width_source"]
    if body.row_m is not None:
        if not ROW_MIN_M <= body.row_m <= ROW_MAX_M:
            raise HTTPException(422, f"Width must be between {ROW_MIN_M:g} and {ROW_MAX_M:g} m")
        if abs(body.row_m - row_m) > 0.005:
            row_m, source = body.row_m, "manual"
    try:
        rules = rules_loader.load_all()
    except RuleError as e:
        raise HTTPException(500, f"A rule file has a problem: {e}") from e
    cfg = engine.load_config()
    result = engine.design(row_m=row_m, road_class=seg["road_class"], oneway=bool(seg["oneway"]),
                           context=set(body.context), demand=_demand_for(city_id, seg_id, cfg),
                           rules=rules, width_source=source, cfg=cfg)
    result["segment"] = {"seg_id": seg_id, "name": seg.get("display_name"), "road_width_m": seg["width_m"],
                         "road_width_source": seg["width_source"]}
    return result
