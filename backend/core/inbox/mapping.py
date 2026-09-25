"""Suggest which file column feeds which layer field.

1. Auto-detect from column headers vs. each field's name/label/aliases (no AI).
2. Optionally ask the LLM to fill the gaps. The LLM sees ONLY column names and their inferred
   types, never cell values, so no partner data goes into a prompt, whichever provider is set.
A person always confirms the mapping before anything is imported.
"""
import re

from rapidfuzz import fuzz

from core.llm import client as llm

AUTO_THRESHOLD = 82


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _score(header: str, candidate: str) -> float:
    h, c = _norm(header), _norm(candidate)
    if not h or not c:
        return 0.0
    if h == c:
        return 100.0
    ht, ct = set(h.split()), set(c.split())
    # All words of a multi-word alias present in the header ("cars (nos)" vs "cars").
    if ct <= ht and len(c) >= 3:
        return 92.0 - 2 * len(ht - ct)
    return float(fuzz.ratio(h, c))


def auto_suggest(columns: list[str], fields: dict, skip: set[str] = frozenset()) -> dict:
    """{field: {"column", "method": "auto", "score"}} for fields with a confident match.
    Each column is used at most once (best-scoring pairs first)."""
    triples = []
    for f, spec in fields.items():
        if f in skip:
            continue
        cands = [f.replace("_", " "), spec.get("label", "")] + list(spec.get("aliases", []))
        for col in columns:
            s = max(_score(col, c) for c in cands if c)
            if s >= AUTO_THRESHOLD:
                triples.append((s, f, col))
    out, used = {}, set()
    for s, f, col in sorted(triples, key=lambda t: -t[0]):
        if f in out or col in used:
            continue
        out[f] = {"column": col, "method": "auto", "score": round(s)}
        used.add(col)
    return out


SYSTEM = (
    "You match spreadsheet column headers to a target schema for an urban planning database. "
    "Reply with a JSON object: {\"mapping\": {\"<field>\": \"<exact column header>\" or null}}. "
    "Use only headers from the list, exactly as written. Use null when no column clearly fits. "
    "Never map one column to two fields."
)


def llm_prompt(columns: list[dict], fields: dict) -> str:
    """Only headers + inferred types + field descriptions. No cell values."""
    flines = [f"- {f} ({spec.get('type', 'string')}): {spec.get('label', '')}. {spec.get('description', '')}".strip()
              for f, spec in fields.items()]
    clines = [f"- \"{c['name']}\" ({c['type']})" for c in columns]
    return "Target fields:\n" + "\n".join(flines) + "\n\nColumn headers in the file:\n" + "\n".join(clines)


def llm_suggest(columns: list[dict], fields: dict) -> dict:
    """{field: column} from the LLM, validated: unknown headers/fields and duplicates are dropped."""
    raw = llm.chat_json(llm_prompt(columns, fields), SYSTEM)
    mapping = raw.get("mapping", raw)
    names = {c["name"] for c in columns}
    out, used = {}, set()
    if not isinstance(mapping, dict):
        return out
    for f, col in mapping.items():
        if f in fields and isinstance(col, str) and col in names and col not in used:
            out[f] = col
            used.add(col)
    return out


def suggest(columns: list[dict], fields: dict, *, use_llm: bool = False, has_geometry: bool = False) -> dict:
    """Merge auto-detect and (optionally) LLM suggestions. Auto wins on conflict; the LLM only
    fills fields auto-detect left empty, with columns not already taken."""
    skip = {"latitude", "longitude"} if has_geometry else set()
    names = [c["name"] for c in columns]
    result = auto_suggest(names, fields, skip)
    notes: list[str] = []
    if use_llm:
        info = llm.info()
        try:
            ai = llm_suggest(columns, {f: s for f, s in fields.items() if f not in skip})
            used = {v["column"] for v in result.values()}
            for f, col in ai.items():
                if f not in result and col not in used:
                    result[f] = {"column": col, "method": "ai", "score": None}
                    used.add(col)
                elif f in result and result[f]["column"] != col:
                    result[f]["ai_suggests"] = col
            notes.append(f"AI ({info.provider}, {info.model}) saw column names and types only.")
        except llm.LLMError as e:
            notes.append(f"AI suggestion unavailable: {e}")
    return {"mapping": result, "notes": notes}
