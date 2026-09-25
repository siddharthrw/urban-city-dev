r"""Propose rules from a standards document, for a human to review.

The LLM never invents a number: every proposed rule must carry a `quote` that is checked to
actually appear (near-verbatim) in the source chunk before the rule is accepted. A rule whose
quote doesn't match the chunk is dropped, not silently kept with a made-up citation -- this is
the same "AI never does the arithmetic" principle applied to extraction: the AI may only point
at where a number appears, never assert what it thinks the number should be.

Only chunks that look like they might state a checkable dimension (mention "width", "minimum",
"shall be", etc.) are sent to the LLM, to keep this fast and cheap on a long document.
"""
import re
from difflib import SequenceMatcher

from core.llm import client as llm
from core.rules import documents
from core.rules.schema import ELEMENTS

KEYWORD_RE = re.compile(
    r"\b(width|widths|minimum|maximum|shall be|not less than|not more than|at least|clear|metre|meter|\bm\b)\b",
    re.IGNORECASE,
)
QUOTE_MATCH_THRESHOLD = 0.75  # SequenceMatcher ratio; allows for OCR/whitespace noise, not fabrication

SYSTEM = (
    "You extract road-design dimension rules (minimum/maximum sizes for footpath, lane, cycle_track, "
    "tree_strip, median, bus_bay, verge, or crossing) from a passage of an official standards document, "
    "for an urban planning tool. Reply with JSON: {\"rules\": [...]}. Each item: "
    "{\"element\": one of the elements above, \"min_m\": number or null, \"max_m\": number or null, "
    "\"clause\": clause/section number if visible else null, "
    "\"quote\": the EXACT sentence from the passage that states this, copied verbatim, "
    "\"statement\": a one-sentence plain-English paraphrase}. "
    "Only include a rule if the passage states a specific number in metres for one of the listed "
    "elements. If the passage states no such rule, reply {\"rules\": []}. Never estimate or guess a "
    "number that isn't written in the passage."
)


def relevant_chunks(chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if KEYWORD_RE.search(c["text"])]


def _quote_is_grounded(quote: str, chunk_text: str) -> bool:
    """True if `quote` actually appears in chunk_text (allowing minor whitespace/OCR noise),
    so a hallucinated citation can never survive into a proposed rule."""
    q = re.sub(r"\s+", " ", quote).strip()
    if not q:
        return False
    if q in re.sub(r"\s+", " ", chunk_text):
        return True
    # Sliding-window fuzzy check for near-verbatim OCR noise (not for paraphrases).
    norm = re.sub(r"\s+", " ", chunk_text)
    window = len(q) + 20
    best = max(
        (SequenceMatcher(None, q, norm[i:i + window]).ratio() for i in range(0, max(1, len(norm) - len(q) + 1), 10)),
        default=0.0,
    )
    return best >= QUOTE_MATCH_THRESHOLD


def extract_from_chunk(chunk: dict) -> list[dict]:
    """Proposed rule dicts (schema-shaped but not yet validated/assigned an id) from one chunk.
    Drops any rule whose quote isn't actually grounded in the chunk."""
    try:
        out = llm.chat_json(f"Passage (page {chunk['page']}):\n{chunk['text']}", SYSTEM)
    except llm.LLMError:
        return []
    raw = out.get("rules", [])
    if not isinstance(raw, list):
        return []

    proposals = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        element, quote = r.get("element"), r.get("quote", "")
        if element not in ELEMENTS or not quote:
            continue
        if not _quote_is_grounded(quote, chunk["text"]):
            continue
        min_m, max_m = r.get("min_m"), r.get("max_m")
        if not isinstance(min_m, (int, float)) and not isinstance(max_m, (int, float)):
            continue
        proposals.append({
            "element": element,
            "value": {k: v for k, v in {"min_m": min_m, "max_m": max_m}.items() if isinstance(v, (int, float))},
            "statement": str(r.get("statement") or f"{element}: see quoted clause."),
            "quote": quote, "page": chunk["page"], "clause": r.get("clause"),
        })
    return proposals


def extract_document(source: dict, *, max_chunks: int | None = None) -> tuple[list[dict], dict]:
    """Proposed-rule dicts (ready for core.rules.loader.write_proposed) for a whole document,
    plus stats (chunks scanned/sent/dropped)."""
    chunks = documents.load_chunks(source["topic"], source["source_id"])
    candidates = relevant_chunks(chunks)
    if max_chunks:
        candidates = candidates[:max_chunks]

    seen_ids: set[str] = set()
    rules = []
    for chunk in candidates:
        for p in extract_from_chunk(chunk):
            rid_base = f"proposed_{p['element']}_{source['source_id'][-8:]}_p{p['page']}"
            rid, n = rid_base, 2
            while rid in seen_ids:
                rid, n = f"{rid_base}_{n}", n + 1
            seen_ids.add(rid)
            rules.append({
                "rule_id": rid, "status": "proposed", "category": "dimension", "element": p["element"],
                "statement": p["statement"], "value": p["value"],
                "source": {"authority": "primary", "doc_id": source["source_id"],
                          "doc_title": source["name"], "page": p["page"], "clause": p.get("clause"),
                          "quote": p["quote"]},
            })
    return rules, {"chunks_total": len(chunks), "chunks_scanned": len(candidates), "rules_proposed": len(rules)}
