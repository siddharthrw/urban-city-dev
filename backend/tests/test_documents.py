import pytest

from core.inbox import files
from core.rules import documents
from tests.conftest import make_pdf


@pytest.fixture
def doc_source(world, tmp_path):
    p = make_pdf(tmp_path / "doc.pdf", [
        "Page one. " + ("The minimum footpath width shall be 1.8 m. " * 30),
        "Page two about cycle tracks and lanes.",
        "",  # a page with (nearly) no text, simulating a scanned/blank page
    ])
    from core.store import catalog
    sid = files.save_upload(p.read_bytes(), "doc.pdf", topic="standards",
                            authority="active", doc_year=2026, jurisdiction="Test")
    return catalog.get_source(sid)


def test_clean_text_collapses_whitespace_and_nulls():
    assert documents.clean_text("a\x00b   c\n\n\n\nd") == "a b c\n\nd"


def test_chunk_text_respects_size_and_overlap():
    text = "x" * 3000
    chunks = documents.chunk_text(text, size=1000, overlap=200)
    assert all(len(c) <= 1000 for c in chunks)
    assert len(chunks) >= 3
    # Consecutive chunks actually overlap.
    assert chunks[0][-100:] in text and chunks[1][:100] in text


def test_chunk_text_short_input_is_one_chunk():
    assert documents.chunk_text("short text", size=1000, overlap=200) == ["short text"]


def test_chunk_text_empty_input():
    assert documents.chunk_text("") == []


def test_extract_pages_gives_page_numbers_starting_at_one(doc_source):
    pages = documents.extract_pages(doc_source["abs_path"])
    assert len(pages) == 3
    assert pages[0][0] == 1 and "footpath" in pages[0][1].lower()
    assert pages[1][0] == 2 and "cycle" in pages[1][1].lower()
    assert pages[2][0] == 3  # the blank page still gets a page number


def test_ingest_writes_chunks_with_page_numbers(doc_source):
    rep = documents.ingest(doc_source)
    assert rep["pages"] == 3
    assert rep["chunks"] > 1  # page one's long repeated text splits into multiple chunks

    chunks = documents.load_chunks("standards", doc_source["source_id"])
    assert chunks == sorted(chunks, key=lambda c: (c["page"], c["id"]))
    assert all(c["source_id"] == doc_source["source_id"] for c in chunks)
    assert any(c["page"] == 1 for c in chunks) and any(c["page"] == 2 for c in chunks)
    assert not any(c["page"] == 3 for c in chunks)  # the blank page contributed no chunks


def test_reingesting_replaces_chunks_cleanly(doc_source):
    documents.ingest(doc_source)
    first = documents.load_chunks("standards", doc_source["source_id"])
    rep2 = documents.ingest(doc_source)
    second = documents.load_chunks("standards", doc_source["source_id"])
    assert rep2["chunks"] == len(first) == len(second)


def test_load_chunks_for_uningested_document_is_empty(world):
    assert documents.load_chunks("standards", "no-such-doc") == []


def test_document_authority_and_metadata_recorded(doc_source):
    assert doc_source["authority"] == "active"
    assert doc_source["doc_year"] == 2026
    assert doc_source["jurisdiction"] == "Test"
    assert doc_source["topic"] == "standards"
