"""End to end through the HTTP API. Every test that writes a rule uses the `rules_dir` fixture,
so nothing here ever touches the repo's real rules/active or rules/proposed folders.
LLM calls are mocked (extraction, relevance judging) so these tests are fast and deterministic
and do not need a running Ollama."""
import io

import pytest

from core.llm import client as llm
from tests.conftest import SAMPLES, make_pdf

RULES = "/api/rules"


def upload_pdf(client, tmp_path, name: str, pages: list[str], **form) -> dict:
    p = make_pdf(tmp_path / name, pages)
    form.setdefault("authority", "active")
    r = client.post(f"{RULES}/documents/upload", files={"file": (name, io.BytesIO(p.read_bytes()), "application/pdf")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


# Deliberately unique wording (not shared with any other test file): with a shared session
# catalog, near-duplicate text across test files makes retrieval ranking ties order-dependent.
FOOTPATH_TEXT = "5.1 A quoritan footpath shall have a minimum width of 1.8 m in residential areas."


def mock_extraction(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda prompt, system=None, **k: (
        {"rules": [{"element": "footpath", "min_m": 1.8, "clause": "5.1", "quote": FOOTPATH_TEXT,
                   "statement": "Footpaths must be at least 1.8 m wide."}]}
        if "extract" in system.lower() else {"applies": True, "reason": "matches"}
    ))


# ---------- placeholder rules (real repo data, read-only) ----------

def test_list_rules_includes_the_real_placeholder_set(client):
    rules = client.get(RULES).json()
    ids = {r["rule_id"] for r in rules}
    assert "footpath_min_width" in ids and "bus_bay_min_width" in ids
    footpath = next(r for r in rules if r["rule_id"] == "footpath_min_width")
    assert footpath["source"]["authority"] == "placeholder"
    assert footpath["status"] == "active"


def test_get_one_rule(client):
    r = client.get(f"{RULES}/footpath_min_width").json()
    assert r["element"] == "footpath" and r["value"]["min_m"] == 1.8
    assert client.get(f"{RULES}/nope").status_code == 404


def test_filter_by_status_and_category(client):
    active = client.get(RULES, params={"status": "active"}).json()
    assert all(r["status"] == "active" for r in active)
    dims = client.get(RULES, params={"category": "dimension"}).json()
    assert all(r["category"] == "dimension" for r in dims)


# ---------- document upload / ingest ----------

def test_upload_ingests_immediately(client, rules_dir, tmp_path):
    res = upload_pdf(client, tmp_path, "doc1.pdf", [FOOTPATH_TEXT], authority="active",
                     title="SAMPLE Test Standard", doc_year=2026, jurisdiction="Test")
    assert res["ingest"]["chunks"] >= 1 and res["ingest"]["pages"] == 1

    docs = client.get(f"{RULES}/documents/list").json()
    doc = next(d for d in docs if d["source_id"] == res["source_id"])
    assert doc["authority"] == "active" and doc["doc_year"] == 2026 and doc["jurisdiction"] == "Test"
    assert doc["embedded"] is False and doc["chunks"] >= 1


def test_sample_title_keeps_the_sample_label(client, rules_dir, tmp_path):
    res = upload_pdf(client, tmp_path, "SAMPLE_doc.pdf", [FOOTPATH_TEXT], title="A Nice Title")
    doc = next(d for d in client.get(f"{RULES}/documents/list").json() if d["source_id"] == res["source_id"])
    assert doc["name"].startswith("A Nice Title") and "SAMPLE" in doc["name"] and doc["sample"] is True


def test_upload_rejects_non_pdf(client, rules_dir):
    r = client.post(f"{RULES}/documents/upload", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"))},
                    data={"authority": "active"})
    assert r.status_code == 422 and "PDF" in r.json()["detail"]


def test_upload_rejects_bad_authority(client, rules_dir, tmp_path):
    p = make_pdf(tmp_path / "d.pdf", [FOOTPATH_TEXT])
    r = client.post(f"{RULES}/documents/upload", files={"file": ("d.pdf", io.BytesIO(p.read_bytes()))},
                    data={"authority": "definitely"})
    assert r.status_code == 422


def test_embed_then_extract_then_review(client, rules_dir, tmp_path, monkeypatch):
    mock_extraction(monkeypatch)
    res = upload_pdf(client, tmp_path, "doc2.pdf", [FOOTPATH_TEXT])
    sid = res["source_id"]

    embed = client.post(f"{RULES}/documents/{sid}/embed").json()
    assert embed["chunks_embedded"] >= 1

    extracted = client.post(f"{RULES}/documents/{sid}/extract").json()
    assert extracted["stats"]["rules_proposed"] == 1
    proposed = extracted["rules"][0]
    assert proposed["status"] == "proposed" and proposed["source"]["quote"] == FOOTPATH_TEXT
    assert proposed["source"]["doc_id"] == sid

    listed = client.get(RULES, params={"status": "proposed"}).json()
    assert any(r["rule_id"] == proposed["rule_id"] for r in listed)

    approved = client.post(f"{RULES}/{proposed['rule_id']}/approve").json()
    assert approved["status"] == "active" and approved["source"]["authority"] == "primary"
    assert client.get(f"{RULES}/{proposed['rule_id']}").json()["status"] == "active"


def test_reject_removes_a_proposed_rule(client, rules_dir, tmp_path, monkeypatch):
    mock_extraction(monkeypatch)
    res = upload_pdf(client, tmp_path, "doc3.pdf", [FOOTPATH_TEXT])
    client.post(f"{RULES}/documents/{res['source_id']}/embed")
    extracted = client.post(f"{RULES}/documents/{res['source_id']}/extract").json()
    rid = extracted["rules"][0]["rule_id"]

    r = client.post(f"{RULES}/{rid}/reject")
    assert r.status_code == 200
    assert client.get(f"{RULES}/{rid}").status_code == 404


def test_approve_reject_unknown_or_already_active(client, rules_dir):
    assert client.post(f"{RULES}/nope/approve").status_code == 422
    assert client.post(f"{RULES}/nope/reject").status_code == 422
    # The real placeholder rule is already active (read-only in this test, no rules_dir writes needed).
    r = client.post(f"{RULES}/footpath_min_width/approve")
    assert r.status_code == 422


def test_extract_requires_ingestion_first(client, rules_dir, tmp_path):
    p = make_pdf(tmp_path / "notyet.pdf", [FOOTPATH_TEXT])
    sid = f"file-standards-notyet-{'0' * 10}"  # never actually registered/ingested
    r = client.post(f"{RULES}/documents/{sid}/extract")
    assert r.status_code == 404  # unknown source


def test_extract_refuses_a_superseded_document(client, rules_dir, tmp_path):
    res = upload_pdf(client, tmp_path, "old.pdf", [FOOTPATH_TEXT], authority="superseded")
    r = client.post(f"{RULES}/documents/{res['source_id']}/extract")
    assert r.status_code == 422 and "superseded" in r.json()["detail"]


def test_extract_with_no_rules_found_returns_empty(client, rules_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": []})
    res = upload_pdf(client, tmp_path, "empty.pdf", ["The minimum width shall be stated elsewhere."])
    r = client.post(f"{RULES}/documents/{res['source_id']}/extract").json()
    assert r["rules"] == [] and r["stats"]["rules_proposed"] == 0


# ---------- document search ----------

def test_document_search_with_relevance(client, rules_dir, tmp_path, monkeypatch):
    mock_extraction(monkeypatch)
    res = upload_pdf(client, tmp_path, "doc4.pdf", [FOOTPATH_TEXT])
    client.post(f"{RULES}/documents/{res['source_id']}/embed")

    r = client.post(f"{RULES}/documents/search", json={"query": "minimum quoritan width"}).json()
    assert r["found"] is True and r["best"]["source_id"] == res["source_id"]
    assert r["best"]["page"] == 1


def test_document_search_no_applicable_provision(client, rules_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda prompt, system=None, **k: (
        {"applies": False, "reason": "not about this"}
    ))
    upload_pdf(client, tmp_path, "doc5.pdf", [FOOTPATH_TEXT])
    r = client.post(f"{RULES}/documents/search", json={"query": "parking requirements for malls"}).json()
    assert r["found"] is False and "No applicable provision" in r["message"]


# ---------- expert-rules sheet ----------

@pytest.fixture
def expert_source(client, rules_dir):
    r = client.post("/api/inbox/chennai/upload",
                    files={"file": ("SAMPLE_expert_rules.csv", (SAMPLES / "SAMPLE_expert_rules.csv").open("rb"))},
                    data={"topic": "roads"})
    assert r.status_code == 200, r.text
    return r.json()["source_id"]


def test_expert_sheet_preview_and_import(client, expert_source):
    pv = client.get(f"{RULES}/expert-sheet/{expert_source}/preview").json()
    assert pv["mapping"] == {"if_text": "If", "then_text": "Then", "because_text": "Because", "source_text": "Source"}
    assert pv["preview"]["row_count"] == 4

    imported = client.post(f"{RULES}/expert-sheet/{expert_source}/import", json={"mapping": pv["mapping"]}).json()
    assert imported["imported"] == 4

    rules = client.get(RULES, params={"category": "conditional"}).json()
    assert any(r["rule_id"] in imported["rule_ids"] for r in rules)


def test_expert_sheet_import_with_bad_mapping(client, rules_dir):
    r = client.post("/api/inbox/chennai/upload", files={"file": ("bad.csv", io.BytesIO(b"Then\nX\n"))}, data={"topic": "roads"})
    sid = r.json()["source_id"]
    resp = client.post(f"{RULES}/expert-sheet/{sid}/import", json={"mapping": {"then_text": "Then"}})
    assert resp.status_code == 422 and "If" in resp.json()["detail"]


def test_expert_sheet_unknown_source(client, rules_dir):
    assert client.get(f"{RULES}/expert-sheet/nope/preview").status_code == 404
