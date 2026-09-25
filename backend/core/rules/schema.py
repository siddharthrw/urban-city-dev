"""The rule schema, and a hand-written validator (no pydantic: this mirrors the plain-dict
validation style already used for imported data in core/inbox/validate.py, and keeps the
schema readable as the YAML it actually is).

Two kinds of rule:
  dimension   -- a minimum/maximum size for one road element (footpath, lane, cycle track, ...)
  conditional -- an If/Then/Because rule (from an expert, or extracted from a document)

Every rule, whatever its kind, carries a `source` with an `authority`:
  primary      -- from a current, valid standard: doc_id + page are required
  superseded   -- from a standard later replaced by another; NEVER used for design (M3/M4
                  must refuse to cite it), kept only so it's visible and traceable
  expert       -- from the partner's own judgement (the If/Then/Because sheet)
  placeholder  -- an engineering guess, not from any standard; must say so in `statement`
"""
from dataclasses import dataclass, field
from pathlib import Path

ELEMENTS = {"footpath", "cycle_track", "tree_strip", "median", "bus_bay", "lane", "verge", "crossing"}
AUTHORITIES = {"primary", "superseded", "expert", "placeholder"}
CATEGORIES = {"dimension", "conditional"}
STATUSES = {"active", "proposed"}


class RuleError(ValueError):
    """A rule (or a whole file) failed validation. Message is meant to be shown to a person."""


@dataclass(frozen=True)
class Source:
    authority: str
    doc_id: str | None = None
    doc_title: str | None = None
    page: int | None = None
    clause: str | None = None
    quote: str | None = None
    detail: str | None = None

    def label(self) -> str:
        if self.authority == "placeholder":
            return "Placeholder (uncited)"
        if self.authority == "expert":
            if not self.detail or self.detail.strip().lower().startswith("expert judgement"):
                return self.detail or "Expert judgement"
            return f"Expert judgement: {self.detail}"
        bits = [self.doc_title or self.doc_id or "Unknown document"]
        if self.clause:
            bits.append(f"clause {self.clause}")
        if self.page:
            bits.append(f"p.{self.page}")
        return ", ".join(bits)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    status: str
    category: str
    statement: str
    source: Source
    element: str | None = None
    applies_to: dict = field(default_factory=dict)
    value: dict = field(default_factory=dict)
    condition: dict = field(default_factory=dict)
    file: str | None = None  # relative path this rule was loaded from, for editing/moving

    def to_dict(self) -> dict:
        d = {
            "rule_id": self.rule_id, "status": self.status, "category": self.category,
            "statement": self.statement, "source": {k: v for k, v in vars(self.source).items() if v is not None},
        }
        if self.element:
            d["element"] = self.element
        if self.applies_to:
            d["applies_to"] = self.applies_to
        if self.value:
            d["value"] = self.value
        if self.condition:
            d["condition"] = self.condition
        return d


def _require(d: dict, key: str, ctx: str) -> object:
    if key not in d or d[key] in (None, ""):
        raise RuleError(f"{ctx}: missing required field '{key}'")
    return d[key]


def validate_rule(d: dict, *, expected_status: str | None = None, file: str | None = None) -> Rule:
    """Validate one rule dict (as loaded from YAML) and return a Rule. Raises RuleError."""
    rule_id = _require(d, "rule_id", file or "rule")
    ctx = f"rule '{rule_id}'" + (f" in {file}" if file else "")

    status = _require(d, "status", ctx)
    if status not in STATUSES:
        raise RuleError(f"{ctx}: status must be one of {sorted(STATUSES)}, got '{status}'")
    if expected_status and status != expected_status:
        raise RuleError(f"{ctx}: status is '{status}' but it is in the {expected_status}/ folder")

    category = _require(d, "category", ctx)
    if category not in CATEGORIES:
        raise RuleError(f"{ctx}: category must be one of {sorted(CATEGORIES)}, got '{category}'")

    statement = _require(d, "statement", ctx)

    src = d.get("source")
    if not isinstance(src, dict):
        raise RuleError(f"{ctx}: missing 'source'")
    authority = _require(src, "authority", ctx)
    if authority not in AUTHORITIES:
        raise RuleError(f"{ctx}: source.authority must be one of {sorted(AUTHORITIES)}, got '{authority}'")
    if authority in ("primary", "superseded") and not (src.get("doc_id") and src.get("page")):
        raise RuleError(f"{ctx}: authority '{authority}' needs source.doc_id and source.page (a real citation)")
    if authority == "placeholder" and "uncited" not in statement.lower() and "placeholder" not in statement.lower():
        raise RuleError(f"{ctx}: a placeholder rule's statement must say so (e.g. 'UNCITED'), so it can never "
                        "be mistaken for a real standard when read on its own")
    source = Source(authority=authority, doc_id=src.get("doc_id"), doc_title=src.get("doc_title"),
                    page=src.get("page"), clause=src.get("clause"), quote=src.get("quote"),
                    detail=src.get("detail"))

    element = d.get("element")
    value = d.get("value") or {}
    condition = d.get("condition") or {}
    if category == "dimension":
        if element not in ELEMENTS:
            raise RuleError(f"{ctx}: dimension rule needs 'element', one of {sorted(ELEMENTS)}, got '{element}'")
        if value.get("min_m") is None and value.get("max_m") is None:
            raise RuleError(f"{ctx}: dimension rule needs value.min_m and/or value.max_m")
        for k in ("min_m", "max_m"):
            v = value.get(k)
            if v is not None and (not isinstance(v, (int, float)) or v <= 0):
                raise RuleError(f"{ctx}: value.{k} must be a positive number, got {v!r}")
        if value.get("min_m") is not None and value.get("max_m") is not None and value["min_m"] > value["max_m"]:
            raise RuleError(f"{ctx}: value.min_m ({value['min_m']}) is greater than value.max_m ({value['max_m']})")
    else:  # conditional
        _require(condition, "if", ctx)
        _require(condition, "then", ctx)

    applies_to = d.get("applies_to") or {}
    if not isinstance(applies_to, dict):
        raise RuleError(f"{ctx}: applies_to must be a mapping (e.g. road_class: [primary])")

    return Rule(rule_id=rule_id, status=status, category=category, statement=statement, source=source,
               element=element, applies_to=applies_to, value=value, condition=condition, file=file)


def validate_file(rules: list[dict], *, expected_status: str, file: str) -> list[Rule]:
    out = [validate_rule(d, expected_status=expected_status, file=file) for d in rules]
    seen: dict[str, str] = {}
    for r in out:
        if r.rule_id in seen:
            raise RuleError(f"Duplicate rule_id '{r.rule_id}' in {file} (already used by {seen[r.rule_id]})")
        seen[r.rule_id] = file
    return out


def rule_filename(rule_id: str) -> str:
    return f"{rule_id}.yaml"
