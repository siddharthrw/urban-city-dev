"""Sample traffic-impact estimate: before vs after travel time for a design option (M17).

Not a traffic simulation. There is no SUMO run and no real traffic count behind these numbers:
this only answers "if a typical road of this class carried a representative volume, how would
travel time on this stretch change between the current layout and a redesign option" — using an
assumed SAMPLE demand volume and the standard BPR congestion curve. Everything returned here is
labelled sample_data: True and must be shown as a labelled estimate, never as a measurement or a
simulation result. Pure function, no I/O, like engine.py.
"""
from modules.roads.design.engine import cm

LANE_WIDTH_M = 3.0  # assumed width of one existing traffic lane, used only to infer today's lane
                     # count from the current carriageway's total width (there is no survey of
                     # today's lane markings — see engine.current_state)
MAX_INFERRED_LANES = 10  # sanity cap: a wide undivided carriageway should not imply absurd lane counts


def _free_flow_kmh(road_class: str, cfg: dict) -> float:
    table = cfg["free_flow_kmh"]
    return table.get(road_class, table["unclassified"])


def sample_demand_pcu(road_class: str, cfg: dict) -> tuple[float, str]:
    """A representative peak-hour PCU volume for this road class. SAMPLE DATA, not a real count."""
    cls = cfg["classes"].get(road_class, cfg["classes"]["unclassified"])
    dir_lanes = cls["dir_default"]
    load = cfg["sample_demand_load_factor"]
    pcu = dir_lanes * cfg["lane_capacity_pcu_per_hour"] * load
    detail = (f"Sample demand: assumed {load:.0%} of a typical {road_class.replace('_', ' ')} road's "
              f"capacity ({dir_lanes} lane(s)/direction x {cfg['lane_capacity_pcu_per_hour']:,} "
              "PCU/hour). SAMPLE DATA — not a real traffic count.")
    return pcu, detail


def _travel_time(*, pcu_per_hour: float, lanes: int, oneway: bool, length_m: float,
                 road_class: str, cfg: dict) -> dict:
    dir_lanes = max(lanes if oneway else lanes / 2, 0.5)
    capacity = dir_lanes * cfg["lane_capacity_pcu_per_hour"]
    vc = pcu_per_hour / capacity if capacity else None
    kmh = _free_flow_kmh(road_class, cfg)
    free_flow_min = (length_m / 1000) / kmh * 60
    delay = 1 + cfg["bpr_alpha"] * (vc ** cfg["bpr_beta"]) if vc is not None else 1.0
    return {"lanes": lanes, "vc_ratio": round(vc, 2) if vc is not None else None,
            "free_flow_kmh": kmh, "minutes": round(free_flow_min * delay, 2)}


def _infer_current_lanes(current_elements: list[dict]) -> int:
    """How many lanes today's undivided carriageway notionally holds, for the 'before' side of the
    comparison. The current-state model (engine.current_state) has no real lane count, so this is
    a width-based guess, capped to stay plausible — SAMPLE DATA, not a survey."""
    carriage_cm = sum(e["width_cm"] for e in current_elements if e["kind"] == "carriageway")
    lanes = round(carriage_cm / cm(LANE_WIDTH_M))
    return max(1, min(lanes, MAX_INFERRED_LANES))


def estimate(*, current_elements: list[dict], option_lanes: int, oneway: bool, length_m: float,
            road_class: str, cfg: dict) -> dict:
    """Before/after travel-time estimate for one design option. SAMPLE DATA throughout —
    see the module docstring. length_m <= 0 is treated as 100 m (a placeholder stretch)."""
    length_m = length_m if length_m and length_m > 0 else 100.0
    before_lanes = _infer_current_lanes(current_elements)
    pcu, pcu_detail = sample_demand_pcu(road_class, cfg)
    before = _travel_time(pcu_per_hour=pcu, lanes=before_lanes, oneway=oneway, length_m=length_m,
                          road_class=road_class, cfg=cfg)
    after = _travel_time(pcu_per_hour=pcu, lanes=option_lanes, oneway=oneway, length_m=length_m,
                         road_class=road_class, cfg=cfg)
    change_pct = ((after["minutes"] - before["minutes"]) / before["minutes"] * 100) if before["minutes"] else 0.0
    return {
        "sample_data": True,
        "note": ("Modelled estimate using a SAMPLE traffic volume and a standard congestion curve "
                 "(BPR), not a real traffic count or a traffic simulation (SUMO). For illustration "
                 "only until real demand data and a simulation are wired in — see docs/PARKED.md."),
        "sample_pcu": round(pcu), "sample_pcu_detail": pcu_detail,
        "length_m": length_m, "before": before, "after": after, "change_pct": round(change_pct, 1),
    }
