import pytest

from core.inbox import mapping
from core.layers import registry
from core.llm import client as llm

TRAFFIC = registry.import_fields("traffic_counts")


def cols(*names, typ="text"):
    return [{"name": n, "type": typ, "filled": 1} for n in names]


def test_auto_detects_real_world_headers():
    got = mapping.auto_suggest(["Sl No", "Name of Road", "Date of Survey", "Cars (nos)", "2W", "Auto Rickshaw", "Total"], TRAFFIC)
    flat = {f: v["column"] for f, v in got.items()}
    assert flat == {"road_name": "Name of Road", "count_date": "Date of Survey", "cars": "Cars (nos)",
                    "two_wheelers": "2W", "autos": "Auto Rickshaw", "total_vehicles": "Total"}
    assert all(v["method"] == "auto" for v in got.values())


def test_each_column_used_once_and_weak_matches_ignored():
    got = mapping.auto_suggest(["Cars", "Car"], TRAFFIC)
    assert list(got) == ["cars"]
    assert mapping.auto_suggest(["xyz", "Remarks about the weather"], {"cars": TRAFFIC["cars"]}) == {}


def test_lat_lon_skipped_when_file_has_geometry():
    out = mapping.suggest(cols("Latitude", "Longitude", "Stop"), registry.import_fields("bus_stops"), has_geometry=True)
    assert "latitude" not in out["mapping"] and out["mapping"]["stop_name"]["column"] == "Stop"


def test_prompt_contains_headers_and_types_but_never_values():
    columns = cols("Road", "Vehicles", typ="number")
    prompt = mapping.llm_prompt(columns, TRAFFIC)
    assert "- cars (int): Cars." in prompt
    # The file part of the prompt is exactly the headers and their types: nothing else about the file.
    assert prompt.split("Column headers in the file:\n")[1] == '- "Road" (number)\n- "Vehicles" (number)'


def test_llm_answers_are_validated(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"mapping": {
        "cars": "Vehicles", "buses": "Vehicles",   # duplicate column -> second dropped
        "trucks": "Not A Column",                   # invented header -> dropped
        "flying_cars": "Road",                      # unknown field -> dropped
        "direction": None,
    }})
    assert mapping.llm_suggest(cols("Road", "Vehicles"), TRAFFIC) == {"cars": "Vehicles"}


def test_suggest_merges_ai_into_gaps_only(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"mapping": {"cars": "LMV Count", "road_name": "Where", "buses": "Stage Carriages"}})
    out = mapping.suggest(cols("Where", "LMV Count", "Stage Carriages", "Cars"), TRAFFIC, use_llm=True)
    m = out["mapping"]
    assert m["cars"] == {"column": "Cars", "method": "auto", "score": 100, "ai_suggests": "LMV Count"}  # auto wins
    assert m["buses"]["method"] == "ai" and m["buses"]["column"] == "Stage Carriages"
    assert "column names and types only" in out["notes"][0]


def test_suggest_survives_llm_failure(monkeypatch):
    def boom(*a, **k):
        raise llm.LLMError("Ollama is not running")
    monkeypatch.setattr(llm, "chat_json", boom)
    out = mapping.suggest(cols("Cars"), TRAFFIC, use_llm=True)
    assert out["mapping"]["cars"]["column"] == "Cars"
    assert "unavailable" in out["notes"][0]


@pytest.mark.parametrize("layer_id", [d["layer_id"] for d in registry.import_layer_defs()])
def test_every_layer_type_is_well_formed(layer_id):
    d = registry.layer_def(layer_id)
    assert d["topic"] in {t["topic"] for t in registry.topics()}
    assert d["color"].startswith("#")
    if "link_to" in d:
        assert d["link_to"] == "roads"
    fields = registry.import_fields(layer_id)
    assert {"latitude", "longitude", "road_name"} <= set(fields)
    for f, spec in fields.items():
        assert spec["type"] in {"string", "int", "float", "date"}, f
        assert isinstance(spec.get("aliases", []), list), f
    for f in d.get("summary_fields", []):
        assert f in fields, f
