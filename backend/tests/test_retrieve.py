import pytest

from core.inbox import files
from core.llm import client as llm
from core.rules import documents, embeddings, retrieve
from tests.conftest import make_pdf


def _make_doc(tmp_path, name: str, text: str, *, authority: str):
    p = make_pdf(tmp_path / name, [text])
    from core.store import catalog
    sid = files.save_upload(p.read_bytes(), name, topic="standards", authority=authority)
    src = catalog.get_source(sid)
    documents.ingest(src)
    embeddings.embed_document("standards", sid)
    return src


@pytest.fixture(scope="module")
def two_docs(world, tmp_path_factory):
    # Module-scoped and read-only from every test's point of view: with a shared session
    # catalog, a function-scoped version would create a fresh near-duplicate document per test
    # and pile them up, making "the top hit is THIS test's document" an order-dependent guess.
    tmp_path = tmp_path_factory.mktemp("two_docs")
    current = _make_doc(tmp_path, "current.pdf",
                        "A vintangular footpath shall have a minimum width of 1.8 m in residential areas.",
                        authority="active")
    old = _make_doc(tmp_path, "old.pdf",
                    "A vintangular footpath shall have a minimum width of 1.2 m in residential areas.",
                    authority="superseded")
    return current, old


def test_search_finds_the_relevant_chunk(two_docs):
    current, _ = two_docs
    hits = retrieve.search("What is the minimum vintangular footpath width?", topic="standards", k=5)
    assert hits and hits[0].source_id == current["source_id"]
    assert "1.8" in hits[0].text


def test_superseded_documents_are_never_returned(two_docs):
    current, old = two_docs
    hits = retrieve.search("What is the minimum vintangular footpath width?", topic="standards", k=10)
    assert all(h.source_id != old["source_id"] for h in hits)
    assert any(h.source_id == current["source_id"] for h in hits)


def test_search_skips_a_document_that_has_not_been_embedded(world, tmp_path):
    # A uniquely-worded PDF: it would be the top hit for its own query if search() didn't skip it.
    p = make_pdf(tmp_path / "unembedded.pdf", ["A zorbaxial footpath conduit shall be 1.8 m wide."])
    from core.store import catalog
    sid = files.save_upload(p.read_bytes(), "unembedded.pdf", topic="standards", authority="active")
    documents.ingest(catalog.get_source(sid))  # ingested but NOT embedded
    hits = retrieve.search("zorbaxial footpath conduit width", topic="standards")
    assert all(h.source_id != sid for h in hits)


def test_judge_relevance_true(two_docs, monkeypatch):
    current, _ = two_docs
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"applies": True, "reason": "It states the width."})
    hit = retrieve.search("minimum vintangular footpath width", topic="standards")[0]
    applies, reason = retrieve.judge_relevance("minimum vintangular footpath width", hit)
    assert applies and reason == "It states the width."


def test_judge_relevance_false(two_docs, monkeypatch):
    current, _ = two_docs
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"applies": False, "reason": "Unrelated."})
    hit = retrieve.search("minimum vintangular footpath width", topic="standards")[0]
    applies, reason = retrieve.judge_relevance("something else entirely", hit)
    assert not applies and reason == "Unrelated."


def test_judge_relevance_fails_open_when_llm_unreachable(two_docs, monkeypatch):
    current, _ = two_docs

    def boom(*a, **k):
        raise llm.LLMError("no Ollama")
    monkeypatch.setattr(llm, "chat_json", boom)
    hit = retrieve.search("minimum vintangular footpath width", topic="standards")[0]
    applies, reason = retrieve.judge_relevance("minimum vintangular footpath width", hit)
    assert applies is True and "unavailable" in reason


def test_search_with_relevance_returns_best_when_it_applies(two_docs, monkeypatch):
    current, _ = two_docs
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"applies": True, "reason": "matches"})
    res = retrieve.search_with_relevance("minimum vintangular footpath width", topic="standards")
    assert res["found"] is True and res["message"] is None
    assert res["best"].source_id == current["source_id"]


def test_search_with_relevance_says_no_applicable_provision_when_nothing_applies(two_docs, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"applies": False, "reason": "not about this"})
    res = retrieve.search_with_relevance("how many parking spaces for a mall", topic="standards")
    assert res["found"] is False
    assert res["best"] is None
    assert res["message"] == "No applicable provision found in the ingested documents."


def test_search_with_relevance_checks_only_the_top_n(two_docs, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: calls.append(1) or {"applies": False, "reason": "x"})
    retrieve.search_with_relevance("vintangular footpath", topic="standards", k=5, check_top=1)
    assert len(calls) == 1


def test_search_with_relevance_stops_at_the_first_applicable_hit(two_docs, monkeypatch):
    """If the first checked hit applies, later ones are still checked (so the UI can show them),
    but `best` is the first one that applies, not necessarily the highest raw score."""
    current, _ = two_docs
    responses = iter([{"applies": True, "reason": "first"}, {"applies": True, "reason": "second"}])
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: next(responses))
    res = retrieve.search_with_relevance("vintangular footpath", topic="standards", check_top=2)
    assert res["best"] is res["checked"][0]["hit"]
