r"""Load the partner's expert-rules sheet: a CSV/XLSX with If / Then / Because / Source columns
(see the Phase 1 plan, section 5C), one row per rule of thumb from experience.

Reuses the data inbox's generic pieces (file reading, header detection, column auto-mapping,
type validation) -- an expert-rules sheet is just tabular data with a fixed small schema, so
there is no reason to duplicate that machinery. What's different from a geo import: the output
is rule YAML, not a map layer, and there is no road-linking step (an expert rule isn't tied to
one road).
"""
import re
from datetime import datetime
from pathlib import Path

from core.inbox import mapping, readers, validate
from core.rules import loader

FIELDS = {
    "if_text": {"type": "string", "label": "If", "required": True,
               "aliases": ["if", "if...", "condition", "when", "situation"]},
    "then_text": {"type": "string", "label": "Then", "required": True,
                 "aliases": ["then", "then...", "action", "recommendation", "do"]},
    "because_text": {"type": "string", "label": "Because",
                     "aliases": ["because", "because...", "reason", "rationale", "why"]},
    "source_text": {"type": "string", "label": "Source",
                    "aliases": ["source", "reference", "source doc", "citation", "authority"]},
}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:50] or "rule"


def suggest_mapping(columns: list[dict]) -> dict:
    return mapping.auto_suggest([c["name"] for c in columns], FIELDS)


def _rule_id(if_text: str, seen: set[str]) -> str:
    base = f"expert_{_slug(if_text)}"
    rid, n = base, 2
    while rid in seen:
        rid, n = f"{base}_{n}", n + 1
    seen.add(rid)
    return rid


def preview_and_map(source, sheet: str | None, column_map: dict[str, str] | None = None):
    """Read the sheet and return (preview_dict, mapping_dict). If column_map is not given,
    columns are auto-detected from headers."""
    res = readers.read_file(source["abs_path"], sheet)
    pv = readers.preview(res, n=10)
    cmap = column_map or {f: v["column"] for f, v in suggest_mapping(pv["columns"]).items()}
    return res, pv, cmap


def build_rules(res: readers.ReadResult, column_map: dict[str, str], source_name: str) -> tuple[list[dict], list[dict]]:
    """Validate rows and turn each into a rule dict (not yet written to disk).
    Returns (rules, problems) -- problems mirror the inbox's per-row error shape."""
    missing_req = [FIELDS[f]["label"] for f, s in FIELDS.items() if s.get("required") and f not in column_map]
    if missing_req:
        raise validate.Invalid(f"Required column(s) not mapped: {', '.join(missing_req)}")

    clean, problems = validate.validate_rows(res.table, column_map, FIELDS, readers.ROW_NO)
    rules, seen_ids = [], set()
    for row in clean.to_dict("records"):
        rid = _rule_id(row["if_text"], seen_ids)
        statement = f"If {row['if_text'].rstrip('.')}, then {row['then_text'].rstrip('.').lower()}."
        rules.append({
            "rule_id": rid, "status": "active", "category": "conditional", "statement": statement,
            "condition": {"if": row["if_text"], "then": row["then_text"],
                          **({"because": row["because_text"]} if row.get("because_text") else {})},
            "source": {"authority": "expert",
                      "detail": row.get("source_text") or f"Expert judgement (row {row['row_no']} of {source_name})"},
        })
    return rules, problems


def import_sheet(source: dict, sheet: str | None, column_map: dict[str, str] | None = None) -> dict:
    """Read, validate, and write an expert-rules sheet to rules/active/expert_<file>.yaml,
    replacing any rules previously imported from this exact file (re-importing is safe)."""
    res, pv, cmap = preview_and_map(source, sheet, column_map)
    rules, problems = build_rules(res, cmap, source["name"])
    # Short and readable, but still unique per file (the source_id already hashes the content).
    file_stem = f"expert_{_slug(Path(source['name']).stem)}_{source['source_id'][-10:]}"
    path = loader.write_active(file_stem, rules) if rules else None
    return {
        "source_id": source["source_id"], "file_stem": file_stem, "path": str(path) if path else None,
        "mapping": cmap, "rows_in_file": pv["row_count"], "imported": len(rules), "invalid": len(problems),
        "problems": problems, "rule_ids": [r["rule_id"] for r in rules],
        "imported_at": datetime.now().isoformat(timespec="seconds"),
    }
