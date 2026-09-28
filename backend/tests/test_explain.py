"""Unit tests for the LLM explanation module (explain.py)."""
import pytest

from modules.roads.design.explain import build_prompt, build_prompt_one, explain, explain_one, unknown_citations

_RULES = {
    "footpath_min_width": {
        "statement": "UNCITED: footpaths at least 1.8 m.",
        "authority": "placeholder",
        "source": "Placeholder (uncited)",
        "quote": None,
        "page": None,
    }
}

_RESULT = {
    "row_m": 18.0, "row_cm": 1800, "road_class": "secondary", "oneway": False,
    "width_source": "estimated", "context": [],
    "segment": {"seg_id": "1-2-0", "name": "Usman Road",
                "road_width_m": 18.0, "road_width_source": "estimated"},
    "options": [
        {
            "option_id": "balanced",
            "name": "Balanced (cycle track + shade)",
            "summary": "Footpaths, trees and a cycle track.",
            "elements": [
                {"kind": "footpath", "label": "Footpath", "side": "left",
                 "width_cm": 250, "width_m": 2.5, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
                {"kind": "lane", "label": "Lane", "side": "centre",
                 "width_cm": 650, "width_m": 6.5, "rule_ids": [], "fallback_minimum": False},
                {"kind": "footpath", "label": "Footpath", "side": "right",
                 "width_cm": 250, "width_m": 2.5, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
            ],
            "omitted": [], "notes": [],
            "metrics": {"lanes": 2, "carriageway_m": 6.5, "lane_width_m": 3.25, "footpath_m": 2.5,
                        "has_cycle_track": False, "has_trees": False, "has_bus_bay": False, "has_median": False},
            "rule_ids": ["footpath_min_width"],
            "total_cm": 1800, "uses_fallback_minimums": False,
        },
        {
            "option_id": "traffic",
            "name": "Traffic priority",
            "summary": "As many lanes as fit.",
            "elements": [
                {"kind": "footpath", "label": "Footpath", "side": "left",
                 "width_cm": 180, "width_m": 1.8, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
                {"kind": "lane", "label": "Lane", "side": "centre",
                 "width_cm": 720, "width_m": 7.2, "rule_ids": [], "fallback_minimum": False},
                {"kind": "footpath", "label": "Footpath", "side": "right",
                 "width_cm": 180, "width_m": 1.8, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
            ],
            "omitted": [], "notes": [],
            "metrics": {"lanes": 2, "carriageway_m": 7.2, "lane_width_m": 3.6, "footpath_m": 1.8,
                        "has_cycle_track": False, "has_trees": False, "has_bus_bay": False, "has_median": False},
            "rule_ids": ["footpath_min_width"],
            "total_cm": 1800, "uses_fallback_minimums": False,
        },
    ],
    "dropped": [{"option_id": "walking", "name": "Walking & shade", "reason": "Needs 20 m."}],
    "warnings": ["Width is an ESTIMATE."],
    "rules": _RULES,
}


# ---------- build_prompt ----------

def test_build_prompt_includes_road_context_inputs():
    result_with_inputs = {
        **_RESULT,
        "inputs": [
            {"name": "Bus stops", "value": "3", "source": "data",
             "detail": "3 bus stop(s) linked to this road."},
            {"name": "Right-of-way", "value": "18.0 m", "source": "estimated",
             "detail": "Typical width for this type of road (not measured)."},
        ],
        "context": ["bus_route"],
    }
    p = build_prompt(result_with_inputs)
    assert "Bus stops" in p
    assert "3 bus stop(s)" in p
    assert "bus route" in p  # context flag rendered as plain words

    p_one = build_prompt_one(result_with_inputs, "balanced")
    assert "Bus stops" in p_one
    assert "3 bus stop(s)" in p_one


def test_build_prompt_includes_road_name():
    assert "Usman Road" in build_prompt(_RESULT)


def test_build_prompt_includes_option_ids_and_widths():
    p = build_prompt(_RESULT)
    assert "balanced" in p
    assert "traffic" in p
    assert "Footpath 2.5 m" in p


def test_build_prompt_lists_allowed_rule_ids():
    p = build_prompt(_RESULT)
    assert "footpath_min_width" in p
    assert "Rule IDs you may cite" in p


def test_build_prompt_includes_dropped_option():
    p = build_prompt(_RESULT)
    assert "Walking & shade" in p
    assert "Needs 20 m" in p


def test_build_prompt_includes_warnings():
    p = build_prompt(_RESULT)
    assert "ESTIMATE" in p


# ---------- unknown_citations ----------

def test_unknown_citations_detects_unknown_id():
    assert "irc_103_table2" in unknown_citations("See irc_103_table2.", {"footpath_min_width"})


def test_unknown_citations_ignores_known_ids():
    assert unknown_citations("See footpath_min_width.", {"footpath_min_width"}) == []


def test_unknown_citations_ignores_excluded_phrases():
    assert "road_class" not in unknown_citations("The road_class is secondary.", set())
    assert "one_way" not in unknown_citations("It is one_way.", set())


def test_unknown_citations_returns_sorted_list():
    result = unknown_citations("See z_rule and a_rule.", set())
    assert result == sorted(result)


# ---------- explain ----------

def test_explain_returns_empty_on_llm_error(monkeypatch):
    import modules.roads.design.explain as explain_mod
    from core.llm.client import LLMError

    def _fail(*a, **kw):
        raise LLMError("no server")

    monkeypatch.setattr(explain_mod, "chat_json", _fail)
    result = explain(_RESULT)
    assert result["explanations"] == {}
    assert result["comparison"] == ""
    assert any("unavailable" in w.lower() for w in result["warnings"])


def test_explain_returns_llm_text(monkeypatch):
    import modules.roads.design.explain as explain_mod

    monkeypatch.setattr(explain_mod, "chat_json", lambda *a, **kw: {
        "explanations": {
            "balanced": "A good balanced layout with wide footpaths.",
            "traffic": "Maximises traffic flow with wide lanes.",
        },
        "comparison": "Use balanced for pedestrian comfort.",
    })
    result = explain(_RESULT)
    assert result["explanations"]["balanced"] == "A good balanced layout with wide footpaths."
    assert result["explanations"]["traffic"] == "Maximises traffic flow with wide lanes."
    assert result["comparison"] == "Use balanced for pedestrian comfort."
    assert result["warnings"] == []


def test_explain_flags_unknown_rule_citations(monkeypatch):
    import modules.roads.design.explain as explain_mod

    monkeypatch.setattr(explain_mod, "chat_json", lambda *a, **kw: {
        "explanations": {"balanced": "See irc_103_clause4 for the footpath rule.",
                         "traffic": "Good for traffic."},
        "comparison": "Use balanced.",
    })
    result = explain(_RESULT)
    assert any("irc_103_clause4" in w for w in result["warnings"])
    assert "irc_103_clause4" in result["explanations"]["balanced"]  # text kept, warning added


def test_explain_known_rule_id_is_not_flagged(monkeypatch):
    import modules.roads.design.explain as explain_mod

    monkeypatch.setattr(explain_mod, "chat_json", lambda *a, **kw: {
        "explanations": {"balanced": "Rule footpath_min_width applies here.", "traffic": ""},
        "comparison": "",
    })
    result = explain(_RESULT)
    assert result["warnings"] == []


def test_explain_returns_empty_for_no_options():
    no_opts = {**_RESULT, "options": []}
    result = explain(no_opts)
    assert result == {"explanations": {}, "comparison": "", "warnings": []}


def test_explain_handles_missing_option_in_llm_response(monkeypatch):
    import modules.roads.design.explain as explain_mod

    # LLM only returns one option but there are two
    monkeypatch.setattr(explain_mod, "chat_json", lambda *a, **kw: {
        "explanations": {"balanced": "Good layout."},
        "comparison": "Use balanced.",
    })
    result = explain(_RESULT)
    assert result["explanations"]["balanced"] == "Good layout."
    assert result["explanations"]["traffic"] == ""  # missing -> empty string


# ---------- explain API endpoint ----------

def test_explain_endpoint_returns_design_plus_explanations(client):
    r = client.post("/api/roads/chennai/segments/1-2-0/design/explain", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    # Design fields are present
    assert "options" in body
    assert "row_m" in body
    assert "segment" in body
    # Explanation fields are present (may be empty if no LLM)
    assert "explanations" in body
    assert "comparison" in body
    assert "explanation_warnings" in body
    # If LLM not available, explanations is {} and explanation_warnings is non-empty
    assert isinstance(body["explanations"], dict)
    assert isinstance(body["explanation_warnings"], list)


def test_explain_endpoint_with_manual_width(client):
    r = client.post("/api/roads/chennai/segments/1-2-0/design/explain", json={"row_m": 24})
    assert r.status_code == 200
    assert r.json()["row_m"] == 24.0
    assert r.json()["width_source"] == "manual"


def test_explain_endpoint_validation_errors(client):
    assert client.post("/api/roads/chennai/segments/nope/design/explain", json={}).status_code == 404
    assert client.post("/api/roads/atlantis/segments/1-2-0/design/explain", json={}).status_code == 404
    assert client.post("/api/roads/chennai/segments/1-2-0/design/explain",
                       json={"context": ["earthquake"]}).status_code == 422
    assert client.post("/api/roads/chennai/segments/1-2-0/design/explain",
                       json={"row_m": 1}).status_code == 422


# ---------- M8: build_prompt_one + explain_one unit tests ----------

def test_build_prompt_one_includes_only_the_requested_option():
    p = build_prompt_one(_RESULT, "balanced")
    assert "balanced" in p
    assert "Footpath 2.5 m" in p
    # The other option's text should NOT be in the per-option prompt
    assert "traffic" not in p or p.index("balanced") < p.index("traffic")


def test_build_prompt_one_for_unknown_option_returns_empty():
    assert build_prompt_one(_RESULT, "nonexistent") == ""


def test_explain_one_returns_text_on_success(monkeypatch):
    import modules.roads.design.explain as explain_mod

    monkeypatch.setattr(explain_mod, "chat_json", lambda *a, **kw: {
        "explanation": "A balanced layout with wide footpaths and cycle tracks."
    })
    result = explain_one(_RESULT, "balanced")
    assert result["explanation"] == "A balanced layout with wide footpaths and cycle tracks."
    assert result["warnings"] == []


def test_explain_one_flags_unknown_rule_citations(monkeypatch):
    import modules.roads.design.explain as explain_mod

    monkeypatch.setattr(explain_mod, "chat_json", lambda *a, **kw: {
        "explanation": "See irc_103_clause4 for details."
    })
    result = explain_one(_RESULT, "balanced")
    assert any("irc_103_clause4" in w for w in result["warnings"])
    assert "irc_103_clause4" in result["explanation"]


def test_explain_one_returns_empty_on_llm_error(monkeypatch):
    import modules.roads.design.explain as explain_mod
    from core.llm.client import LLMError

    def _fail(*a, **kw):
        raise LLMError("no server")

    monkeypatch.setattr(explain_mod, "chat_json", _fail)
    result = explain_one(_RESULT, "balanced")
    assert result["explanation"] == ""
    assert any("unavailable" in w.lower() for w in result["warnings"])


def test_explain_one_returns_error_for_unknown_option():
    result = explain_one(_RESULT, "nonexistent")
    assert result["explanation"] == ""
    assert result["warnings"]


# ---------- M8: per-option explain endpoint ----------

def test_explain_option_endpoint_returns_explanation_and_warnings(client):
    r = client.post("/api/roads/chennai/segments/1-2-0/design/explain/traffic",
                    json={"row_m": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "explanation" in body
    assert "warnings" in body
    assert isinstance(body["explanation"], str)
    assert isinstance(body["warnings"], list)


def test_explain_option_endpoint_404_on_unknown_option(client):
    r = client.post("/api/roads/chennai/segments/1-2-0/design/explain/nonexistent", json={})
    assert r.status_code == 404


def test_explain_option_endpoint_404_on_unknown_segment(client):
    r = client.post("/api/roads/chennai/segments/nope/design/explain/traffic", json={})
    assert r.status_code == 404


def test_explain_option_endpoint_validates_context(client):
    r = client.post("/api/roads/chennai/segments/1-2-0/design/explain/traffic",
                    json={"context": ["earthquake"]})
    assert r.status_code == 422
