"""Roads pipeline on a tiny synthetic graph: segments, lengths, widths, layer file, tiles, API.
No network: the OSM download step is not exercised here."""
import gzip
import math
from datetime import datetime

import mapbox_vector_tile
import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pmtiles.reader import MmapSource, Reader
from pyproj import Geod

from app.main import app
from core.layers import registry
from core.store import catalog, db, layers, paths, tiles
from modules.roads.pipelines import build_roads as br

CITY = registry.city_config("chennai")


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def tiny_graph() -> nx.MultiDiGraph:
    """Three nodes ~111 m apart north-south in Chennai; one named two-way road, one unnamed one-way."""
    G = nx.MultiDiGraph(crs="EPSG:4326")
    for n, lat in [(1, 13.0600), (2, 13.0610), (3, 13.0620)]:
        G.add_node(n, x=80.2500, y=lat)
    road = dict(osmid=101, highway="secondary", name="Test Road", lanes="2", oneway=False, length=110.6)
    G.add_edge(1, 2, key=0, **road)
    G.add_edge(2, 1, key=0, **road)
    G.add_edge(2, 3, key=0, osmid=102, highway=["residential", "tertiary"], oneway=True, width="6", length=110.6)
    return G


@pytest.fixture(scope="module")
def built():
    catalog.init_data_dir()
    seg = br.apply_widths(br.to_segments(tiny_graph(), CITY), "chennai")
    out = paths.layer_path("chennai", "roads", "roads")
    layers.write_geoparquet(seg, out)
    catalog.record_layer(city_id="chennai", layer_id="roads", topic="roads", file=out,
                         geometry_type="LineString", feature_count=len(seg),
                         build_script="test", source_ids=[])
    t = registry.layer_def("roads")["tiles"]
    info = tiles.build_pmtiles(parquet=out, out=paths.tiles_path("chennai", "roads", "roads"),
                               layer_name="roads", properties=t["properties"], minzoom=14, maxzoom=15)
    return seg, info


def test_segments_are_undirected_and_parsed(built):
    seg, _ = built
    assert len(seg) == 2  # the two directions of Test Road collapse into one segment
    assert seg["seg_id"].is_unique
    road = seg.set_index("seg_id").loc["1-2-0"]
    assert road["name"] == "Test Road" and road["lanes_osm"] == 2 and not road["oneway"]
    other = seg.set_index("seg_id").loc["2-3-0"]
    assert other["road_class"] == "tertiary"  # the higher class wins when OSM merges ways
    assert other["osm_width_hint"] == "6"  # kept as a hint...
    assert other["width_m"] != 6  # ...never used as the right-of-way


def test_lengths_match_ellipsoid(built):
    seg, _ = built
    geod = Geod(ellps="WGS84")
    for _, r in seg.iterrows():
        assert r["length_m"] == pytest.approx(geod.geometry_length(r.geometry), rel=1e-3)


def test_all_estimated_without_overrides(built):
    seg, _ = built
    assert set(seg["width_source"]) == {"estimated"}
    assert seg["width_source_detail"].str.len().min() > 10


def test_verified_override_wins(built):
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO feature_overrides VALUES (?,?,?,?,?,?,?,?)",
                    ["chennai", "roads", "1-2-0", "width_m", 12.4, "Tape survey 2026-09-20", None, datetime.now()])
    try:
        seg = br.apply_widths(br.to_segments(tiny_graph(), CITY), "chennai").set_index("seg_id")
        assert seg.loc["1-2-0", "width_m"] == 12.4
        assert seg.loc["1-2-0", "width_source"] == "verified"
        assert seg.loc["2-3-0", "width_source"] == "estimated"
    finally:
        with db.connect() as con:
            con.execute("DELETE FROM feature_overrides")


def test_tiles_contain_features_with_properties(built):
    _, info = built
    assert info["tiles"] > 0
    with open(paths.tiles_path("chennai", "roads", "roads"), "rb") as f:
        r = Reader(MmapSource(f))
        data = r.get(15, *tile_xy(80.25, 13.061, 15))
        assert data is not None
        feats = mapbox_vector_tile.decode(gzip.decompress(data))["roads"]["features"]
    props = {f["properties"]["seg_id"]: f["properties"] for f in feats}
    assert props["1-2-0"]["name"] == "Test Road"
    assert props["1-2-0"]["width_source"] == "estimated"


def test_api_segment_and_search(built):
    with TestClient(app) as client:
        r = client.get("/api/roads/chennai/segments/1-2-0").json()
        assert r["segment"]["name"] == "Test Road"
        assert r["road"]["segments"] == 1
        assert client.get("/api/roads/chennai/segments/nope").status_code == 404

        hits = client.get("/api/roads/chennai/search", params={"q": "test"}).json()
        assert hits[0]["name"] == "Test Road" and hits[0]["road_class"] == "secondary"

        tiles_url = client.get("/api/cities/chennai/layers").json()[0]["tiles_url"]
        part = client.get(tiles_url, headers={"Range": "bytes=0-126"})
        assert part.status_code == 206 and len(part.content) == 127
