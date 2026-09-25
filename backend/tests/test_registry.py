import pytest

from core import modules
from core.layers import registry


def test_topics_in_display_order():
    assert [t["topic"] for t in registry.topics()][:3] == ["roads", "people", "surroundings"]


def test_layer_definitions_found_by_folder():
    defs = {d["layer_id"]: d for d in registry.layer_defs()}
    assert defs["roads"]["topic"] == "roads" and defs["traffic_counts"]["topic"] == "people"
    assert "_topic" not in defs and "_location_fields" not in defs
    with pytest.raises(LookupError):
        registry.layer_def("nope")


def test_import_fields_merge_location_fields():
    f = registry.import_fields("footfall")
    assert f["pedestrians"]["required"] and {"latitude", "longitude", "road_name", "area"} <= set(f)
    with pytest.raises(LookupError):
        registry.import_fields("roads")  # built by a pipeline, not importable


def test_city_config():
    c = registry.city_config("chennai")
    assert c["utm_epsg"] == 32644 and c["osm_boundary_id"] == "R1766358"
    assert c["official_road_names"]["name_field"] == "road_name"
    with pytest.raises(LookupError):
        registry.city_config("atlantis")


def test_modules_discovered():
    found = {m.NAME: m for m in modules.discover()}
    assert "roads" in found
    assert "roads" in found["roads"].IMPORT_LINKERS and "width_surveys" in found["roads"].IMPORT_HOOKS


def test_width_defaults_file():
    from modules.roads import widths
    d = widths.load_defaults()
    assert d["status"] == "UNCITED" and d["lanes_refinement"]["lane_width_m"] > 0
    for cls in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street"):
        assert cls in d["classes"]
