"""Local embeddings for document chunks, using sentence-transformers (all-MiniLM-L6-v2).

Entirely local: the model runs on this machine, nothing is sent anywhere. The model itself
(~90 MB) downloads once from Hugging Face the first time this is used, then is cached by
sentence-transformers in the user's profile; after that, no network is needed.
"""
import numpy as np

from core.rules import documents

MODEL_NAME = "all-MiniLM-L6-v2"

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # heavy import; deferred
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    vecs = _get_model().encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    return np.asarray(vecs, dtype=np.float32)


def embed_document(topic: str, source_id: str) -> dict:
    chunks = documents.load_chunks(topic, source_id)
    if not chunks:
        raise ValueError(f"No chunks for '{source_id}': ingest the document first")
    vecs = embed_texts([c["text"] for c in chunks])
    np.save(documents.embeddings_path(topic, source_id), vecs)
    return {"source_id": source_id, "chunks_embedded": len(chunks), "dims": int(vecs.shape[1]) if len(vecs) else 0}


def load_embeddings(topic: str, source_id: str) -> np.ndarray | None:
    p = documents.embeddings_path(topic, source_id)
    return np.load(p) if p.exists() else None
