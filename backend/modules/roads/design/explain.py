"""LLM-powered explanations for design options.

Rules (from the project brief):
  - The LLM never does geometry or arithmetic; it only interprets the engine's output.
  - Only cite rule IDs that the engine actually used; validated here in code.
  - Never put raw partner data in the prompt; widths in the prompt come from the design result.
  - If the LLM is unreachable, return empty explanations with a warning rather than failing.
"""
import re

from core.config import Settings, settings
from core.llm.client import LLMError, chat_json

_RULE_ID_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")

# Tokens that are syntactically rule-ID-like but are never rule IDs.
_KNOWN_NON_RULE = frozenset({
    "road_class", "right_of_way", "per_hour", "per_side", "per_direction",
    "one_way", "two_way", "bus_route", "bus_bay", "bus_stop", "tree_strip",
    "cycle_track", "school_nearby", "metro_nearby", "road_type", "width_source",
    "lane_width", "footpath_m", "carriageway_m", "option_id",
})

_SYSTEM = (
    "You are a road design assistant helping city planners in India understand design options. "
    "Explain each option in plain English, 2-3 sentences, suitable for a planning official. "
    "Be factual and concise. Only refer to measurements and rules given to you below. "
    "Do not invent numbers. Only cite rules by their exact ID as listed in the prompt."
)


def _option_text(opt: dict, rules: dict) -> str:
    els = ", ".join(f"{e['label']} {e['width_m']:.1f} m" for e in opt["elements"])
    m = opt["metrics"]
    features = [f for f, flag in [
        ("cycle track", m["has_cycle_track"]),
        ("shade trees", m["has_trees"]),
        ("bus bays", m["has_bus_bay"]),
        ("median", m["has_median"]),
    ] if flag]
    metrics = (
        f"{m['lanes']} lane{'s' if m['lanes'] != 1 else ''}, "
        f"{m['footpath_m']:.1f} m footpaths"
        + ((", " + ", ".join(features)) if features else "")
    )
    rule_texts = "; ".join(
        f"{rid}: {rules[rid]['statement']}" for rid in opt["rule_ids"] if rid in rules
    )
    lines = [
        f"Option ID: {opt['option_id']}",
        f"Name: {opt['name']}",
        f"Summary: {opt['summary']}",
        f"Layout (left to right): {els}",
        f"Metrics: {metrics}",
    ]
    if rule_texts:
        lines.append(f"Rules applied: {rule_texts}")
    if opt["notes"]:
        lines.append("Notes: " + "; ".join(opt["notes"]))
    return "\n".join(lines)


def build_prompt(result: dict) -> str:
    """Build the LLM prompt for a design result. Public so tests can inspect it."""
    seg = result.get("segment", {})
    name = seg.get("name") or "Unnamed road"
    known_ids = sorted(result.get("rules", {}).keys())
    option_ids = [o["option_id"] for o in result.get("options", [])]

    lines = [
        f"Road: {name}",
        f"Right-of-way: {result['row_m']:g} m ({result['width_source']})",
        f"Type: {result['road_class'].replace('_', ' ')}, "
        f"{'one-way' if result['oneway'] else 'two-way'}",
        "",
        "=== DESIGN OPTIONS ===",
    ]
    for opt in result.get("options", []):
        lines += ["", _option_text(opt, result.get("rules", {}))]

    if result.get("dropped"):
        lines += ["", "=== NOT POSSIBLE AT THIS WIDTH ==="]
        for d in result["dropped"]:
            lines.append(f"- {d['name']}: {d['reason']}")

    if result.get("warnings"):
        lines += ["", "=== NOTES / WARNINGS ==="]
        lines += [f"- {w}" for w in result["warnings"]]

    lines += [
        "",
        "=== YOUR TASK ===",
        "Return a JSON object with exactly these keys:",
        f'  "explanations": object with one key per option ID ({", ".join(option_ids)}), '
        "each value being 2-3 sentences of plain English.",
        '  "comparison": 2-3 sentences comparing the options and giving a recommendation.',
        "",
        "Rule IDs you may cite (exact IDs only, no others): "
        + (", ".join(known_ids) if known_ids else "none — all rules are uncited placeholders"),
    ]
    return "\n".join(lines)


def unknown_citations(text: str, known_ids: set[str]) -> list[str]:
    """Return rule-ID-like tokens in `text` that are not in `known_ids`."""
    found = set(_RULE_ID_RE.findall(text))
    return sorted(found - known_ids - _KNOWN_NON_RULE)


