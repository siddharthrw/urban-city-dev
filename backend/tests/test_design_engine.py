import copy

import pytest

from core.rules import loader
from core.rules.schema import validate_rule
from modules.roads.design import engine
from modules.roads.design.demand import Demand

RULES = loader.load_all()
CFG = engine.load_config()


def go(row_m=18, road_class="secondary", oneway=False, context=(), demand=None, rules=None, **kw):
    return engine.design(row_m=row_m, road_class=road_class, oneway=oneway, context=set(context),
                         demand=demand, rules=RULES if rules is None else rules, **kw)


def option(res, key):
    return next(o for o in res["options"] if o["option_id"] == key)


def widths(o):
    return [(e["kind"], e["width_cm"]) for e in o["elements"]]


def rule(rid, element, **value):
    return validate_rule({"rule_id": rid, "status": "active", "category": "dimension", "element": element,
                          "statement": f"UNCITED placeholder {rid}", "value": value,
                          "source": {"authority": "placeholder", "detail": "test"}})


# ---------- the plan's 18 m example ----------

def test_18m_road_gives_three_options_that_sum_exactly():
    res = go(18)
    assert [o["option_id"] for o in res["options"]] == ["balanced", "traffic", "walking"]
    assert res["dropped"] == [] and res["row_cm"] == 1800
    assert all(o["total_cm"] == 1800 for o in res["options"])


def test_traffic_option_at_18m_is_minimum_footpaths_and_four_lanes():
    o = option(go(18), "traffic")
    assert widths(o) == [("footpath", 180), ("tree_strip", 120), ("lane", 300), ("lane", 300), ("lane", 300),
                         ("lane", 300), ("tree_strip", 120), ("footpath", 180)]
    assert o["metrics"]["lanes"] == 4 and not o["metrics"]["has_cycle_track"]


def test_balanced_option_has_cycle_tracks_and_shade_and_two_lanes():
    o = option(go(18), "balanced")
    kinds = [e["kind"] for e in o["elements"]]
    assert kinds == ["footpath", "tree_strip", "cycle_track", "lane", "lane", "cycle_track", "tree_strip", "footpath"]
    assert o["metrics"]["has_cycle_track"] and o["metrics"]["has_trees"] and o["metrics"]["lanes"] == 2


def test_option_names_and_summaries_present():
    for o in go(18)["options"]:
        assert o["name"] and o["summary"]


# ---------- too narrow: drop with a reason, never bend a rule ----------

def test_narrow_road_drops_options_with_specific_reasons():
    res = go(12)
    assert [o["option_id"] for o in res["options"]] == ["traffic", "walking"]
    d = res["dropped"][0]
    assert d["option_id"] == "balanced" and "16 m" in d["reason"] and "12 m" in d["reason"]


def test_road_too_narrow_for_anything_returns_no_options_and_says_why():
    res = go(6)
    assert res["options"] == [] and len(res["dropped"]) == 3
    assert any("No layout" in w for w in res["warnings"])
    assert "9.6 m" in next(d for d in res["dropped"] if d["option_id"] == "traffic")["reason"]


def test_one_way_road_needs_less_width():
    # One lane (3.0) + two footpaths (2 x 1.8) = 6.6 m; a two-way road needs 9.6 m.
    assert go(6.6, oneway=True)["options"] and not go(6.59, oneway=True)["options"]
    assert not go(9.0)["options"] and go(9.6)["options"]


def test_one_way_at_7m_gives_a_traffic_layout_with_one_lane_and_no_median():
    o = option(go(7, oneway=True), "traffic")
    assert o["metrics"]["lanes"] == 1 and not o["metrics"]["has_median"]


def test_lanes_are_reduced_before_optional_elements_for_balanced_but_after_for_traffic():
    # 4-lane demand on a 17 m road: balanced sheds lanes to fit its cycle tracks; traffic keeps lanes.
    d = Demand(peak_pcu=9000)
    res = go(17, demand=d)
    assert option(res, "balanced")["metrics"]["lanes"] == 2
    assert option(res, "traffic")["metrics"]["lanes"] == 4
    assert any("Lanes reduced from 4 to 2" in n for n in option(res, "balanced")["notes"])
    assert not any("Lanes reduced" in n for n in option(res, "traffic")["notes"])


# ---------- context, demand, bus ----------

