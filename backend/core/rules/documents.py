r"""Standards documents: PDF -> text chunks with page numbers -> (in embeddings.py) vectors.

Ported from the earlier urban_city project's ingest.py, adapted to this repo's storage layout.
Chunks (and later their embeddings) live under DATA_DIR\documents\<topic>\<source_id>\, next to
the registered raw PDF; nothing here touches a road or a layer.
"""
import json
import re
from pathlib import Path

from pypdf import PdfReader

from core.config import settings

CHUNK_SIZE = 1200     # characters per chunk
CHUNK_OVERLAP = 200   # characters of overlap between consecutive chunks


def doc_dir(topic: str, source_id: str) -> Path:
    return settings.data_dir / "documents" / topic / source_id


def chunks_path(topic: str, source_id: str) -> Path:
    return doc_dir(topic, source_id) / "chunks.json"


def embeddings_path(topic: str, source_id: str) -> Path:
    return doc_dir(topic, source_id) / "embeddings.npy"


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + size, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end == n:
            break
        start = end - overlap
    return chunks


def extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """(page_number, cleaned_text) for every page, 1-based. Pages that fail to extract (e.g. a
    scanned image with no text layer) come back with empty text, not an error."""
    reader = PdfReader(str(pdf_path))
    out = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # a single bad page must not abort the whole document
            text = ""
        out.append((i, clean_text(text)))
    return out


def ingest(source: dict) -> dict:
    """Chunk a registered PDF and write chunks.json. Re-running replaces it cleanly."""
    pdf_path: Path = source["abs_path"]
    topic, source_id = source["topic"], source["source_id"]
    pages = extract_pages(pdf_path)

    chunks, chunk_id = [], 0
    for page_num, text in pages:
        if not text:
            continue
        for piece in chunk_text(text):
            chunks.append({"id": chunk_id, "source_id": source_id, "page": page_num, "text": piece})
            chunk_id += 1

    d = doc_dir(topic, source_id)
    d.mkdir(parents=True, exist_ok=True)
    tmp = chunks_path(topic, source_id).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(chunks_path(topic, source_id))
    embeddings_path(topic, source_id).unlink(missing_ok=True)  # stale after a re-ingest

    pages_with_text = sum(1 for _, t in pages if t)
    return {
        "source_id": source_id, "pages": len(pages), "pages_with_text": pages_with_text,
        "chunks": len(chunks), "chars": sum(len(c["text"]) for c in chunks),
    }


def load_chunks(topic: str, source_id: str) -> list[dict]:
    p = chunks_path(topic, source_id)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))
