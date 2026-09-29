"""Property-based tests: for ANY road width from 6 to 60 m (to the centimetre), class, direction,
context and demand, every option the engine returns sums exactly to the right-of-way and breaks
no rule. Hypothesis searches for a counter-example; none may exist."""
from hypothesis import given, settings, strategies as st

from core.rules import loader
from modules.roads.design import engine
from modules.roads.design.demand import Demand

RULES = loader.load_all()  # the real repo rules (placeholder set); read-only
CFG = engine.load_config()
CLASSES = sorted(CFG["classes"])
FLAGS = list(engine.CONTEXT_FLAGS)

demands = st.builds(
    Demand,
    peak_pcu=st.one_of(st.none(), st.floats(0, 20000)),
    peak_pedestrians=st.one_of(st.none(), st.floats(0, 20000)),
    bus_stops=st.one_of(st.none(), st.integers(0, 5)),
)
inputs = dict(
    row_cm=st.integers(600, 6000),
    road_class=st.sampled_from(CLASSES),
    oneway=st.booleans(),
    context=st.sets(st.sampled_from(FLAGS)),
    demand=demands,
)


def run(row_cm, road_class, oneway, context, demand):
    return engine.design(row_m=row_cm / 100, road_class=road_class, oneway=oneway, context=context,
                         demand=demand, rules=RULES)


@settings(max_examples=250, deadline=None)
@given(**inputs)
def test_every_option_sums_exactly_and_breaks_no_rule(row_cm, road_class, oneway, context, demand):
    res = run(row_cm, road_class, oneway, context, demand)
    for o in res["options"]:
        assert o["total_cm"] == row_cm == sum(e["width_cm"] for e in o["elements"])
        problems = engine.check_option(o, RULES, road_class=road_class, context=context, row_cm=row_cm,
                                       fallback_min_m=CFG["fallback_min_m"])
        assert problems == [], (o["option_id"], problems)
        assert all(e["width_cm"] > 0 for e in o["elements"])


@settings(max_examples=250, deadline=None)
@given(**inputs)
def test_layouts_are_symmetric(row_cm, road_class, oneway, context, demand):
    for o in run(row_cm, road_class, oneway, context, demand)["options"]:
        els = o["elements"]
        for kind in ("footpath", "tree_strip", "cycle_track", "bus_bay"):
            sides = [e["width_cm"] for e in els if e["kind"] == kind and e["side"] == "left"]
            mirrored = [e["width_cm"] for e in els if e["kind"] == kind and e["side"] == "right"]
            assert len(sides) == len(mirrored)
            assert all(abs(a - b) <= 1 for a, b in zip(sides, mirrored)), (kind, sides, mirrored)
        lanes = [e["width_cm"] for e in els if e["kind"] == "lane"]
        assert max(lanes) - min(lanes) <= 1
        # the drawing order really is a mirror image in kinds
        assert [e["kind"] for e in els] == [e["kind"] for e in reversed(els)]


@settings(max_examples=250, deadline=None)
@given(**inputs)
def test_lane_counts_and_directions_are_valid(row_cm, road_class, oneway, context, demand):
    for o in run(row_cm, road_class, oneway, context, demand)["options"]:
        lanes = o["metrics"]["lanes"]
        assert lanes >= 1
        shared = o["option_id"] == "narrow"  # narrow uses one shared carriageway for both directions
        if not oneway and not shared:
            assert lanes % 2 == 0 and lanes >= 2  # a two-way road never has an odd or single lane
            assert o["metrics"]["has_median"] == any(e["kind"] == "median" for e in o["elements"])
        elif not oneway and shared:
            assert lanes == 1  # narrow: single shared lane regardless of direction
        else:
            assert not o["metrics"]["has_median"]


@settings(max_examples=250, deadline=None)
@given(**inputs)
def test_an_empty_result_always_explains_itself(row_cm, road_class, oneway, context, demand):
    res = run(row_cm, road_class, oneway, context, demand)
    # 3 standard options always; narrow adds a 4th (two-way, ≤9.5 m);
    # two_wheeler_priority adds another when two_wheeler_dominant is in context
    assert 3 <= len(res["options"]) + len(res["dropped"]) <= 5
    assert all(d["reason"] for d in res["dropped"])
    if not res["options"]:
        assert res["warnings"] and any("No layout" in w for w in res["warnings"])


@settings(max_examples=250, deadline=None)
@given(**inputs)
def test_wide_enough_roads_always_get_an_option(row_cm, road_class, oneway, context, demand):
    # Traffic priority needs only footpaths + the minimum lanes; two-way minimum is 2x3.0 + 2x1.8.
    minimum_cm = 960 if not oneway else 660
    res = run(row_cm, road_class, oneway, context, demand)
    if row_cm >= minimum_cm:
        assert res["options"], (row_cm, res["dropped"])


@settings(max_examples=100, deadline=None)
@given(**inputs)
def test_engine_is_deterministic(row_cm, road_class, oneway, context, demand):
    assert run(row_cm, road_class, oneway, context, demand) == run(row_cm, road_class, oneway, context, demand)


@settings(max_examples=100, deadline=None)
@given(**inputs)
def test_rule_ids_reported_are_the_rules_that_apply(row_cm, road_class, oneway, context, demand):
    res = run(row_cm, road_class, oneway, context, demand)
    known = {r.rule_id for r in RULES}
    for o in res["options"]:
        assert set(o["rule_ids"]) <= known
        assert set(o["rule_ids"]) <= set(res["rules"])
        for e in o["elements"]:
            assert e["rule_ids"] or e["fallback_minimum"]
