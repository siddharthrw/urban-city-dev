r"""Find the passage that backs a claim, across every ingested standards document.

Two fixes over the earlier urban_city project this is ported from:
  1. Superseded documents are EXCLUDED, not just down-ranked. They can never be retrieved as
     a citation (non-negotiable #4), so a caller can't accidentally cite one even if it scores
     highest on similarity.
  2. A relevance check: the top similarity match is not assumed to apply. judge_relevance() asks
     the LLM whether the retrieved text actually answers the query, and search() reports
     "no applicable provision found" rather than a plausible-looking but wrong citation.
"""
from dataclasses import dataclass

import numpy as np

from core.llm import client as llm
from core.rules import documents, embeddings
from core.store import catalog


@dataclass(frozen=True)
class Hit:
    score: float
    source_id: str
    doc_title: str
    page: int
    text: str
    chunk_id: int


def _active_documents(topic: str) -> list[dict]:
    return [s for s in catalog.list_sources() if s["topic"] == topic and s.get("authority") != "superseded"]


def search(query: str, *, topic: str = "standards", k: int = 5) -> list[Hit]:
    """Top-k chunks across every ACTIVE document in this topic, by cosine similarity
    (embeddings are pre-normalised, so this is a dot product)."""
    docs = _active_documents(topic)
    q = embeddings.embed_texts([query])[0]

    all_hits: list[tuple[float, dict, dict]] = []
    for doc in docs:
        vecs = embeddings.load_embeddings(topic, doc["source_id"])
        if vecs is None or len(vecs) == 0:
            continue
        chunks = documents.load_chunks(topic, doc["source_id"])
        sims = vecs @ q
        for i, s in enumerate(sims):
            all_hits.append((float(s), doc, chunks[i]))

    all_hits.sort(key=lambda t: -t[0])
    return [
        Hit(score=s, source_id=doc["source_id"], doc_title=doc["name"], page=chunk["page"],
           text=chunk["text"], chunk_id=chunk["id"])
        for s, doc, chunk in all_hits[:k]
    ]


RELEVANCE_SYSTEM = (
    "You check whether a passage from a document actually answers a question, for an urban "
    "planning tool. Reply with JSON: {\"applies\": true/false, \"reason\": \"one short sentence\"}. "
    "Say applies=false if the passage is about something else, even if it shares some words with "
    "the question. Never invent information not in the passage."
)


def judge_relevance(query: str, hit: Hit) -> tuple[bool, str]:
    """Does this specific passage actually answer the query? Fails open to "applies" only when
    the LLM is unreachable (a person reviewing the result can still see the passage and judge for
    themselves); a real "doesn't apply" verdict from the LLM is always trusted."""
    prompt = f"Question: {query}\n\nPassage (page {hit.page}):\n{hit.text}"
    try:
        out = llm.chat_json(prompt, RELEVANCE_SYSTEM)
        return bool(out.get("applies")), str(out.get("reason", ""))
    except llm.LLMError as e:
        return True, f"AI relevance check unavailable ({e}); showing the top match for you to judge."


def search_with_relevance(query: str, *, topic: str = "standards", k: int = 5, check_top: int = 3) -> dict:
    """search() plus a relevance verdict on the top `check_top` hits. If none of them apply,
    says so explicitly rather than returning a plausible but wrong citation."""
    hits = search(query, topic=topic, k=k)
    checked = []
    for h in hits[:check_top]:
        applies, reason = judge_relevance(query, h)
        checked.append({"hit": h, "applies": applies, "reason": reason})
    best = next((c for c in checked if c["applies"]), None)
    return {
        "query": query, "checked": checked, "other_hits": hits[check_top:],
        "best": best["hit"] if best else None,
        "found": best is not None,
        "message": None if best else "No applicable provision found in the ingested documents.",
    }
