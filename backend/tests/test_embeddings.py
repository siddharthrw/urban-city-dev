"""Uses the real local sentence-transformers model (cached after the first run on this machine;
the very first run of these tests on a fresh machine needs internet to download it once)."""
import numpy as np
import pytest

from core.inbox import files
from core.rules import documents, embeddings
from tests.conftest import make_pdf


def test_embed_texts_shape_and_normalisation():
    vecs = embeddings.embed_texts(["a footpath is 1.8 m wide", "a cycle track is 2.0 m wide"])
    assert vecs.shape == (2, 384)
    assert vecs.dtype == np.float32
    # normalize_embeddings=True -> every vector is unit length.
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-4)


def test_embed_texts_empty_list():
    vecs = embeddings.embed_texts([])
    assert vecs.shape == (0, 384)


def test_similar_sentences_score_higher_than_unrelated_ones():
    a, b, c = embeddings.embed_texts([
        "The minimum footpath width shall be 1.8 m.",
        "Footpaths must be at least 1.8 metres wide.",
        "The capital of France is Paris.",
    ])
    assert float(a @ b) > float(a @ c)


@pytest.fixture
def embedded_doc(world, tmp_path):
    p = make_pdf(tmp_path / "doc.pdf", ["The minimum footpath width shall be 1.8 m wide."])
    from core.store import catalog
    sid = files.save_upload(p.read_bytes(), "doc.pdf", topic="standards", authority="active")
    src = catalog.get_source(sid)
    documents.ingest(src)
    return src


def test_embed_document_writes_a_file_matching_chunk_count(embedded_doc):
    rep = embeddings.embed_document("standards", embedded_doc["source_id"])
    chunks = documents.load_chunks("standards", embedded_doc["source_id"])
    assert rep["chunks_embedded"] == len(chunks) == 1
    assert rep["dims"] == 384


def test_load_embeddings_round_trips(embedded_doc):
    embeddings.embed_document("standards", embedded_doc["source_id"])
    vecs = embeddings.load_embeddings("standards", embedded_doc["source_id"])
    assert vecs.shape == (1, 384)


def test_load_embeddings_before_embedding_is_none(embedded_doc):
    assert embeddings.load_embeddings("standards", embedded_doc["source_id"]) is None


def test_embed_document_with_no_chunks_raises(world):
    with pytest.raises(ValueError, match="ingest the document first"):
        embeddings.embed_document("standards", "no-such-doc")


def test_reembedding_overwrites_the_file(embedded_doc):
    embeddings.embed_document("standards", embedded_doc["source_id"])
    embeddings.embed_document("standards", embedded_doc["source_id"])  # must not error or duplicate
    vecs = embeddings.load_embeddings("standards", embedded_doc["source_id"])
    assert vecs.shape == (1, 384)
