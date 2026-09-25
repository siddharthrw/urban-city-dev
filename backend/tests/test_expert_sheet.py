import pytest

from core.inbox import files, validate
from core.rules import expert_sheet, loader
from tests.conftest import SAMPLES


@pytest.fixture
def sample_source(world):
    sid = files.save_upload((SAMPLES / "SAMPLE_expert_rules.csv").read_bytes(), "SAMPLE_expert_rules.csv",
                            topic="roads", city_id="chennai")
    from core.store import catalog
    return catalog.get_source(sid)


def test_auto_mapping_finds_the_four_columns(sample_source):
    res, pv, cmap = expert_sheet.preview_and_map(sample_source, None)
    assert cmap == {"if_text": "If", "then_text": "Then", "because_text": "Because", "source_text": "Source"}
    assert pv["row_count"] == 4


def test_import_writes_one_rule_per_row(rules_dir, sample_source):
    res = expert_sheet.import_sheet(sample_source, None)
    assert res["imported"] == 4 and res["invalid"] == 0
    rules = {r.rule_id: r for r in loader.load_all()}
    assert set(rules) == set(res["rule_ids"])
    assert all(r.category == "conditional" and r.status == "active" for r in rules.values())
    assert all(r.source.authority == "expert" for r in rules.values())


def test_statement_and_condition_come_from_if_then(rules_dir, sample_source):
    expert_sheet.import_sheet(sample_source, None)
    r = next(r for r in loader.load_all() if "seating" in r.condition["if"].lower())
    assert r.condition["if"] == "There is seating on the footpath"
    assert r.condition["then"] == "Place a shade tree over it"
    assert r.condition["because"] == "Too hot to sit otherwise"
    assert r.statement == "If There is seating on the footpath, then place a shade tree over it."


def test_source_text_becomes_the_expert_detail(rules_dir, sample_source):
    expert_sheet.import_sheet(sample_source, None)
    r = next(r for r in loader.load_all() if "tree" in r.condition["if"].lower())
    assert r.source.detail == "Tree guide p.X"


def test_rule_ids_are_unique_even_for_similar_if_texts(rules_dir):
    csv = "If,Then\nA school is near,Do X\nA school is near,Do Y\n"
    src = _upload_csv(csv)
    res = expert_sheet.import_sheet(src, None)
    assert len(set(res["rule_ids"])) == 2


def test_reimporting_the_same_file_replaces_its_rules(rules_dir, sample_source):
    expert_sheet.import_sheet(sample_source, None)
    before = len(loader.load_all())
    expert_sheet.import_sheet(sample_source, None)
    assert len(loader.load_all()) == before  # not doubled


def test_missing_required_column_is_reported(rules_dir):
    src = _upload_csv("Then,Because\nDo X,Y\n")
    with pytest.raises(validate.Invalid, match="If"):
        expert_sheet.import_sheet(src, None)


def test_invalid_rows_are_reported_not_silently_dropped(rules_dir):
    # A blank "If" cell -> required field missing for that row only.
    src = _upload_csv("If,Then\nA school is near,Do X\n,Do Y\n")
    res = expert_sheet.import_sheet(src, None)
    assert res["imported"] == 1 and res["invalid"] == 1
    assert "If" in res["problems"][0]["errors"][0]


def _upload_csv(text: str) -> dict:
    from core.store import catalog
    sid = files.save_upload(text.encode(), "sheet.csv", topic="roads", city_id="chennai")
    return catalog.get_source(sid)
