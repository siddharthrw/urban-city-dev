r"""Snapshot DATA_DIR into one zip file, skipping things that can be regenerated.

    .\.venv\Scripts\python.exe scripts\backup.py                 # -> <DATA_DIR>_backups\citydata_<timestamp>.zip
    .\.venv\Scripts\python.exe scripts\backup.py --dest E:\backups

Skipped (rebuilt by the pipelines): vector tiles (tiles\, *.pmtiles) and embeddings (*.npy, embeddings\).
Everything else is kept: catalog, raw files, layers, documents, exports.
To restore: unzip into an empty folder and point DATA_DIR at it.
"""
import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from core.config import settings  # noqa: E402

SKIP_DIRS = {"tiles", "embeddings"}
SKIP_SUFFIXES = {".pmtiles", ".npy", ".tmp", ".wal"}


def skipped(rel: Path) -> bool:
    return bool(SKIP_DIRS & set(rel.parts[:-1])) or rel.suffix.lower() in SKIP_SUFFIXES


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=settings.data_dir.parent / f"{settings.data_dir.name}_backups")
    args = ap.parse_args(argv)

    src = settings.data_dir
    dest_dir = args.dest.resolve()
    if dest_dir == src or src in dest_dir.parents:
        sys.exit(f"--dest must be outside DATA_DIR ({src})")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"citydata_{datetime.now():%Y%m%d_%H%M%S}.zip"

    kept, skipped_n, total = [], 0, 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for p in sorted(src.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(src)
            if skipped(rel):
                skipped_n += 1
                continue
            z.write(p, rel.as_posix())
            size = p.stat().st_size
            kept.append({"path": rel.as_posix(), "bytes": size})
            total += size
        z.writestr("_backup_manifest.json", json.dumps(
            {"created": datetime.now().isoformat(timespec="seconds"), "data_dir": str(src),
             "files": kept, "skipped_regenerable": skipped_n}, indent=1))

    print(f"Backed up {len(kept)} files ({total / 1e6:.1f} MB) -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    print(f"Skipped {skipped_n} regenerable files (tiles, embeddings).")


if __name__ == "__main__":
    main()
