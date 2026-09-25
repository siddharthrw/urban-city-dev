"""Roads pipeline on the made-up network: segments, lengths, names, widths, tiles, API.
The OSM download step is not exercised (no network in tests)."""
import gzip
import math
from datetime import datetime

import mapbox_vector_tile
import pandas as pd
import pytest
from pmtiles.reader import MmapSource, Reader
from pyproj import Geod

from core.store import catalog, db, paths
from modules.roads.pipelines import build_roads as br
from tests.conftest import LAT, LON, MAIN_ROAD_SEGS


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def by_id(world):
    return world.set_index("seg_id")


# ---------- segments ----------

def test_two_way_streets_become_one_segment_each(world):
    assert world["seg_id"].is_unique
    assert len(world) == 11  # 4 Usman Road + 2 Cross + 2x 1st Street + namesake + unnamed + one-way
    assert set(MAIN_ROAD_SEGS) <= set(world["seg_id"])


def test_osm_attributes_parsed(world):
    s = by_id(world)
    assert s.loc["1-2-0", "lanes_osm"] == 2 and not s.loc["1-2-0", "oneway"]
    one_way = s.loc["18-19-0"]
    assert one_way["oneway"]
    assert one_way["road_class"] == "tertiary"      # the higher class wins when OSM merges ways
    assert one_way["osm_width_hint"] == "6"         # kept as a hint...
    assert one_way["width_m"] != 6                  # ...never used as the right-of-way


def test_parsers():
    assert br._lanes("2") == 2 and br._lanes(["2", "3"]) == 3 and br._lanes("2;3") is None and br._lanes(None) is None
    assert br._best_class(["residential", "primary"]) == "primary"
    assert br._first(["", "A Road", "B Road"]) == "A Road" and br._first(float("nan")) is None
    assert br._as_bool(["no", "yes"]) and not br._as_bool("no")
    assert br._raw_str(["5", None]) == "5" and br._raw_str(float("nan")) is None


def test_lengths_match_ellipsoid(world):
    geod = Geod(ellps="WGS84")
    for _, r in world.iterrows():
        assert r["length_m"] == pytest.approx(geod.geometry_length(r.geometry), rel=1e-3)


def test_report_counts(world):
    rep = br.report(world)
    assert rep["segments"] == 11
    assert rep["length_check_vs_ellipsoid_median_rel_diff"] < 0.001


# ---------- names ----------

def test_official_names_matched_along_the_street(world):
    s = by_id(world)
    assert (s.loc[MAIN_ROAD_SEGS, "name_official"] == "USMAN RD.").all()
    assert (s.loc[MAIN_ROAD_SEGS, "name_match"] == "same").all()  # "Usman Road" vs "USMAN RD."
    assert s.loc["3-6-0", "name_official"] == "Cross St."
    assert s.loc["3-6-0", "name_match"] == "same"  # "Cross St." normalises to "cross street"
    # A crossing official line (Cross St.) never names a Usman Road segment; far streets get nothing.
    assert pd.isna(s.loc["10-11-0", "name_official"])


def test_display_name_falls_back_to_official(world):
    s = by_id(world).loc["16-17-0"]
    assert pd.isna(s["name"])
    assert s["display_name"] == "Official Only Street"
    assert s["display_name_source"] == "official"
    assert s["name_match"] == "official_only"
    assert "official only street" in s["search_key"]


def test_osm_only_names(world):
    s = by_id(world).loc["10-11-0"]
    assert s["display_name"] == "1st Street" and s["display_name_source"] == "osm"
    assert s["name_match"] == "osm_only"


# ---------- widths ----------

def test_all_estimated_without_overrides(world):
    assert set(world["width_source"]) == {"estimated"}
    assert world["width_source_detail"].str.contains("UNCITED").all()


def test_lanes_refine_the_estimate(world):
    s = by_id(world).loc["1-2-0"]
    assert s["width_m"] == pytest.approx(2 * 3.5 + 2 * 2.5)  # secondary: lanes x 3.5 + 2 x side 2.5
    assert "lanes=2" in s["width_source_detail"]


