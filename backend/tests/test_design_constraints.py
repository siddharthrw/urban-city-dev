import pytest

from core.rules.schema import validate_rule
from modules.roads.design.constraints import RuleConflict, RuleSet, cm_ceil, cm_floor, usable

FALLBACK = {"footpath": 1.5, "tree_strip": 1.0, "cycle_track": 1.5, "lane": 3.0, "median": 0.6, "bus_bay": 2.5}


def rule(rid, element, *, min_m=None, max_m=None, applies_to=None, status="active", authority="placeholder"):
    d = {"rule_id": rid, "status": status, "category": "dimension", "element": element,
         "statement": f"UNCITED placeholder rule {rid}", "value": {k: v for k, v in
                                                                   {"min_m": min_m, "max_m": max_m}.items() if v is not None},
         "source": {"authority": authority, "detail": "test"} if authority == "placeholder"
         else {"authority": authority, "doc_id": "d", "page": 1}}
    if applies_to:
        d["applies_to"] = applies_to
    return validate_rule(d)


def cs(rules):
    return RuleSet(rules, FALLBACK)


def test_centimetre_rounding_never_undercuts_a_minimum_or_overshoots_a_maximum():
    assert cm_ceil(1.8) == 180 and cm_ceil(2.005) == 201 and cm_ceil(0.1 + 0.2) == 30
    assert cm_floor(3.5) == 350 and cm_floor(3.499) == 349


def test_min_and_max_from_one_rule():
    c = cs([rule("r", "lane", min_m=3.0, max_m=3.5)]).constraint("lane", "primary", set())
    assert (c.min_cm, c.max_cm, c.rule_ids, c.fallback) == (300, 350, ("r",), False)


def test_several_rules_combine_strictly():
    c = cs([rule("a", "footpath", min_m=1.8), rule("b", "footpath", min_m=2.4, max_m=6.0),
            rule("c", "footpath", max_m=4.0)]).constraint("footpath", "primary", set())
    assert (c.min_cm, c.max_cm) == (240, 400) and set(c.rule_ids) == {"a", "b", "c"}


def test_contradicting_rules_raise():
    with pytest.raises(RuleConflict, match="contradict"):
        cs([rule("a", "footpath", min_m=3.0), rule("b", "footpath", max_m=2.0)]).constraint("footpath", "primary", set())


def test_no_rule_uses_the_uncited_fallback_and_says_so():
    c = cs([]).constraint("median", "primary", set())
    assert c.fallback and c.min_cm == 60 and c.rule_ids == ()


def test_rule_with_only_a_max_still_falls_back_for_the_minimum():
    c = cs([rule("m", "median", max_m=5.0)]).constraint("median", "primary", set())
    assert c.min_cm == 60 and c.max_cm == 500 and c.fallback


def test_context_scoped_rules_apply_only_when_the_tag_is_present():
    rs = cs([rule("one", "cycle_track", min_m=2.0, applies_to={"context": ["one_way"]}),
             rule("two", "cycle_track", min_m=2.5, applies_to={"context": ["two_way"]})])
    assert rs.constraint("cycle_track", "primary", {"one_way"}).min_cm == 200
    assert rs.constraint("cycle_track", "primary", {"two_way"}).min_cm == 250
    assert rs.constraint("cycle_track", "primary", set()).fallback  # neither applies


def test_all_listed_context_tags_are_required():
    rs = cs([rule("r", "footpath", min_m=3.0, applies_to={"context": ["market", "school_nearby"]})])
    assert rs.constraint("footpath", "primary", {"market"}).min_cm == 150  # fallback
    assert rs.constraint("footpath", "primary", {"market", "school_nearby", "x"}).min_cm == 300


def test_road_class_scoped_rules():
    rs = cs([rule("r", "lane", min_m=3.5, applies_to={"road_class": ["primary", "trunk"]})])
    assert rs.constraint("lane", "primary", set()).min_cm == 350
    assert rs.constraint("lane", "residential", set()).fallback


def test_unknown_applies_to_key_means_the_rule_is_not_used():
    rs = cs([rule("r", "lane", min_m=9.0, applies_to={"weather": ["rain"]})])
    assert rs.constraint("lane", "primary", set()).min_cm == 300  # fallback, not 9.0


def test_only_active_non_superseded_dimension_rules_are_usable():
    rules = [rule("ok", "lane", min_m=3.0),
             rule("prop", "lane", min_m=9.0, status="proposed", authority="primary"),
             rule("old", "lane", min_m=8.0, authority="superseded")]
    assert [r.rule_id for r in usable(rules)] == ["ok"]
    assert cs(rules).constraint("lane", "primary", set()).min_cm == 300
