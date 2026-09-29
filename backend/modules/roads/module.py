"""Roads module: pick a road, get 2-3 standards-based cross-section designs.

M1: road details and search. M1b: links imported data to roads; width surveys -> verified widths.
Design endpoints arrive in M3. M5: set verified width from the UI.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.layers import registry
from core.rules import loader as rules_loader
from core.rules.schema import RuleError
from core.store import catalog, layers
from core.text import normalize_name
from modules.roads import hooks, linking
from modules.roads.design import engine
from modules.roads.design.demand import Demand, build_demand
from modules.roads.design.explain import explain as _explain, explain_one as _explain_one
from modules.roads.design.pdf import build_pdf

NAME = "roads"
LABEL = "Roads"
LAYER_ID = "roads"

# Used by the data inbox (core.inbox.importer): layers with `link_to: roads` are linked by
# linking.link_rows; importing into `width_surveys` upgrades widths to verified.
IMPORT_LINKERS = {"roads": linking.link_rows}
IMPORT_HOOKS = {"width_surveys": hooks.apply_width_surveys}

# Spatial radius (degrees) for nearby-context detection. ~300 m at Chennai's latitude.
_NEARBY_DEG = 0.003

# Maps layer_id -> (context_flag, emoji_label, limit)
_NEARBY_LAYERS: list[tuple[str, str, str, int]] = [
    ("schools",        "school_nearby", "school",  10),
    ("metro_stations", "metro_nearby",  "metro",    5),
]

router = APIRouter(prefix="/api/roads", tags=["roads"])


def _require_layer(city_id: str) -> dict:
    layer = catalog.get_layer(city_id, LAYER_ID)
    if layer is None:
        raise HTTPException(404, f"Roads have not been built for '{city_id}'. Run scripts\\build_roads.ps1.")
    return layer


def _nearby_context(city_id: str, seg: dict) -> tuple[set[str], list[dict]]:
    """Detect context flags from spatial data within ~300 m of the segment.

    Returns (flags, detected) where detected items carry display info for the UI and LLM.
    Never raises: a missing layer is silently skipped.
    """
    bbox = seg.get("bbox")  # [minx, miny, maxx, maxy] in EPSG:4326
    if not bbox:
        return set(), []

    r = _NEARBY_DEG
    expanded = (bbox[0] - r, bbox[1] - r, bbox[2] + r, bbox[3] + r)

    flags: set[str] = set()
    detected: list[dict] = []

    for layer_id, flag, label, limit in _NEARBY_LAYERS:
        if catalog.get_layer(city_id, layer_id) is None:
            continue
        # name_col: first string field in each layer's summary_fields
        from core.layers import registry as _reg
        defn = next((d for d in _reg.layer_defs() if d.get("layer_id") == layer_id), {})
        name_col = (defn.get("summary_fields") or [None])[0]

        result = layers.features_geojson(city_id, layer_id, expanded, limit=limit,
                                         exclude=(name_col,) if name_col is None else ())
        if not result["features"]:
            continue

        flags.add(flag)
        names: list[str] = []
        if name_col:
            names = [
                f["properties"].get(name_col, "") for f in result["features"]
                if f["properties"].get(name_col)
            ][:3]

        count = len(result["features"])
        truncated = result.get("truncated", False)
        count_str = f"{count}+" if truncated else str(count)
        detail = f"{count_str} {label}{'s' if count != 1 else ''} within ~300 m"
        if names:
            detail += f" (e.g. {', '.join(names)})"

        detected.append({
            "type": layer_id,
            "flag": flag,
            "count": count,
            "names": names,
            "detail": detail,
        })

    return flags, detected


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

    auto_flags, detected = _nearby_context(city_id, seg)
    merged_context = set(body.context) | auto_flags

    unknown = sorted(merged_context - set(engine.CONTEXT_FLAGS))
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
                           context=merged_context, demand=_demand_for(city_id, seg_id, cfg),
                           rules=rules, width_source=source, cfg=cfg)
    result["segment"] = {"seg_id": seg_id, "name": seg.get("display_name"), "road_width_m": seg["width_m"],
                         "road_width_source": seg["width_source"]}
    result["nearby"] = detected
    result["auto_context"] = sorted(auto_flags)
    return result


# ---------- explain (M4) ----------

class ExplainBody(BaseModel):
    context: list[str] = []
    row_m: float | None = None


def _design_for(city_id: str, seg_id: str, context: list[str], row_m_override: float | None) -> tuple[dict, dict]:
    """Shared helper: validate, run design, attach segment. Returns (seg, result)."""
    seg = layers.get_feature(city_id, LAYER_ID, "seg_id", seg_id)
    if seg is None:
        raise HTTPException(404, f"No road segment '{seg_id}'")

    auto_flags, detected = _nearby_context(city_id, seg)
    merged_context = set(context) | auto_flags

    unknown = sorted(merged_context - set(engine.CONTEXT_FLAGS))
    if unknown:
        raise HTTPException(422, f"Unknown context: {', '.join(unknown)}. Allowed: {', '.join(engine.CONTEXT_FLAGS)}")
    row_m, source = seg["width_m"], seg["width_source"]
    if row_m_override is not None:
        if not ROW_MIN_M <= row_m_override <= ROW_MAX_M:
            raise HTTPException(422, f"Width must be between {ROW_MIN_M:g} and {ROW_MAX_M:g} m")
        if abs(row_m_override - row_m) > 0.005:
            row_m, source = row_m_override, "manual"
    try:
        rules = rules_loader.load_all()
    except RuleError as e:
        raise HTTPException(500, f"A rule file has a problem: {e}") from e
    cfg = engine.load_config()
    result = engine.design(row_m=row_m, road_class=seg["road_class"], oneway=bool(seg["oneway"]),
                           context=merged_context, demand=_demand_for(city_id, seg_id, cfg),
                           rules=rules, width_source=source, cfg=cfg)
    result["segment"] = {"seg_id": seg_id, "name": seg.get("display_name"), "road_width_m": seg["width_m"],
                         "road_width_source": seg["width_source"]}
    result["nearby"] = detected
    result["auto_context"] = sorted(auto_flags)
    return seg, result


@router.post("/{city_id}/segments/{seg_id}/design/explain")
def explain_segment(city_id: str, seg_id: str, body: ExplainBody = ExplainBody()):
    """Run the design engine, then ask the LLM to explain each option in plain English.

    The engine result is deterministic; only the text explanations use the LLM.
    If the LLM is unavailable, the design result is returned with empty explanations
    and an explanation_warnings entry.
    """
    _require_layer(city_id)
    _, result = _design_for(city_id, seg_id, body.context, body.row_m)
    exp = _explain(result)
    return {**result, "explanations": exp["explanations"], "comparison": exp["comparison"],
            "explanation_warnings": exp["warnings"]}


@router.post("/{city_id}/segments/{seg_id}/design/explain/{option_id}")
def explain_option(city_id: str, seg_id: str, option_id: str, body: ExplainBody = ExplainBody()):
    """Explain a single design option in plain English (M8).

    Runs the design engine, then asks the LLM to explain just the requested option.
    Faster than the full /explain endpoint because only one option is sent to the LLM.
    Returns {"explanation": str, "warnings": [str]}.
    If the LLM is unavailable the explanation is empty and warnings says so.
    """
    _require_layer(city_id)
    _, result = _design_for(city_id, seg_id, body.context, body.row_m)
    available = [o["option_id"] for o in result["options"]]
    if option_id not in available:
        raise HTTPException(404, f"Option '{option_id}' not in design result. Available: {available}")
    exp = _explain_one(result, option_id)
    return {"explanation": exp["explanation"], "warnings": exp["warnings"]}


@router.get("/{city_id}/segments/{seg_id}/design/pdf")
def design_pdf(city_id: str, seg_id: str,
               row_m: float | None = Query(None),
               context: list[str] = Query(default=[])):
    """Download a PDF report for this road's design.

    Includes LLM explanations when the LLM is reachable; still generates the PDF if it is not.
    """
    from fastapi.responses import Response

    _require_layer(city_id)
    seg, result = _design_for(city_id, seg_id, list(context), row_m)
    exp = _explain(result)
    pdf_bytes = build_pdf(result, exp)
    safe_name = (seg.get("display_name") or seg_id).replace(" ", "_").replace("/", "_")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="design_{safe_name}.pdf"'},
    )


# ---------- verified width (M5) ----------

class VerifiedWidthBody(BaseModel):
    width_m: float = Field(..., ge=ROW_MIN_M, le=ROW_MAX_M)
    note: str = ""


@router.post("/{city_id}/segments/{seg_id}/width/verify")
def set_verified_width(city_id: str, seg_id: str, body: VerifiedWidthBody):
    """Save a human-verified width for this segment.

    Writes to feature_overrides so the value survives layer rebuilds.
    Triggers refresh_widths() to update the roads layer and tiles immediately.
    Returns the updated segment (width_m, width_source = 'verified', width_source_detail).
    """
    from modules.roads.pipelines.build_roads import refresh_widths

    _require_layer(city_id)
    seg = layers.get_feature(city_id, LAYER_ID, "seg_id", seg_id)
    if seg is None:
        raise HTTPException(404, f"No road segment '{seg_id}'")
    note = body.note.strip() or f"Verified manually, entered in the design panel ({body.width_m} m)"
    catalog.set_verified_width(city_id, LAYER_ID, seg_id, body.width_m, note)
    refresh_widths(city_id)
    updated = layers.get_feature(city_id, LAYER_ID, "seg_id", seg_id)
    return {
        "seg_id": seg_id,
        "width_m": updated["width_m"],
        "width_source": updated["width_source"],
        "width_source_detail": updated.get("width_source_detail"),
    }
