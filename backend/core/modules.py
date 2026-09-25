r"""Module discovery. A module is a folder backend\modules\<name>\ with a module.py
that defines NAME, LABEL and an APIRouter called `router`.

Adding a module = adding a folder. The core never lists modules by hand.
"""
import importlib
from pathlib import Path

MODULES_ROOT = Path(__file__).resolve().parents[1] / "modules"


def discover() -> list:
    found = []
    for p in sorted(MODULES_ROOT.glob("*/module.py")):
        found.append(importlib.import_module(f"modules.{p.parent.name}.module"))
    return found
