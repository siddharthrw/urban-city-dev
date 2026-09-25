r"""Getting partner files into DATA_DIR\raw\ and into the provenance manifest.

Two ways in:
  - upload in the UI  -> saved to raw\<topic>\uploads\<date>\<file>, registered
  - drop a file anywhere under DATA_DIR\raw\ -> listed as "unregistered", one click registers it
Raw files are never edited or deleted by the app.
"""
import re
from datetime import date
from pathlib import Path

from core.config import settings
from core.store import catalog, paths

SAMPLE_PREFIX = "sample"  # files named SAMPLE_... are made-up test data and are labelled as such
IGNORED = {"thumbs.db", "desktop.ini", ".ds_store"}


def is_sample(filename: str) -> bool:
    return Path(filename).name.lower().startswith(SAMPLE_PREFIX)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "file"


def safe_filename(name: str) -> str:
    name = Path(name).name  # no directories from the client
    stem = re.sub(r"[^\w\-. ]+", "_", Path(name).stem).strip(" .") or "file"
    return f"{stem}{Path(name).suffix.lower()}"


def _topic_of(rel: Path) -> str:
    r"""raw\<topic>\... -> topic; files dropped straight into raw\ get 'unsorted'."""
    return rel.parts[1] if len(rel.parts) > 2 else "unsorted"


def register(path: Path, *, topic: str, city_id: str, origin: str, licence: str = "",
             received: date | None = None, notes: str = "") -> str:
    r"""Register a file under raw\ and return its source_id (stable for the same path + content)."""
    path = path.resolve()
    if settings.data_dir / "raw" not in path.parents:
        raise ValueError(f"{path} is not under {settings.data_dir / 'raw'}")
    sha = catalog.sha256_file(path)
    source_id = f"file-{topic}-{_slug(path.stem)}-{sha[:10]}"
    sample = is_sample(path.name)
    catalog.register_source(
        source_id=source_id, file=path, city_id=city_id, topic=topic,
        name=path.name + (" (SAMPLE: made-up test data)" if sample else ""),
        origin=origin, licence=licence or ("n/a (made-up test data)" if sample else "unknown: ask the sender"),
        received_at=received or date.today(), notes=notes,
    )
    return source_id


def save_upload(data: bytes, filename: str, *, topic: str, city_id: str, origin: str = "uploaded in the app") -> str:
    fname = safe_filename(filename)
    d = paths.raw_dir(topic, "uploads", date.today().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    target = d / fname
    n = 1
    while target.exists() and target.read_bytes() != data:  # same name, different content: keep both
        n += 1
        target = d / f"{Path(fname).stem} ({n}){Path(fname).suffix}"
    if not target.exists():
        target.write_bytes(data)
    return register(target, topic=topic, city_id=city_id, origin=origin)


def unregistered() -> list[dict]:
    r"""Files under raw\ that are not in the manifest yet (e.g. dropped in by hand)."""
    known = catalog.registered_paths()
    raw = settings.data_dir / "raw"
    out = []
    for p in sorted(raw.rglob("*")):
        if not p.is_file() or p.name.lower() in IGNORED or p.suffix in (".tmp", ".part"):
            continue
        rel = p.relative_to(settings.data_dir)
        if str(rel) in known:
            continue
        out.append({"path": str(rel), "name": p.name, "topic": _topic_of(rel),
                    "bytes": p.stat().st_size, "sample": is_sample(p.name)})
    return out


def register_dropped(rel_path: str, city_id: str) -> str:
    p = (settings.data_dir / rel_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(rel_path)
    rel = p.relative_to(settings.data_dir)
    return register(p, topic=_topic_of(rel), city_id=city_id, origin="dropped into the raw folder")
