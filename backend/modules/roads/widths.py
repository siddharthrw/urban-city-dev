"""Road width (right-of-way) resolution: verified > measured > estimated.

Pure functions, no I/O, so they are easy to test. Level-2 "measured" arrives in M5.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULTS_PATH = Path(__file__).with_name("width_defaults.yaml")

# Classes where a one-way OSM way is often one half of a divided road.
DIVIDED_ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary"}


@dataclass(frozen=True)
class Width:
    width_m: float
    source: str  # estimated | measured | verified
    detail: str


def load_defaults(path: Path = DEFAULTS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def estimate(road_class: str, lanes: int | None, oneway: bool, defaults: dict) -> Width:
    """Level-1 estimate from road class, refined by the OSM lane count when that is meaningful."""
    cls = defaults["classes"].get(road_class)
    if cls is None:
        cls = defaults["classes"]["unclassified"]
        base = f"class '{road_class}' has no default, used 'unclassified'"
    else:
        base = f"default for {road_class}"
    cite = cls.get("citation", "UNCITED")

    divided_note = ""
    if oneway and road_class in DIVIDED_ROAD_CLASSES:
        divided_note = (" One-way segment: may be one carriageway of a divided road;"
                        " the estimate is for the whole road.")

    if lanes and lanes > 0 and not oneway:
        lr = defaults["lanes_refinement"]
        w = lanes * lr["lane_width_m"] + 2 * cls["side_allowance_m"]
        detail = (f"Estimated from OSM lanes={lanes}: {lanes} x {lr['lane_width_m']} m lanes"
                  f" + 2 x {cls['side_allowance_m']} m sides ({lr.get('citation', 'UNCITED')} values).")
        return Width(round(w, 1), "estimated", detail)

    lanes_note = f" OSM lanes={lanes} not used (one-way)." if lanes and oneway else ""
    detail = f"Estimated: {base}, {cls['row_m']} m ({cite}).{lanes_note}{divided_note}"
    return Width(float(cls["row_m"]), "estimated", detail)


def resolve(estimated: Width, measured: Width | None = None, verified: Width | None = None) -> Width:
    return verified or measured or estimated