def build_prompt_one(result: dict, option_id: str) -> str:
    """Build a focused LLM prompt for a single design option."""
    opt = next((o for o in result.get("options", []) if o["option_id"] == option_id), None)
    if opt is None:
        return ""
    seg = result.get("segment", {})
    name = seg.get("name") or "Unnamed road"
    known_ids = sorted(result.get("rules", {}).keys())

    lines = [
        f"Road: {name}",
        f"Right-of-way: {result['row_m']:g} m ({result['width_source']})",
        f"Type: {result['road_class'].replace('_', ' ')}, "
        f"{'one-way' if result['oneway'] else 'two-way'}",
        "",
        "=== DESIGN OPTION ===",
        "",
        _option_text(opt, result.get("rules", {})),
    ]
    if result.get("dropped"):
        lines += ["", "=== NOT POSSIBLE AT THIS WIDTH ==="]
        for d in result["dropped"]:
            lines.append(f"- {d['name']}: {d['reason']}")
    if result.get("warnings"):
        lines += ["", "=== NOTES / WARNINGS ==="]
        lines += [f"- {w}" for w in result["warnings"]]
    lines += [
        "",
        "=== YOUR TASK ===",
        f"Write 2-3 sentences of plain English explaining this design option ('{option_id}') "
        "to a planning official. Be factual and concise.",
        'Return a JSON object with exactly one key:',
        '  "explanation": your 2-3 sentence explanation.',
        "",
        "Rule IDs you may cite (exact IDs only, no others): "
        + (", ".join(known_ids) if known_ids else "none — all rules are uncited placeholders"),
    ]
    return "\n".join(lines)


def explain_one(result: dict, option_id: str, *, cfg: Settings = settings) -> dict:
    """Return an LLM explanation for a single design option.

    Returns::

        {"explanation": str, "warnings": [str, ...]}

    Never raises: LLM failures become warnings with an empty explanation.
    """
    opt = next((o for o in result.get("options", []) if o["option_id"] == option_id), None)
    if opt is None:
        return {"explanation": "", "warnings": [f"Option '{option_id}' not found."]}

    known_ids = set(result.get("rules", {}).keys())
    prompt = build_prompt_one(result, option_id)
    try:
        raw = chat_json(prompt, _SYSTEM, timeout=90, cfg=cfg)
    except LLMError as e:
        return {"explanation": "", "warnings": [f"LLM unavailable — explanation could not be generated: {e}"]}

    text = str(raw.get("explanation", ""))
    warnings: list[str] = []
    unknown = unknown_citations(text, known_ids)
    if unknown:
        warnings.append(
            f"Explanation cited unknown rule IDs: {', '.join(unknown)}. "
            "Shown as-is; verify before using officially."
        )
    return {"explanation": text, "warnings": warnings}


def explain(result: dict, *, cfg: Settings = settings) -> dict:
    """Return LLM explanations for the design options in `result`.

    Returns::

        {
            "explanations": {option_id: str, ...},
            "comparison": str,
            "warnings": [str, ...],
        }

    Never raises: LLM failures become warnings with empty explanations.
    """
    options = result.get("options", [])
    if not options:
        return {"explanations": {}, "comparison": "", "warnings": []}

    known_ids = set(result.get("rules", {}).keys())
    try:
        raw = chat_json(build_prompt(result), _SYSTEM, timeout=120, cfg=cfg)
    except LLMError as e:
        return {"explanations": {}, "comparison": "",
                "warnings": [f"LLM unavailable — explanations could not be generated: {e}"]}

    explanations: dict[str, str] = {}
    warnings: list[str] = []

    for opt in options:
        oid = opt["option_id"]
        text = str(raw.get("explanations", {}).get(oid, ""))
        unknown = unknown_citations(text, known_ids)
        if unknown:
            warnings.append(
                f"Explanation for '{oid}' cited unknown rule IDs: {', '.join(unknown)}. "
                "Shown as-is; verify before using officially."
            )
        explanations[oid] = text

    comparison = str(raw.get("comparison", ""))
    unknown_cmp = unknown_citations(comparison, known_ids)
    if unknown_cmp:
        warnings.append(
            f"Comparison cited unknown rule IDs: {', '.join(unknown_cmp)}. "
            "Shown as-is; verify before using officially."
        )

    return {"explanations": explanations, "comparison": comparison, "warnings": warnings}
