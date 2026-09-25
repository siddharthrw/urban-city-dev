r"""Load and write rule files under the repo's rules\active\ and rules\proposed\ folders.

Each YAML file holds a list of rules (a file is usually "one import" or "one hand-written set",
not one rule per file, except where noted). Loading validates every rule and checks rule_id is
unique across ALL active+proposed rules combined, not just within one file.
"""
from pathlib import Path

import yaml

from core.config import REPO_ROOT
from core.rules.schema import Rule, RuleError, rule_filename, validate_file, validate_rule

RULES_ROOT = REPO_ROOT / "rules"
ACTIVE_DIR = RULES_ROOT / "active"
PROPOSED_DIR = RULES_ROOT / "proposed"


def _read_yaml_list(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    if isinstance(data, dict):
        data = data.get("rules", [data])
    if not isinstance(data, list):
        raise RuleError(f"{p.name}: expected a list of rules (or {{rules: [...]}})")
    return data


def _load_dir(d: Path, status: str) -> list[Rule]:
    d.mkdir(parents=True, exist_ok=True)
    out: list[Rule] = []
    for p in sorted(d.glob("*.yaml")):
        rel = p.relative_to(RULES_ROOT).as_posix()  # always "/", never "\", so file paths parse the same on Windows
        out.extend(validate_file(_read_yaml_list(p), expected_status=status, file=rel))
    return out


def load_all() -> list[Rule]:
    """Every rule, active and proposed. Raises RuleError (naming the file) on the first problem,
    so a broken rule file is loud, not silently skipped."""
    active = _load_dir(ACTIVE_DIR, "active")
    proposed = _load_dir(PROPOSED_DIR, "proposed")
    seen: dict[str, str] = {}
    for r in active + proposed:
        if r.rule_id in seen:
            raise RuleError(f"Duplicate rule_id '{r.rule_id}': in both {seen[r.rule_id]} and {r.file}")
        seen[r.rule_id] = r.file
    return active + proposed


def get(rule_id: str) -> Rule | None:
    for r in load_all():
        if r.rule_id == rule_id:
            return r
    return None


def _write_list(p: Path, rules: list[Rule]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump([r.to_dict() for r in rules], f, sort_keys=False, allow_unicode=True)


def write_proposed(file_stem: str, rules: list[dict]) -> Path:
    """Write a batch of proposed rules (e.g. one document's LLM extraction) to one file,
    replacing it if it already exists (so re-running extraction is safe)."""
    validated = validate_file(rules, expected_status="proposed", file=f"proposed/{file_stem}.yaml")
    p = PROPOSED_DIR / f"{file_stem}.yaml"
    _write_list(p, validated)
    return p


def write_active(file_stem: str, rules: list[dict]) -> Path:
    validated = validate_file(rules, expected_status="active", file=f"active/{file_stem}.yaml")
    p = ACTIVE_DIR / f"{file_stem}.yaml"
    _write_list(p, validated)
    return p


def approve(rule_id: str) -> Rule:
    """Move one rule from a proposed file into rules/active/<rule_id>.yaml (its own file, so
    approving one rule from a batch never touches its siblings)."""
    all_rules = load_all()
    rule = next((r for r in all_rules if r.rule_id == rule_id), None)
    if rule is None:
        raise RuleError(f"No rule '{rule_id}'")
    if rule.status != "proposed":
        raise RuleError(f"Rule '{rule_id}' is already {rule.status}, not proposed")

    active_dict = rule.to_dict()
    active_dict["status"] = "active"
    _write_list(ACTIVE_DIR / rule_filename(rule_id), [validate_rule(active_dict, expected_status="active")])
    _remove_from_file(PROPOSED_DIR / rule.file.split("/", 1)[1], rule_id)
    return get(rule_id)  # re-load: proves the write round-trips cleanly


def reject(rule_id: str) -> None:
    rule = get(rule_id)
    if rule is None:
        raise RuleError(f"No rule '{rule_id}'")
    if rule.status != "proposed":
        raise RuleError(f"Rule '{rule_id}' is already {rule.status}, not proposed")
    _remove_from_file(PROPOSED_DIR / rule.file.split("/", 1)[1], rule_id)


def _remove_from_file(p: Path, rule_id: str) -> None:
    remaining = [d for d in _read_yaml_list(p) if d.get("rule_id") != rule_id]
    if remaining:
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(remaining, f, sort_keys=False, allow_unicode=True)
    else:
        p.unlink(missing_ok=True)  # file's only rule was just moved/rejected
