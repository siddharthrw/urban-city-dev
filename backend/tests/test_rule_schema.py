import pytest

from core.rules.schema import RuleError, validate_file, validate_rule

DIM = {
    "rule_id": "footpath_min", "status": "active", "category": "dimension", "element": "footpath",
    "statement": "Footpaths shall be at least 1.8 m wide.", "value": {"min_m": 1.8},
    "source": {"authority": "primary", "doc_id": "irc-103", "page": 12},
}
COND = {
    "rule_id": "school_crossing", "status": "active", "category": "conditional",
    "statement": "If a school is within 200 m, add a raised crossing.",
    "condition": {"if": "school within 200 m", "then": "add a raised crossing"},
    "source": {"authority": "expert", "detail": "Expert judgement"},
}
PLACEHOLDER = {
    "rule_id": "lane_width", "status": "active", "category": "dimension", "element": "lane",
    "statement": "UNCITED placeholder: lanes should be 3.0-3.5 m.", "value": {"min_m": 3.0, "max_m": 3.5},
    "source": {"authority": "placeholder", "detail": "typical practice"},
}


def test_valid_dimension_and_conditional_rules():
    r = validate_rule(DIM)
    assert r.rule_id == "footpath_min" and r.element == "footpath" and r.value == {"min_m": 1.8}
    assert r.source.authority == "primary" and r.source.page == 12

    r2 = validate_rule(COND)
    assert r2.category == "conditional" and r2.condition["then"] == "add a raised crossing"


def test_placeholder_must_say_so_in_the_statement():
    validate_rule(PLACEHOLDER)  # says "UNCITED" -> fine
    bad = {**PLACEHOLDER, "statement": "Lanes should be 3.0-3.5 m."}
    with pytest.raises(RuleError, match="must say so"):
        validate_rule(bad)


@pytest.mark.parametrize("authority", ["primary", "superseded"])
def test_cited_authorities_need_doc_id_and_page(authority):
    bad = {**DIM, "source": {"authority": authority, "doc_id": "irc-103"}}  # no page
    with pytest.raises(RuleError, match="needs source.doc_id and source.page"):
        validate_rule(bad)
    bad2 = {**DIM, "source": {"authority": authority, "page": 12}}  # no doc_id
    with pytest.raises(RuleError, match="needs source.doc_id and source.page"):
        validate_rule(bad2)


def test_expert_and_placeholder_do_not_need_a_citation():
    validate_rule(COND)         # expert, no doc_id -- fine
    validate_rule(PLACEHOLDER)  # placeholder, no doc_id -- fine


@pytest.mark.parametrize("field", ["rule_id", "status", "category", "statement", "source"])
def test_missing_required_top_level_fields(field):
    bad = {k: v for k, v in DIM.items() if k != field}
    with pytest.raises(RuleError, match=f"missing required field '{field}'" if field != "source" else "missing 'source'"):
        validate_rule(bad)


def test_unknown_status_category_authority_rejected():
    with pytest.raises(RuleError, match="status must be"):
        validate_rule({**DIM, "status": "draft"})
    with pytest.raises(RuleError, match="category must be"):
        validate_rule({**DIM, "category": "vibe"})
    with pytest.raises(RuleError, match="authority must be"):
        validate_rule({**DIM, "source": {"authority": "trust me", "doc_id": "x", "page": 1}})


def test_expected_status_mismatch():
    with pytest.raises(RuleError, match="proposed/ folder"):
        validate_rule(DIM, expected_status="proposed")


def test_dimension_rule_needs_a_known_element_and_a_value():
    with pytest.raises(RuleError, match="needs 'element'"):
        validate_rule({**DIM, "element": "sidewalk"})  # not a recognised element name
    with pytest.raises(RuleError, match="needs value.min_m and/or value.max_m"):
        validate_rule({**DIM, "value": {}})


@pytest.mark.parametrize("value", [{"min_m": 0}, {"min_m": -1}, {"min_m": "wide"}])
def test_dimension_values_must_be_positive_numbers(value):
    with pytest.raises(RuleError, match="must be a positive number"):
        validate_rule({**DIM, "value": value})


def test_min_cannot_exceed_max():
    with pytest.raises(RuleError, match="greater than value.max_m"):
        validate_rule({**DIM, "value": {"min_m": 5, "max_m": 2}})


def test_conditional_rule_needs_if_and_then():
    with pytest.raises(RuleError, match="missing required field 'if'"):
        validate_rule({**COND, "condition": {"then": "x"}})
    with pytest.raises(RuleError, match="missing required field 'then'"):
        validate_rule({**COND, "condition": {"if": "x"}})


def test_applies_to_must_be_a_mapping():
    with pytest.raises(RuleError, match="applies_to must be a mapping"):
        validate_rule({**DIM, "applies_to": ["primary"]})


def test_applies_to_is_optional_and_passed_through():
    r = validate_rule({**DIM, "applies_to": {"road_class": ["primary", "secondary"]}})
    assert r.applies_to == {"road_class": ["primary", "secondary"]}


def test_validate_file_rejects_duplicate_ids_within_one_file():
    with pytest.raises(RuleError, match="Duplicate rule_id"):
        validate_file([DIM, {**DIM}], expected_status="active", file="x.yaml")


def test_validate_file_returns_rules_tagged_with_the_file():
    rules = validate_file([DIM, COND], expected_status="active", file="active/set.yaml")
    assert all(r.file == "active/set.yaml" for r in rules)


def test_to_dict_round_trips_through_validate_rule():
    r = validate_rule(DIM)
    again = validate_rule(r.to_dict())
    assert again == r


def test_source_label_for_each_authority():
    assert validate_rule(PLACEHOLDER).source.label() == "Placeholder (uncited)"
    assert "Expert judgement" in validate_rule(COND).source.label()
    assert "irc-103" in validate_rule(DIM).source.label() or "p.12" in validate_rule(DIM).source.label()


def test_source_label_never_doubles_up_expert_judgement():
    r = validate_rule({**COND, "source": {"authority": "expert", "detail": "Expert judgement"}})
    assert r.source.label() == "Expert judgement"
    r2 = validate_rule({**COND, "source": {"authority": "expert", "detail": "Expert judgement: tree guide p.4"}})
    assert r2.source.label() == "Expert judgement: tree guide p.4"
