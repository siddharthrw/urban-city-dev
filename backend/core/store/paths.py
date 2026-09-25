r"""Where things live under DATA_DIR. One place, so the layout is easy to change.

DATA_DIR\
  catalog.duckdb
  raw\<topic>\<source>\<date>\...
  cities\<city_id>\<topic>\layers\<layer>.parquet
  cities\<city_id>\<topic>\tiles\<layer>.pmtiles
  documents\<topic>\...
  exports\
"""
from pathlib import Path

from core.config import settings


def base_dirs() -> list[Path]:
    root = settings.data_dir
    return [root, root / "raw", root / "cities", root / "documents", root / "exports"]


def raw_dir(topic: str, source: str, date: str) -> Path:
    return settings.data_dir / "raw" / topic / source / date


def city_topic_dir(city_id: str, topic: str) -> Path:
    return settings.data_dir / "cities" / city_id / topic


def layer_path(city_id: str, topic: str, layer_id: str) -> Path:
    return city_topic_dir(city_id, topic) / "layers" / f"{layer_id}.parquet"


def tiles_path(city_id: str, topic: str, layer_id: str) -> Path:
    return city_topic_dir(city_id, topic) / "tiles" / f"{layer_id}.pmtiles"


def relative(p: Path) -> str:
    """Paths stored in the catalog are relative, so DATA_DIR can move."""
    return str(p.resolve().relative_to(settings.data_dir))
