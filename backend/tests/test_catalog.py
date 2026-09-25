from datetime import date

import pytest

from core.config import settings
from core.store import catalog, paths


@pytest.fixture
def raw_file():
    p = paths.raw_dir("roads", "unit", "2026-02-01") / "f.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    return p


def test_register_source_records_checksum_and_relative_path(world, raw_file):
    catalog.register_source(source_id="unit-1", file=raw_file, name="f.csv", origin="test", licence="CC0",
                            received_at=date(2026, 2, 1), topic="roads", city_id="chennai")
    s = catalog.get_source("unit-1")
    assert s["sha256"] == catalog.sha256_file(raw_file) and s["bytes"] == raw_file.stat().st_size
    assert not s["path"].startswith(str(settings.data_dir))  # stored relative, so DATA_DIR can move
    assert s["abs_path"] == raw_file.resolve()
    assert str(raw_file.resolve().relative_to(settings.data_dir)) in catalog.registered_paths()


def test_latest_source_picks_newest(world, raw_file):
    for sid, d in [("pref-old", date(2025, 1, 1)), ("pref-new", date(2026, 1, 1))]:
        catalog.register_source(source_id=sid, file=raw_file, name=sid, origin="t", licence="t", received_at=d, topic="roads")
    assert catalog.latest_source("pref-")["source_id"] == "pref-new"
    assert catalog.latest_source("no-such-prefix") is None


def test_record_layer_replaces_source_links(world, raw_file):
    catalog.register_source(source_id="unit-a", file=raw_file, name="a", origin="t", licence="t", received_at=date(2026, 1, 1), topic="roads")
    catalog.register_source(source_id="unit-b", file=raw_file, name="b", origin="t", licence="t", received_at=date(2026, 1, 1), topic="roads")
    for ids in (["unit-a", "unit-b"], ["unit-b"]):
        catalog.record_layer(city_id="chennai", layer_id="unit_layer", topic="roads", file=raw_file,
                             geometry_type="Point", feature_count=1, build_script="t", source_ids=ids)
    assert [s["source_id"] for s in catalog.get_layer("chennai", "unit_layer")["sources"]] == ["unit-b"]
    catalog.delete_layer_record("chennai", "unit_layer")
    assert catalog.get_layer("chennai", "unit_layer") is None


def test_overrides_replaced_per_source(world):
    catalog.replace_overrides("chennai", "unit", "width_m", "src-1", {"s1": (10.0, "a"), "s2": (11.0, "b")})
    catalog.replace_overrides("chennai", "unit", "width_m", "src-2", {"s3": (12.0, "c")})
    catalog.replace_overrides("chennai", "unit", "width_m", "src-1", {"s1": (9.5, "a2")})
    got = catalog.get_overrides("chennai", "unit", "width_m")
    assert got == {"s1": {"value": 9.5, "detail": "a2"}, "s3": {"value": 12.0, "detail": "c"}}
    catalog.replace_overrides("chennai", "unit", "width_m", "src-1", {})
    catalog.replace_overrides("chennai", "unit", "width_m", "src-2", {})
    assert catalog.get_overrides("chennai", "unit", "width_m") == {}


def test_import_records_and_links_round_trip(world):
    rec = {"import_id": "imp-unit", "city_id": "chennai", "source_id": "s", "layer_id": "l", "sheet": None,
           "mapping": {"a": "A"}, "options": {"epsg": 32644}, "status": "imported",
           "stats": {"when": date(2026, 1, 1)}, "problems": {"invalid": []}}
    catalog.save_import(rec)
    first = catalog.get_import("imp-unit")
    catalog.save_import(rec)  # re-save keeps created_at
    again = catalog.get_import("imp-unit")
    assert again["created_at"] == first["created_at"] and again["mapping"] == {"a": "A"}
    assert again["stats"] == {"when": "2026-01-01"}
    catalog.set_import_link("imp-unit", 3, ["x", "y"], "Road")
    assert catalog.get_import_links("imp-unit") == {3: {"seg_ids": ["x", "y"], "road_name": "Road"}}
    catalog.clear_import_link("imp-unit", 3)
    assert catalog.get_import_links("imp-unit") == {}
    catalog.delete_import("imp-unit")
    assert catalog.get_import("imp-unit") is None


def test_cities_and_health(world):
    assert catalog.list_cities()[0]["city_id"] == "chennai"
    h = catalog.health()
    assert h["data_dir_writable"] and h["spatial_ok"] and h["free_disk_gb"] > 0
