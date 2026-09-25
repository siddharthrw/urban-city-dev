"""The design engine: splits a road's right-of-way into 2-3 named layouts.

Guarantees, for every option returned:
  * widths (integer centimetres) sum EXACTLY to the right-of-way;
  * every element is within the min/max of every applicable active rule;
  * paired elements (footpaths, tree strips, ...) match left/right, all lanes match, apart from at
    most 1 cm of rounding that is pushed onto single elements when the spare width is odd.
An option that cannot be drawn is dropped with a reason, never bent to fit.

No LLM and no I/O here: same inputs, same output.
"""
import math
from pathlib import Path

import yaml

from core.rules.schema import Rule
from modules.roads.design.constraints import Constraint, RuleConflict, RuleSet
from modules.roads.design.demand import Demand

DEFAULTS_PATH = Path(__file__).with_name("design_defaults.yaml")
KIND_LABEL = {"footpath": "Footpath", "tree_strip": "Trees", "cycle_track": "Cycle track",
              "bus_bay": "Bus bay", "lane": "Lane", "median": "Median"}
OUTER_TO_INNER = ["footpath", "tree_strip", "cycle_track", "bus_bay"]  # order from the property line inwards
PHASE4_ORDER = ["median", "tree_strip", "footpath", "cycle_track", "bus_bay", "lane"]
CONTEXT_FLAGS = ("school_nearby", "bus_route", "metro_nearby", "waterlogging", "market")


