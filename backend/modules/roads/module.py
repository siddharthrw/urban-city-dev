"""Roads module: pick a road, get 2-3 standards-based cross-section designs.

M0: registered but empty. Road endpoints arrive in M1.
"""
from fastapi import APIRouter

NAME = "roads"
LABEL = "Roads"

router = APIRouter(prefix="/api/roads", tags=["roads"])
