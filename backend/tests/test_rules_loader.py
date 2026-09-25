import pytest

from core.rules import loader
from core.rules.schema import RuleError

DIM = {
    "rule_id": "footpath_min", "status": "active", "category": "dimension", "element": "footpath",
    "statement": "UNCITED placeholder: footpaths at least 1.8 m.", "value": {"min_m": 1.8},
    "source": {"authority": "placeholder", "detail": "guess"},
}
PROPOSED = {
    "rule_id": "cycle_track_min", "status": "proposed", "category": "dimension", "element": "cycle_track",
    "statement": "A cycle track shall be at least 2.0 m wide.", "value": {"min_m": 2.0},
    "source": {"authority": "primary", "doc_id": "doc-1", "doc_title": "SAMPLE Standard",
              "page": 7, "quote": "A cycle track shall be at least 2.0 m wide."},
}


def test_empty_rules_dir_loads_nothing(rules_dir):
    assert loader.load_all() == []
    assert (rules_dir / "active").is_dir() and (rules_dir / "proposed").is_dir()


def test_write_and_load_active_and_proposed(rules_dir):
    loader.write_active("set1", [DIM])
    loader.write_proposed("doc1", [PROPOSED])
    rules = {r.rule_id: r for r in loader.load_all()}
    assert set(rules) == {"footpath_min", "cycle_track_min"}
    assert rules["footpath_min"].status == "active" and rules["footpath_min"].file == "active/set1.yaml"
    assert rules["cycle_track_min"].status == "proposed" and rules["cycle_track_min"].file == "proposed/doc1.yaml"


def test_rewriting_the_same_file_replaces_its_contents(rules_dir):
    loader.write_active("set1", [DIM])
    loader.write_active("set1", [{**DIM, "value": {"min_m": 2.0}}])  # re-import with a changed value
    rules = loader.load_all()
    assert len(rules) == 1 and rules[0].value == {"min_m": 2.0}


def test_duplicate_rule_id_across_different_files_is_rejected(rules_dir):
    loader.write_active("set1", [DIM])
    loader.write_active("set2", [DIM])
    with pytest.raises(RuleError, match="Duplicate rule_id"):
        loader.load_all()


def test_get_returns_none_for_unknown_rule(rules_dir):
    assert loader.get("nope") is None
    loader.write_active("set1", [DIM])
    assert loader.get("footpath_min").rule_id == "footpath_min"


def test_approve_moves_a_rule_into_its_own_active_file(rules_dir):
    loader.write_proposed("doc1", [PROPOSED, {**PROPOSED, "rule_id": "other_rule", "value": {"min_m": 3.0}}])
    approved = loader.approve("cycle_track_min")
    assert approved.status == "active" and approved.file == "active/cycle_track_min.yaml"
    assert approved.source.authority == "primary" and approved.source.quote == PROPOSED["source"]["quote"]

    remaining = loader.load_all()
    statuses = {r.rule_id: r.status for r in remaining}
    assert statuses == {"cycle_track_min": "active", "other_rule": "proposed"}
    # The sibling rule's own file is untouched -- still readable, still proposed.
    assert loader.get("other_rule").file == "proposed/doc1.yaml"


def test_approve_removes_the_file_when_it_was_the_only_rule_in_it(rules_dir):
    loader.write_proposed("doc1", [PROPOSED])
    loader.approve("cycle_track_min")
    assert not (rules_dir / "proposed" / "doc1.yaml").exists()


def test_reject_deletes_the_rule(rules_dir):
    loader.write_proposed("doc1", [PROPOSED])
    loader.reject("cycle_track_min")
    assert loader.load_all() == []
    assert not (rules_dir / "proposed" / "doc1.yaml").exists()


def test_reject_only_removes_its_own_rule_from_a_shared_file(rules_dir):
    loader.write_proposed("doc1", [PROPOSED, {**PROPOSED, "rule_id": "other_rule"}])
    loader.reject("cycle_track_min")
    remaining = loader.load_all()
    assert [r.rule_id for r in remaining] == ["other_rule"]


def test_cannot_approve_or_reject_an_already_active_rule(rules_dir):
    loader.write_active("set1", [DIM])
    with pytest.raises(RuleError, match="already active"):
        loader.approve("footpath_min")
    with pytest.raises(RuleError, match="already active"):
        loader.reject("footpath_min")


def test_approve_reject_unknown_rule(rules_dir):
    with pytest.raises(RuleError, match="No rule"):
        loader.approve("nope")
    with pytest.raises(RuleError, match="No rule"):
        loader.reject("nope")


def test_write_proposed_validates_before_writing_anything(rules_dir):
    bad = {**PROPOSED, "value": {}}  # dimension rule with no min/max
    with pytest.raises(RuleError):
        loader.write_proposed("doc1", [bad])
    assert loader.load_all() == []  # nothing was written


def test_file_paths_use_forward_slashes_even_on_windows(rules_dir):
    # Regression: rule.file must be splittable on "/" for approve()/reject() to find the
    # sibling file, which broke on Windows when Path str() used backslashes.
    loader.write_proposed("doc1", [PROPOSED])
    rule = loader.get("cycle_track_min")
    assert "\\" not in rule.file
    assert rule.file == "proposed/doc1.yaml"
