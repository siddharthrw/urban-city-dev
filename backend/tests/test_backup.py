import importlib.util
import json
import zipfile

from core.config import REPO_ROOT, settings


def load_backup():
    spec = importlib.util.spec_from_file_location("backup", REPO_ROOT / "scripts" / "backup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_backup_skips_regenerable_files(world, tmp_path):
    backup = load_backup()
    emb = settings.data_dir / "documents" / "standards" / "embeddings" / "e.npy"
    emb.parent.mkdir(parents=True, exist_ok=True)
    emb.write_bytes(b"x")
    backup.main(["--dest", str(tmp_path)])
    [z] = list(tmp_path.glob("citydata_*.zip"))
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("_backup_manifest.json"))
    assert "catalog.duckdb" in names
    assert "cities/chennai/roads/layers/roads.parquet" in names
    assert not any(n.endswith(".pmtiles") or n.endswith(".npy") or "/tiles/" in n for n in names)
    assert manifest["skipped_regenerable"] >= 2 and manifest["data_dir"] == str(settings.data_dir)


def test_backup_refuses_destination_inside_data_dir(world):
    import pytest
    backup = load_backup()
    with pytest.raises(SystemExit):
        backup.main(["--dest", str(settings.data_dir / "backups")])


def test_skip_rules():
    from pathlib import Path
    skipped = load_backup().skipped
    assert skipped(Path("cities/chennai/roads/tiles/roads.pmtiles"))
    assert skipped(Path("documents/x/embeddings/a.bin"))
    assert not skipped(Path("raw/roads/osm/2026-09-25/boundary.geojson"))
