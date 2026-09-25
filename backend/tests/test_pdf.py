"""Unit and endpoint tests for the PDF export module (pdf.py)."""
import pytest

from modules.roads.design.pdf import build_pdf

_RESULT = {
    "row_m": 18.0, "row_cm": 1800, "road_class": "secondary", "oneway": False,
    "width_source": "estimated", "context": [],
    "segment": {"seg_id": "1-2-0", "name": "Usman Road",
                "road_width_m": 18.0, "road_width_source": "estimated"},
    "options": [
        {
            "option_id": "balanced",
            "name": "Balanced (cycle track + shade)",
            "summary": "Footpaths, shade trees and a cycle track on both sides.",
            "elements": [
                {"kind": "footpath", "label": "Footpath", "side": "left",
                 "width_cm": 200, "width_m": 2.0, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
                {"kind": "tree_strip", "label": "Trees", "side": "left",
                 "width_cm": 150, "width_m": 1.5, "rule_ids": [], "fallback_minimum": False},
                {"kind": "lane", "label": "Lane", "side": "centre",
                 "width_cm": 350, "width_m": 3.5, "rule_ids": [], "fallback_minimum": False},
                {"kind": "lane", "label": "Lane", "side": "centre",
                 "width_cm": 350, "width_m": 3.5, "rule_ids": [], "fallback_minimum": False},
                {"kind": "tree_strip", "label": "Trees", "side": "right",
                 "width_cm": 150, "width_m": 1.5, "rule_ids": [], "fallback_minimum": False},
                {"kind": "footpath", "label": "Footpath", "side": "right",
                 "width_cm": 200, "width_m": 2.0, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
            ],
            "omitted": [{"kind": "median", "reason": "Median left out so the option fits in 18 m."}],
            "notes": ["Lanes reduced from 4 to 2."],
            "metrics": {"lanes": 2, "carriageway_m": 7.0, "lane_width_m": 3.5, "footpath_m": 2.0,
                        "has_cycle_track": False, "has_trees": True, "has_bus_bay": False, "has_median": False},
            "rule_ids": ["footpath_min_width"],
            "total_cm": 1400, "uses_fallback_minimums": False,
        },
        {
            "option_id": "traffic",
            "name": "Traffic priority",
            "summary": "As many lanes as the width allows.",
            "elements": [
                {"kind": "footpath", "label": "Footpath", "side": "left",
                 "width_cm": 200, "width_m": 2.0, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
                {"kind": "lane", "label": "Lane", "side": "centre",
                 "width_cm": 700, "width_m": 7.0, "rule_ids": [], "fallback_minimum": False},
                {"kind": "footpath", "label": "Footpath", "side": "right",
                 "width_cm": 200, "width_m": 2.0, "rule_ids": ["footpath_min_width"], "fallback_minimum": False},
            ],
            "omitted": [], "notes": [],
            "metrics": {"lanes": 2, "carriageway_m": 7.0, "lane_width_m": 3.5, "footpath_m": 2.0,
                        "has_cycle_track": False, "has_trees": False, "has_bus_bay": False, "has_median": False},
            "rule_ids": ["footpath_min_width"],
            "total_cm": 1100, "uses_fallback_minimums": False,
        },
    ],
    "dropped": [{"option_id": "walking", "name": "Walking & shade", "reason": "Needs 20 m, road is 18 m."}],
    "warnings": [
        "The road width is an ESTIMATE (a typical width for this type of road).",
        "Dimensions come from PLACEHOLDER rules (UNCITED guesses).",
    ],
    "rules": {
        "footpath_min_width": {
            "statement": "UNCITED placeholder: footpaths at least 1.8 m.",
            "authority": "placeholder",
            "source": "Placeholder (uncited)",
            "quote": None,
            "page": None,
        }
    },
}


def test_build_pdf_returns_bytes():
    b = build_pdf(_RESULT)
    assert isinstance(b, bytes)


def test_build_pdf_starts_with_pdf_header():
    b = build_pdf(_RESULT)
    assert b[:4] == b"%PDF"


def test_build_pdf_is_substantial():
    b = build_pdf(_RESULT)
    assert len(b) > 1_500  # fpdf2 compresses content; a real multi-element PDF is above this


def test_build_pdf_with_explanations():
    exps = {
        "explanations": {
            "balanced": "This balanced layout provides good footpaths and shade.",
            "traffic": "This layout prioritises vehicle throughput.",
        },
        "comparison": "The balanced option is recommended for pedestrian comfort.",
    }
    b = build_pdf(_RESULT, exps)
    assert b[:4] == b"%PDF"
    assert len(b) > 1_500


def test_build_pdf_no_options():
    no_opts = {**_RESULT, "options": [], "dropped": [
        {"option_id": "balanced", "name": "Balanced", "reason": "Needs 20 m."},
    ]}
    b = build_pdf(no_opts)
    assert b[:4] == b"%PDF"


def test_build_pdf_no_warnings():
    clean = {**_RESULT, "warnings": []}
    b = build_pdf(clean)
    assert b[:4] == b"%PDF"


def test_build_pdf_with_context():
    ctx = {**_RESULT, "context": ["bus_route", "school_nearby"]}
    b = build_pdf(ctx)
    assert b[:4] == b"%PDF"


# ---------- PDF endpoint ----------

def test_pdf_endpoint_returns_pdf_bytes(client):
    r = client.get("/api/roads/chennai/segments/1-2-0/design/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_pdf_endpoint_content_disposition(client):
    r = client.get("/api/roads/chennai/segments/1-2-0/design/pdf")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ".pdf" in r.headers.get("content-disposition", "")


def test_pdf_endpoint_with_manual_width(client):
    r = client.get("/api/roads/chennai/segments/1-2-0/design/pdf?row_m=24")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_pdf_endpoint_with_context(client):
    r = client.get("/api/roads/chennai/segments/1-2-0/design/pdf?context=bus_route&context=school_nearby")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_pdf_endpoint_unknown_segment(client):
    assert client.get("/api/roads/chennai/segments/nope/design/pdf").status_code == 404


def test_pdf_endpoint_unknown_city(client):
    assert client.get("/api/roads/atlantis/segments/1-2-0/design/pdf").status_code == 404


def test_pdf_endpoint_invalid_width(client):
    assert client.get("/api/roads/chennai/segments/1-2-0/design/pdf?row_m=0.5").status_code == 422


def test_pdf_endpoint_invalid_context(client):
    assert client.get("/api/roads/chennai/segments/1-2-0/design/pdf?context=earthquake").status_code == 422
