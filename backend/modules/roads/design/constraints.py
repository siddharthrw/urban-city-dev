"""Turn active dimension rules into the min/max width an element must respect, in whole
centimetres (integers, so widths can sum EXACTLY to the right-of-way).

A rule applies to an element when its `applies_to` is satisfied:
  road_class: [..]  -> the road's class is in the list
  context:    [..]  -> every listed tag is among the element's tags (e.g. a cycle track drawn on
                       each side is "one_way": a single-direction track)
Any other applies_to key is not understood, so that rule is skipped rather than over-applied.
Several rules for one element combine strictly: the largest minimum, the smallest maximum.
"""
import math
from dataclasses import dataclass

from core.rules.schema import Rule


class RuleConflict(ValueError):
    """Applicable rules for one element contradict each other (largest min > smallest max)."""


@dataclass(frozen=True)
class Constraint:
    min_cm: int
    max_cm: int | None
    rule_ids: tuple[str, ...]
    fallback: bool  # True when no rule exists and a UNCITED default minimum was used


def cm_ceil(m: float) -> int:
    return math.ceil(round(m * 100, 6))


def cm_floor(m: float) -> int:
    return math.floor(round(m * 100, 6))


def usable(rules: list[Rule]) -> list[Rule]:
    """Active dimension rules from a non-superseded source. Proposed rules (awaiting review) and
    superseded ones are never used to design anything."""
    return [r for r in rules if r.status == "active" and r.category == "dimension"
            and r.source.authority != "superseded"]


def _applies(rule: Rule, road_class: str, tags: set[str]) -> bool:
    for key, val in (rule.applies_to or {}).items():
        if key == "road_class":
            if road_class not in val:
                return False
        elif key == "context":
            if not set(val) <= tags:
                return False
        else:
            return False
    return True


class RuleSet:
    def __init__(self, rules: list[Rule], fallback_min_m: dict[str, float]):
        self.rules = usable(rules)
        self.fallback_min_m = fallback_min_m

    def constraint(self, kind: str, road_class: str, tags: set[str]) -> Constraint:
        hits = [r for r in self.rules if r.element == kind and _applies(r, road_class, tags)]
        if not hits:
            return Constraint(cm_ceil(self.fallback_min_m[kind]), None, (), True)
        mins = [cm_ceil(r.value["min_m"]) for r in hits if r.value.get("min_m") is not None]
        maxs = [cm_floor(r.value["max_m"]) for r in hits if r.value.get("max_m") is not None]
        lo = max(mins) if mins else cm_ceil(self.fallback_min_m[kind])
        hi = min(maxs) if maxs else None
        if hi is not None and lo > hi:
            raise RuleConflict(f"Rules for {kind} contradict each other (minimum {lo / 100:g} m, "
                               f"maximum {hi / 100:g} m): {', '.join(r.rule_id for r in hits)}")
        return Constraint(lo, hi, tuple(r.rule_id for r in hits), not mins)