def test_school_and_market_widen_footpaths():
    plain = option(go(24), "balanced")["metrics"]["footpath_m"]
    school = go(24, context={"school_nearby", "market"})
    assert option(school, "balanced")["metrics"]["footpath_m"] > plain
    assert any("Footpath target raised" in n for n in option(school, "balanced")["notes"])


def test_pedestrian_count_sets_the_footpath_target():
    d = Demand(peak_pedestrians=12000, ped_detail="test")  # 12000/2/1500 + 0.5 = 4.5 m per side
    o = option(go(40, demand=d), "walking")
    assert any("pedestrian count" in n and "4.50 m per side" in n for n in o["notes"])
    assert o["metrics"]["footpath_m"] >= 4.49
    assert any(i["name"] == "Pedestrians" for i in go(40, demand=d)["inputs"])


def test_traffic_count_sets_lanes_and_is_reported_as_data():
    res = go(30, road_class="primary", demand=Demand(peak_pcu=200, pcu_detail="row 4"))
    lanes = next(i for i in res["inputs"] if i["name"] == "Lanes needed")
    assert lanes["source"] == "data" and lanes["value"].startswith("1 per direction")
    assert option(res, "balanced")["metrics"]["lanes"] == 2


def test_without_traffic_data_lanes_come_from_the_class_default_and_say_so():
    lanes = next(i for i in go(18)["inputs"] if i["name"] == "Lanes needed")
    assert lanes["source"] == "default" and "UNCITED" in lanes["detail"]


def test_bus_route_adds_bus_bays_to_walking_and_renames_it():
    res = go(24, context={"bus_route"})
    w = option(res, "walking")
    assert w["name"] == "Walking & bus" and w["metrics"]["has_bus_bay"]
    assert [e["kind"] for e in w["elements"]].count("bus_bay") == 2
    no_bus = option(go(24), "walking")
    assert no_bus["name"] == "Walking & shade" and not no_bus["metrics"]["has_bus_bay"]


def test_bus_stop_data_counts_as_a_bus_route():
    res = go(24, demand=Demand(bus_stops=2, bus_detail="2 stops"))
    assert option(res, "walking")["metrics"]["has_bus_bay"]
    assert any(i["name"] == "Bus stops" for i in res["inputs"])


def test_walking_with_bus_is_dropped_when_bays_cannot_fit():
    res = go(13, context={"bus_route"})
    assert "walking" in [d["option_id"] for d in res["dropped"]]


def test_median_only_on_wide_two_way_roads():
    assert option(go(20), "traffic")["metrics"]["has_median"]
    assert option(go(30), "traffic")["metrics"]["has_median"]
    assert not option(go(16), "traffic")["metrics"]["has_median"]
    assert not option(go(30, oneway=True), "traffic")["metrics"]["has_median"]


def test_waterlogging_is_noted_but_not_modelled():
    res = go(18, context={"waterlogging"})
    assert any("not modelled" in w for w in res["warnings"])


# ---------- rules drive everything ----------

def test_balanced_median_only_from_24m():
    assert not option(go(23), "balanced")["metrics"]["has_median"]
    assert option(go(30), "balanced")["metrics"]["has_median"]


def test_a_rule_maximum_is_respected_and_extra_width_goes_elsewhere():
    rules = [r for r in RULES if r.rule_id != "footpath_min_width"] + [rule("fp", "footpath", min_m=1.8, max_m=2.2)]
    res = go(40, rules=rules)
    for o in res["options"]:
        assert all(e["width_cm"] <= 220 for e in o["elements"] if e["kind"] == "footpath")
        assert o["total_cm"] == 4000


def test_changing_a_rule_minimum_changes_the_design_with_no_code_change():
    bigger = [r for r in RULES if r.rule_id != "lane_width_standard"] + [rule("lane", "lane", min_m=3.5, max_m=3.6)]
    base = option(go(16), "traffic")["metrics"]["lanes"]                  # 4 x 3.0 + 2 x 1.8 = 15.6 m fits
    tighter = option(go(16, rules=bigger), "traffic")["metrics"]["lanes"]  # 4 x 3.5 + 3.6 = 17.6 m does not
    assert (base, tighter) == (4, 2)


def test_option_dropped_when_rules_contradict():
    rules = [rule("a", "lane", min_m=4.0), rule("b", "lane", max_m=3.0)]
    res = go(30, rules=rules)
    assert res["options"] == [] and all("contradict" in d["reason"] for d in res["dropped"])


