import pytest

from core.llm import client as llm
from core.rules import extract

CHUNK = {"id": 0, "source_id": "doc-1", "page": 5,
        "text": "5.1 The minimum width of a footpath shall be 1.8 m in residential areas. "
                "Footpaths shall be kept free of obstructions."}


def test_keyword_filter_keeps_dimension_looking_chunks_only():
    dimension_chunk = {"id": 0, "page": 1, "text": "The minimum width shall be 1.8 m."}
    other_chunk = {"id": 1, "page": 2, "text": "This chapter introduces the purpose of the standard."}
    kept = extract.relevant_chunks([dimension_chunk, other_chunk])
    assert kept == [dimension_chunk]


def test_extract_from_chunk_accepts_a_grounded_quote(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": [{
        "element": "footpath", "min_m": 1.8, "max_m": None, "clause": "5.1",
        "quote": "The minimum width of a footpath shall be 1.8 m in residential areas.",
        "statement": "Footpaths must be at least 1.8 m wide.",
    }]})
    proposals = extract.extract_from_chunk(CHUNK)
    assert len(proposals) == 1
    p = proposals[0]
    assert p["element"] == "footpath" and p["value"] == {"min_m": 1.8} and p["clause"] == "5.1"
    assert p["page"] == 5


def test_extract_from_chunk_drops_a_hallucinated_quote(monkeypatch):
    """The LLM claims a number that is NOT in the source text: this must be dropped, not trusted."""
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": [{
        "element": "footpath", "min_m": 2.4,  # not stated in CHUNK at all
        "quote": "Footpaths shall never be narrower than 2.4 metres under any circumstances.",
        "statement": "Footpaths must be at least 2.4 m wide.",
    }]})
    assert extract.extract_from_chunk(CHUNK) == []


def test_extract_from_chunk_drops_unknown_element(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": [{
        "element": "sidewalk",  # not one of the recognised elements
        "min_m": 1.8, "quote": "The minimum width of a footpath shall be 1.8 m in residential areas.",
    }]})
    assert extract.extract_from_chunk(CHUNK) == []


def test_extract_from_chunk_drops_rule_with_no_number(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": [{
        "element": "footpath", "min_m": None, "max_m": None,
        "quote": "The minimum width of a footpath shall be 1.8 m in residential areas.",
    }]})
    assert extract.extract_from_chunk(CHUNK) == []


def test_extract_from_chunk_handles_empty_and_malformed_output(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": []})
    assert extract.extract_from_chunk(CHUNK) == []
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": "not a list"})
    assert extract.extract_from_chunk(CHUNK) == []
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": ["not a dict"]})
    assert extract.extract_from_chunk(CHUNK) == []


def test_extract_from_chunk_survives_llm_failure(monkeypatch):
    def boom(*a, **k):
        raise llm.LLMError("no Ollama")
    monkeypatch.setattr(llm, "chat_json", boom)
    assert extract.extract_from_chunk(CHUNK) == []


def test_quote_grounding_tolerates_whitespace_noise():
    noisy_quote = "The   minimum width of  a footpath\nshall be 1.8 m in residential areas."
    assert extract._quote_is_grounded(noisy_quote, CHUNK["text"])


def test_quote_grounding_rejects_unrelated_text():
    assert not extract._quote_is_grounded("Bus bays shall be 3.0 m wide.", CHUNK["text"])


def test_quote_grounding_rejects_empty_quote():
    assert not extract._quote_is_grounded("", CHUNK["text"])


def test_extract_document_assigns_stable_unique_ids_and_grounded_source(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": [{
        "element": "footpath", "min_m": 1.8, "clause": "5.1",
        "quote": "The minimum width of a footpath shall be 1.8 m in residential areas.",
        "statement": "Footpaths must be at least 1.8 m wide.",
    }]})
    source = {"source_id": "doc-abcdefgh12", "topic": "standards", "name": "SAMPLE Standard"}
    monkeypatch.setattr("core.rules.documents.load_chunks", lambda topic, sid: [CHUNK])

    rules, stats = extract.extract_document(source)
    assert stats == {"chunks_total": 1, "chunks_scanned": 1, "rules_proposed": 1}
    assert len(rules) == 1
    r = rules[0]
    assert r["status"] == "proposed" and r["category"] == "dimension"
    assert r["source"]["authority"] == "primary"
    assert r["source"]["doc_id"] == "doc-abcdefgh12" and r["source"]["page"] == 5
    assert r["source"]["quote"] in CHUNK["text"]


def test_extract_document_dedupes_rule_ids_for_the_same_element_and_page(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"rules": [
        {"element": "footpath", "min_m": 1.8, "quote": "The minimum width of a footpath shall be 1.8 m in residential areas."},
        {"element": "footpath", "max_m": 4.0, "quote": "Footpaths shall be kept free of obstructions."},
    ]})
    source = {"source_id": "doc-abcdefgh12", "topic": "standards", "name": "SAMPLE Standard"}
    monkeypatch.setattr("core.rules.documents.load_chunks", lambda topic, sid: [CHUNK])
    rules, _ = extract.extract_document(source)
    assert len({r["rule_id"] for r in rules}) == 2  # distinct ids despite same element+page


def test_extract_document_skips_non_matching_chunks(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: calls.append(1) or {"rules": []})
    intro = {"id": 1, "page": 1, "text": "This standard covers urban street design in general terms."}
    monkeypatch.setattr("core.rules.documents.load_chunks", lambda topic, sid: [CHUNK, intro])
    source = {"source_id": "doc-x", "topic": "standards", "name": "X"}
    extract.extract_document(source)
    assert len(calls) == 1  # only the keyword-matching chunk was sent to the LLM
