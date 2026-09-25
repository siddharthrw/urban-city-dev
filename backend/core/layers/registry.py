r"""Topics and layer definitions, read from the repo's layers\ folder.

layers\<topic>\_topic.yaml    declares a topic (roads, people, surroundings, ...)
layers\<topic>\<layer>.yaml   declares a layer: schema, geometry type, sources, build script

Adding a topic or layer = adding YAML. No code changes.
"""
from pathlib import Path

import yaml

from core.config import REPO_ROOT

LAYERS_ROOT = REPO_ROOT / "layers"
CITIES_ROOT = REPO_ROOT / "config" / "cities"


def _load(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def topics() -> list[dict]:
    found = [_load(p) for p in LAYERS_ROOT.glob("*/_topic.yaml")]
    return sorted(found, key=lambda t: (t.get("order", 999), t["topic"]))


def layer_defs() -> list[dict]:
    out = []
    for p in sorted(LAYERS_ROOT.glob("*/*.yaml")):
        if p.name.startswith("_"):
            continue
        d = _load(p)
        d.setdefault("topic", p.parent.name)
        out.append(d)
    return out


def city_configs() -> list[dict]:
    return [_load(p) for p in sorted(CITIES_ROOT.glob("*.yaml"))]