def test_option_dropped_when_extra_width_cannot_be_placed_within_maxima():
    caps = [rule(f"c_{k}", k, max_m=2.5) for k in ("footpath", "tree_strip", "median", "cycle_track", "bus_bay")]
    caps.append(rule("lane_cap", "lane", min_m=3.0, max_m=3.5))
    res = go(55, rules=caps)
    assert all(d["reason"] for d in res["dropped"])
    for o in res["options"]:
        assert o["total_cm"] == 5500


def test_superseded_and_proposed_rules_are_never_used():
    old = validate_rule({"rule_id": "old", "status": "active", "category": "dimension", "element": "footpath",
                         "statement": "old", "value": {"min_m": 9.0},
                         "source": {"authority": "superseded", "doc_id": "d", "page": 1}})
    res = go(18, rules=RULES + [old])
    assert "old" not in res["rules"] and res["options"]


def test_no_rules_at_all_falls_back_to_uncited_minimums_and_says_so():
    res = go(18, rules=[])
    assert res["options"] and all(o["uses_fallback_minimums"] for o in res["options"])
    assert any("no rule" in w for w in res["warnings"])


# ---------- provenance & warnings ----------

def test_estimated_width_and_placeholder_rules_are_flagged():
    res = go(18)
    assert any("ESTIMATE" in w for w in res["warnings"])
    assert any("PLACEHOLDER" in w for w in res["warnings"])


def test_verified_width_has_no_estimate_warning():
    res = go(18, width_source="verified")
    assert not any("ESTIMATE" in w for w in res["warnings"])
    assert next(i for i in res["inputs"] if i["name"] == "Right-of-way")["source"] == "verified"


def test_rules_used_are_listed_with_statement_and_source():
    res = go(18)
    meta = res["rules"]["footpath_min_width"]
    assert "UNCITED" in meta["statement"] and meta["authority"] == "placeholder"
    for o in res["options"]:
        for rid in o["rule_ids"]:
            assert rid in res["rules"]


def test_every_element_lists_the_rules_it_obeyed():
    o = option(go(18), "balanced")
    by_kind = {e["kind"]: e["rule_ids"] for e in o["elements"]}
    assert by_kind["footpath"] == ["footpath_min_width"] and by_kind["lane"] == ["lane_width_standard"]
    assert by_kind["cycle_track"] == ["cycle_track_min_width"]  # the one-way rule, not the two-way one


# ---------- exactness ----------

@pytest.mark.parametrize("row_m", [6.0, 7.01, 9.6, 12.34, 15.55, 18.0, 23.99, 33.33, 47.5, 60.0])
def test_sums_exact_at_awkward_widths(row_m):
    for o in go(row_m)["options"]:
        assert o["total_cm"] == round(row_m * 100)


def test_odd_centimetre_leftover_is_absorbed_by_one_slot_only():
    o = option(go(18.01), "traffic")
    left = [e["width_cm"] for e in o["elements"] if e["side"] == "left"]
    right = [e["width_cm"] for e in o["elements"] if e["side"] == "right"]
    assert sorted(left) == sorted(right) or abs(sum(left) - sum(right)) <= 1


def test_nonpositive_width_is_rejected():
    with pytest.raises(ValueError):
        go(0)


def test_input_rules_and_config_are_not_mutated():
    cfg = copy.deepcopy(CFG)
    before = [r.to_dict() for r in RULES]
    go(18, cfg=cfg)
    assert cfg == CFG and [r.to_dict() for r in RULES] == before


# ---------- the independent checker really catches violations ----------

def check(o, row_cm=1800):
    return engine.check_option(o, RULES, road_class="secondary", context=set(), row_cm=row_cm,
                               fallback_min_m=CFG["fallback_min_m"])


def test_check_option_accepts_engine_output_and_rejects_tampering():
    o = copy.deepcopy(option(go(18), "balanced"))
    assert check(o) == []
    o["elements"][0]["width_cm"] += 1
    assert any("sum" in p for p in check(o))
    o = copy.deepcopy(option(go(18), "balanced"))
    o["elements"][0]["width_cm"] = 100
    o["elements"][1]["width_cm"] += 80
    assert any("below the minimum" in p for p in check(o))
    o = copy.deepcopy(option(go(18), "balanced"))
    o["elements"][3]["width_cm"] = 400
    o["elements"][4]["width_cm"] = 400
    o["elements"][0]["width_cm"] -= 60
    o["elements"][7]["width_cm"] -= 60
    assert any("above the maximum" in p for p in check(o))