def test_verified_override_wins_and_survives_refresh(world):
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO feature_overrides VALUES (?,?,?,?,?,?,?,?)",
                    ["chennai", "roads", "1-2-0", "width_m", 12.4, "Tape survey 2026-09-20", "manual-test", datetime.now()])
    try:
        info = br.refresh_widths("chennai")
        assert info["width_source_counts"] == {"estimated": 10, "verified": 1}
        seg = pd.read_parquet(catalog.get_layer("chennai", "roads")["path"]).set_index("seg_id")
        assert seg.loc["1-2-0", "width_m"] == 12.4 and seg.loc["1-2-0", "width_source"] == "verified"
        assert seg.loc["1-2-0", "width_source_detail"] == "Tape survey 2026-09-20"
    finally:
        with db.connect() as con:
            con.execute("DELETE FROM feature_overrides WHERE source_id = 'manual-test'")
        br.refresh_widths("chennai")


def test_refresh_keeps_layer_sources(world):
    before = {s["source_id"] for s in catalog.get_layer("chennai", "roads")["sources"]}
    br.refresh_widths("chennai")
    assert {s["source_id"] for s in catalog.get_layer("chennai", "roads")["sources"]} == before


# ---------- tiles ----------

def test_tiles_contain_every_segment_at_max_zoom(world):
    with open(paths.tiles_path("chennai", "roads", "roads"), "rb") as f:
        r = Reader(MmapSource(f))
        h = r.header()
        seen = {}
        for lon, lat in [(LON + 0.002, LAT), (LON, LAT + 0.01), (LON, LAT - 0.01), (LON + 0.006, LAT + 0.005)]:
            data = r.get(h["max_zoom"], *tile_xy(lon, lat, h["max_zoom"]))
            for feat in mapbox_vector_tile.decode(gzip.decompress(data))["roads"]["features"]:
                seen[feat["properties"]["seg_id"]] = feat["properties"]
    assert seen["1-2-0"]["display_name"] == "Usman Road"
    assert seen["16-17-0"]["display_name"] == "Official Only Street"
    assert seen["1-2-0"]["width_source"] == "estimated"


def test_low_zoom_tiles_only_carry_big_roads(world):
    with open(paths.tiles_path("chennai", "roads", "roads"), "rb") as f:
        r = Reader(MmapSource(f))
        data = r.get(10, *tile_xy(LON, LAT, 10))
    classes = {f["properties"]["road_class"] for f in mapbox_vector_tile.decode(gzip.decompress(data))["roads"]["features"]}
    assert classes == {"secondary"}  # residential/tertiary dropped at z10


# ---------- API ----------

def test_api_segment(client):
    r = client.get("/api/roads/chennai/segments/1-2-0").json()
    assert r["segment"]["display_name"] == "Usman Road"
    assert r["segment"]["name_official"] == "USMAN RD."
    assert r["road"]["segments"] == 5  # 4 main segments + the far namesake share the name
    assert r["official_name_source"]["name"] == "Greater Chennai Corporation"
    assert r["linked_data"] == [] or isinstance(r["linked_data"], list)
    assert client.get("/api/roads/chennai/segments/nope").status_code == 404


def test_api_search_normalises(client):
    hits = client.get("/api/roads/chennai/search", params={"q": "usman rd"}).json()
    assert hits[0]["name"] == "Usman Road" and hits[0]["road_class"] == "secondary"
    hits = client.get("/api/roads/chennai/search", params={"q": "official only"}).json()
    assert hits[0]["name"] == "Official Only Street"
    assert client.get("/api/roads/chennai/search", params={"q": "zzzz"}).json() == []


def test_api_streets_splits_separate_streets(client):
    r = client.get("/api/roads/chennai/streets", params={"name": "1st Street"}).json()
    assert r["status"] == "ambiguous" and len(r["streets"]) == 2
    r = client.get("/api/roads/chennai/streets", params={"name": "Usman Road"}).json()
    assert r["status"] == "matched" and set(r["streets"][0]["seg_ids"]) == set(MAIN_ROAD_SEGS)
    assert "shorter street" in r["note"]


def test_api_tiles_range_request(client):
    url = next(l["tiles_url"] for l in client.get("/api/cities/chennai/layers").json() if l["layer_id"] == "roads")
    part = client.get(url, headers={"Range": "bytes=0-126"})
    assert part.status_code == 206 and len(part.content) == 127
    assert client.get("/api/tiles/chennai/roads/nope.pmtiles").status_code == 404
