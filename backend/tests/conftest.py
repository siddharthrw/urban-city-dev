"""Shared test setup.

Tests use a throwaway DATA_DIR, never the real one (set before core.config is imported).
`world` builds a small made-up road network near Chennai with the REAL pipeline code
(segments -> official names -> widths -> GeoParquet -> tiles), so every test runs against the
same shapes the app uses. Nothing here downloads anything.
"""
import json
import os
import tempfile
from datetime import date
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="citydata_test_")
os.environ["LLM_PROVIDER"] = "ollama"
os.environ.pop("NVIDIA_API_KEY", None)

import networkx as nx  # noqa: E402
import pytest  # noqa: E402

LON, LAT = 80.2500, 13.0600
D = 0.001  # ~108 m east-west, ~111 m north-south here

# Node id -> (lon, lat)
NODES = {
    # Usman Road: 4 segments west->east, crossed by Cross Street at node 3
    1: (LON, LAT), 2: (LON + D, LAT), 3: (LON + 2 * D, LAT), 4: (LON + 3 * D, LAT), 5: (LON + 4 * D, LAT),
    6: (LON + 2 * D, LAT - D), 7: (LON + 2 * D, LAT + D),                   # Cross Street
    10: (LON, LAT + 10 * D), 11: (LON + D, LAT + 10 * D),                   # 1st Street (north)
    12: (LON, LAT - 10 * D), 13: (LON + D, LAT - 10 * D),                   # 1st Street (south)
    14: (LON + 10 * D, LAT + 20 * D), 15: (LON + 10.5 * D, LAT + 20 * D),   # short "Usman Road" namesake
    16: (LON + 6 * D, LAT + 5 * D), 17: (LON + 7 * D, LAT + 5 * D),         # unnamed in OSM; official name only
    18: (LON + 6 * D, LAT - 5 * D), 19: (LON + 6 * D, LAT - 4 * D),         # one-way, merged classes, width tag
}
MAIN_ROAD_SEGS = ["1-2-0", "2-3-0", "3-4-0", "4-5-0"]


def world_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph(crs="EPSG:4326")
    for n, (x, y) in NODES.items():
        G.add_node(n, x=x, y=y)

    def two_way(u, v, osmid, **attrs):
        for a, b in ((u, v), (v, u)):
            G.add_edge(a, b, key=0, osmid=osmid, oneway=False, length=100.0, **attrs)

    for i, (u, v) in enumerate([(1, 2), (2, 3), (3, 4), (4, 5)]):
        two_way(u, v, 100 + i, highway="secondary", name="Usman Road", lanes="2")
    two_way(6, 3, 200, highway="residential", name="Cross Street")
    two_way(3, 7, 201, highway="residential", name="Cross Street")
    two_way(10, 11, 300, highway="residential", name="1st Street")
    two_way(12, 13, 301, highway="residential", name="1st Street")
    two_way(14, 15, 400, highway="residential", name="Usman Road")
    two_way(16, 17, 500, highway="residential")
    G.add_edge(18, 19, key=0, osmid=600, highway=["residential", "tertiary"], oneway=True, width="6", length=110.0)
    return G


def official_geojson() -> dict:
    """Made-up 'official centerline' file: names along Usman Road, the unnamed street and Cross Street."""
    def line(a, b, rid, name):
        return {"type": "Feature", "properties": {"road_id": rid, "road_name": name},
                "geometry": {"type": "LineString", "coordinates": [list(NODES[a]), list(NODES[b])]}}
    return {"type": "FeatureCollection", "features": [
        line(1, 5, "R1", "USMAN RD."),
        line(16, 17, "R2", "Official Only Street"),
        line(6, 7, "R3", "Cross St."),
    ]}


@pytest.fixture(scope="session")
def world():
    """Build the made-up roads layer once per test session. Returns the segments GeoDataFrame."""
    from core.layers import registry
    from core.store import catalog, paths
    from modules.roads.pipelines import build_roads as br

    catalog.init_data_dir()
    for c in registry.city_configs():
        catalog.upsert_city(c, [t["topic"] for t in registry.topics()])
    city = registry.city_config("chennai")

    raw = paths.raw_dir("roads", "gcc_centerline", "2026-01-01")
    raw.mkdir(parents=True, exist_ok=True)
    f = raw / "official_test.geojson"
    f.write_text(json.dumps(official_geojson()), encoding="utf-8")
    catalog.register_source(source_id="gcc-chennai-road-centerline-test", file=f, city_id="chennai",
                            topic="roads", name="Test official centerline", origin="made up in tests",
                            licence="test", received_at=date(2026, 1, 1))

    seg = br.to_segments(world_graph(), city)
    seg, official_ids, _ = br.official_names(seg, city)
    seg = br.apply_widths(seg, "chennai")
    br.publish("chennai", seg, official_ids)
    return seg


@pytest.fixture(scope="session")
def client(world):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


SAMPLES = Path(__file__).resolve().parents[2] / "samples"