def load_config(path: Path = DEFAULTS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cm(m: float) -> int:
    return int(round(m * 100))


class _Unplaceable(Exception):
    pass


class _Group:
    __slots__ = ("kind", "size", "cur", "min", "max", "target")

    def __init__(self, kind: str, size: int, con: Constraint, target: int):
        self.kind, self.size, self.min, self.max = kind, size, con.min_cm, con.max_cm
        self.target = min(max(target, con.min_cm), con.max_cm if con.max_cm is not None else 10**9)
        self.cur = con.min_cm


def _layout(n_lanes: int, kinds: list[str], oneway: bool) -> list[tuple[str, str]]:
    """Slots left to right as (kind, side). Two-way roads put the median (if any) between the two
    carriageways; one-way roads have one carriageway."""
    side = [k for k in OUTER_TO_INNER if k in kinds]
    left = [(k, "left") for k in side]
    right = [(k, "right") for k in reversed(side)]
    if oneway or n_lanes < 2:
        mid = [("lane", "centre")] * n_lanes
    else:
        half = [("lane", "centre")] * (n_lanes // 2)
        mid = half + ([("median", "centre")] if "median" in kinds else []) + half
    return left + mid + right


def _fill(groups: dict[str, _Group], slack: int, base: dict[str, int], limit, weight) -> int:
    """Progressive filling: repeatedly give 1 cm to the group that is furthest behind (relative to
    its weight) among those that still have room and whose whole set of slots fits in the slack."""
    while True:
        best, best_level = None, 0.0
        for k, g in groups.items():
            w, lim = weight(g), limit(g)
            if w <= 0 or g.size > slack or (lim is not None and g.cur >= lim):
                continue
            level = (g.cur - base[k]) / w
            if best is None or level < best_level - 1e-12:
                best, best_level = k, level
        if best is None:
            return slack
        groups[best].cur += 1
        slack -= groups[best].size


def _allocate(row_cm: int, slots: list[tuple[str, str]], cons: dict[str, Constraint],
              targets: dict[str, int], opt: dict) -> list[int]:
    kinds = list(dict.fromkeys(k for k, _ in slots))
    groups = {k: _Group(k, sum(1 for s, _ in slots if s == k), cons[k], targets[k]) for k in kinds}
    slack = row_cm - sum(g.cur * g.size for g in groups.values())
    if slack < 0:
        raise _Unplaceable("minimums exceed the width")

    weights = opt.get("surplus_weights", {})
    soft = {k: cm(v) for k, v in opt.get("soft_max_m", {}).items()}
    sinks = [k for k in opt.get("sinks", []) if k in groups]

    slack = _fill(groups, slack, {k: g.min for k, g in groups.items()},
                  lambda g: g.target, lambda g: max(g.target - g.min, 0))

    def cap(g):  # preferred ceiling: the soft max, never above a rule maximum
        return min(soft.get(g.kind, 10**9), g.max if g.max is not None else 10**9)

    slack = _fill(groups, slack, {k: g.cur for k, g in groups.items()}, cap,
                  lambda g: weights.get(g.kind, 0))
    slack = _fill(groups, slack, {k: g.cur for k, g in groups.items()}, lambda g: g.max,
                  lambda g: 1 if g.kind in sinks else 0)

    widths = [groups[k].cur for k, _ in slots]
    order = sorted(range(len(slots)), key=lambda i: (PHASE4_ORDER.index(slots[i][0]), i))
    while slack > 0:  # 1 cm at a time onto single slots: the only place asymmetry can appear
        moved = False
        for i in order:
            hi = groups[slots[i][0]].max
            if slack > 0 and (hi is None or widths[i] < hi):
                widths[i] += 1
                slack -= 1
                moved = True
        if not moved:
            raise _Unplaceable("the remaining width cannot be placed without exceeding a rule maximum")
    assert sum(widths) == row_cm
    return widths


def design(*, row_m: float, road_class: str, oneway: bool, context: set[str] | frozenset[str] = frozenset(),
           demand: Demand | None = None, rules: list[Rule], width_source: str = "estimated",
           cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    demand = demand or Demand()
    context = set(context)
    row_cm = cm(row_m)
    if row_cm <= 0:
        raise ValueError("Road width must be positive")
    cls = cfg["classes"].get(road_class) or cfg["classes"]["unclassified"]
    ruleset = RuleSet(rules, cfg["fallback_min_m"])
    inputs, warnings = _inputs(row_cm, road_class, oneway, context, demand, width_source), []

    step = 1 if oneway else 2
    n_min = step
    if demand.peak_pcu is not None:
        per_dir = demand.peak_pcu if oneway else demand.peak_pcu / 2
        dir_lanes = max(1, math.ceil(per_dir / cfg["lane_capacity_pcu_per_hour"]))
        inputs.append({"name": "Lanes needed", "value": f"{min(dir_lanes, cls['dir_cap'])} per direction",
                       "source": "data", "detail": f"{demand.pcu_detail} One lane carries about "
                       f"{cfg['lane_capacity_pcu_per_hour']:,} PCU/hour (UNCITED setting)."})
    else:
        dir_lanes = cls["dir_default"]
        inputs.append({"name": "Lanes needed", "value": f"{dir_lanes} per direction", "source": "default",
                       "detail": f"No traffic count linked to this road: default for a {road_class.replace('_', ' ')} road (UNCITED)."})
    dir_lanes = min(dir_lanes, cls["dir_cap"])

    bus = "bus_route" in context or bool(demand.bus_stops)
    options, dropped, used_rules = [], [], set()
    for key in ("balanced", "traffic", "walking"):
        opt = cfg["options"][key]
        result = _build(key, opt, row_cm=row_cm, road_class=road_class, oneway=oneway, context=context,
                        demand=demand, ruleset=ruleset, cfg=cfg, dir_lanes=dir_lanes, dir_cap=cls["dir_cap"],
                        bus=bus, n_min=n_min, step=step)
        if "reason" in result:
            dropped.append(result)
        else:
            options.append(result)
            used_rules.update(result["rule_ids"])

    rules_by_id = {r.rule_id: r for r in ruleset.rules}
    rules_meta = {rid: {"statement": rules_by_id[rid].statement, "authority": rules_by_id[rid].source.authority,
                        "source": rules_by_id[rid].source.label(), "quote": rules_by_id[rid].source.quote,
                        "page": rules_by_id[rid].source.page} for rid in sorted(used_rules)}
    if width_source == "estimated":
        warnings.append("The road width is an ESTIMATE (a typical width for this type of road), not a measurement. "
                        "Layouts are only as good as this number: enter a surveyed width to design against.")
    placeholder = sorted(rid for rid, m in rules_meta.items() if m["authority"] == "placeholder")
    if placeholder:
        warnings.append("Dimensions come from PLACEHOLDER rules (UNCITED guesses, not a standard): "
                        + ", ".join(placeholder) + ". Replace them with cited rules before showing this to anyone as a design.")
    if any(o["uses_fallback_minimums"] for o in options):
        warnings.append("Some elements had no rule, so an UNCITED default minimum was used (marked in the option).")
    for flag in sorted(context):
        note = cfg["context_effects"].get(flag, {}).get("note")
        if note:
            warnings.append(note)
    if not options:
        warnings.append("No layout satisfies the rules at this width. See the reasons for each dropped option.")

    return {"row_m": row_cm / 100, "row_cm": row_cm, "road_class": road_class, "oneway": oneway,
            "width_source": width_source, "context": sorted(context), "inputs": inputs,
            "options": options, "dropped": dropped, "warnings": warnings, "rules": rules_meta}


def _inputs(row_cm, road_class, oneway, context, demand, width_source) -> list[dict]:
    out = [{"name": "Right-of-way", "value": f"{row_cm / 100:g} m", "source": width_source,
            "detail": {"estimated": "Typical width for this type of road (not measured).",
                       "measured": "Measured from building footprints.",
                       "verified": "From a survey or official record.",
                       "manual": "Entered by you for this design."}.get(width_source, width_source)},
           {"name": "Road type", "value": road_class.replace("_", " "), "source": "map", "detail": "From OpenStreetMap."},
           {"name": "Direction", "value": "one-way" if oneway else "two-way", "source": "map", "detail": "From OpenStreetMap."}]
    if context:
        out.append({"name": "Context", "value": ", ".join(sorted(c.replace("_", " ") for c in context)),
                    "source": "user", "detail": "Ticked by you."})
    if demand.peak_pedestrians is not None:
        out.append({"name": "Pedestrians", "value": f"{demand.peak_pedestrians:,.0f}", "source": "data",
                    "detail": demand.ped_detail})
    if demand.bus_stops:
        out.append({"name": "Bus stops", "value": str(demand.bus_stops), "source": "data", "detail": demand.bus_detail})
    return out


def _build(key, opt, *, row_cm, road_class, oneway, context, demand, ruleset, cfg, dir_lanes, dir_cap, bus,
           n_min, step) -> dict:
    name = opt["name"] if (key != "walking" or bus) else opt["name_without_bus"]
    base = {"option_id": key, "name": name}

    def drop(reason: str) -> dict:
        return {**base, "reason": reason}

    required = list(opt["required"]) + (list(opt.get("required_with_bus", [])) if bus else [])
    optional = [k for k in opt.get("optional", []) if k != "bus_bay" or bus]
    if opt.get("median_from_row_m") is None or oneway or row_cm < cm(opt["median_from_row_m"] or 0):
        optional = [k for k in optional if k != "median"]
    dir_opt = dir_cap if opt["max_dir_lanes"] == "cap" else min(dir_lanes, opt["max_dir_lanes"], dir_cap)
    n = dir_opt * (1 if oneway else 2)

    try:  # only for the elements this option can contain
        cons = {k: ruleset.constraint(k, road_class, set(context) | ({"one_way"} if k == "cycle_track" else set()))
                for k in set(required) | set(optional) | {"lane"}}
    except RuleConflict as e:
        return drop(str(e))

    kinds = required + optional
    omitted, notes = [], []

    def total(n_, kinds_):
        return sum(cons[k].min_cm for k, _ in _layout(n_, kinds_, oneway))

    n0 = n
    order = ["lanes", "drop"] if opt["lanes_first"] else ["drop", "lanes"]
    while total(n, kinds) > row_cm:
        acted = False
        for g in order:
            if g == "lanes" and n > n_min:
                n -= step
                acted = True
            elif g == "drop":
                k = next((k for k in opt["optional_drop_order"] if k in kinds and k in optional), None)
                if k:
                    kinds.remove(k)
                    omitted.append({"kind": k, "reason": f"{KIND_LABEL[k]} left out so the option fits in {row_cm / 100:g} m."})
                    acted = True
            if acted:
                break
        if not acted:
            break
    if total(n, kinds) > row_cm:
        need = total(n_min, required)
        return drop(f"Needs at least {need / 100:g} m ({', '.join(KIND_LABEL[k].lower() for k in required)} "
                    f"at their rule minimums, {n_min} lane{'s' if n_min > 1 else ''}), but the road is {row_cm / 100:g} m.")
    if n < n0:
        notes.append(f"Lanes reduced from {n0} to {n} so the option fits.")

    targets = {k: cm(opt["targets_m"].get(k, cfg["fallback_min_m"][k])) for k in KIND_LABEL}
    add = sum(cfg["context_effects"].get(f, {}).get("footpath_target_add_m", 0) for f in context)
    if add:
        targets["footpath"] += cm(add)
        notes.append(f"Footpath target raised by {add:g} m for: "
                     + ", ".join(f.replace('_', ' ') for f in sorted(context) if cfg['context_effects'].get(f, {}).get('footpath_target_add_m')) + ".")
    if demand.peak_pedestrians is not None:
        per_side = demand.peak_pedestrians / 2 / cfg["pedestrians_per_metre_per_hour"] + cfg["footpath_furniture_allowance_m"]
        if cm(per_side) > targets["footpath"]:
            targets["footpath"] = cm(per_side)
            notes.append(f"Footpath target set from the pedestrian count: {per_side:.2f} m per side "
                         f"({cfg['pedestrians_per_metre_per_hour']:,} people/metre/hour + {cfg['footpath_furniture_allowance_m']} m "
                         "edge allowance, UNCITED settings).")

    slots = _layout(n, kinds, oneway)
    try:
        widths = _allocate(row_cm, slots, cons, targets, opt)
    except _Unplaceable as e:
        return drop(f"Cannot be drawn at {row_cm / 100:g} m: {e}.")

    elements = [{"kind": k, "label": KIND_LABEL[k], "side": side, "width_cm": w, "width_m": w / 100,
                 "rule_ids": list(cons[k].rule_ids), "fallback_minimum": cons[k].fallback}
                for (k, side), w in zip(slots, widths)]
    rule_ids = sorted({rid for e in elements for rid in e["rule_ids"]})
    lane_w = [e["width_cm"] for e in elements if e["kind"] == "lane"]
    foot = [e["width_cm"] for e in elements if e["kind"] == "footpath"]
    metrics = {"lanes": n, "carriageway_m": (sum(lane_w) + sum(e["width_cm"] for e in elements if e["kind"] == "median")) / 100,
               "lane_width_m": min(lane_w) / 100, "footpath_m": min(foot) / 100,
               "has_cycle_track": "cycle_track" in kinds, "has_trees": "tree_strip" in kinds,
               "has_bus_bay": "bus_bay" in kinds, "has_median": "median" in kinds}
    return {**base, "summary": opt["summary"], "elements": elements, "omitted": omitted, "notes": notes,
            "metrics": metrics, "rule_ids": rule_ids, "total_cm": sum(widths),
            "uses_fallback_minimums": any(e["fallback_minimum"] for e in elements)}


def check_option(option: dict, rules: list[Rule], *, road_class: str, context: set[str], row_cm: int,
                 fallback_min_m: dict[str, float]) -> list[str]:
    """Independent validation of a finished option, for tests and for M4: returns a list of
    problems (empty = valid). Recomputes each element's constraint from the rules."""
    problems = []
    if sum(e["width_cm"] for e in option["elements"]) != row_cm:
        problems.append(f"widths sum to {sum(e['width_cm'] for e in option['elements'])} cm, road is {row_cm} cm")
    rs = RuleSet(rules, fallback_min_m)
    for e in option["elements"]:
        tags = set(context) | ({"one_way"} if e["kind"] == "cycle_track" else set())
        c = rs.constraint(e["kind"], road_class, tags)
        if e["width_cm"] < c.min_cm:
            problems.append(f"{e['kind']} {e['width_cm']} cm is below the minimum {c.min_cm} cm")
        if c.max_cm is not None and e["width_cm"] > c.max_cm:
            problems.append(f"{e['kind']} {e['width_cm']} cm is above the maximum {c.max_cm} cm")
    return problems
