"""The data inbox end to end, through the HTTP API, against the made-up road network."""
import io

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

from core.config import settings
from core.store import catalog
from tests.conftest import LAT, LON, MAIN_ROAD_SEGS, NODES, SAMPLES

CITY = "/api/inbox/chennai"


def upload(client, name: str, data: bytes, topic: str) -> str:
    r = client.post(f"{CITY}/upload", files={"file": (name, io.BytesIO(data), "application/octet-stream")}, data={"topic": topic})
    assert r.status_code == 200, r.text
    return r.json()["source_id"]


def run(client, source_id, layer_id, mapping, **kw):
    return client.post(f"{CITY}/imports", json={"source_id": source_id, "layer_id": layer_id, "mapping": mapping, **kw})


def csv(rows: list[list], header: list[str]) -> bytes:
    return pd.DataFrame(rows, columns=header).to_csv(index=False).encode()


def geojson(gdf: gpd.GeoDataFrame) -> bytes:
    return gdf.to_json().encode()


TRAFFIC_HEADER = ["Road Name", "Date", "Cars", "Total", "Lat", "Lon"]
TRAFFIC_ROWS = [
    ["Usman Road", "12/08/2026", 1200, 5000, None, None],                   # row 2: exact (OSM + official)
    ["Usman Rd.", "12/08/2026", 1100, 4800, None, None],                    # row 3: abbreviation
    ["Usmann Road", "13/08/2026", 900, 4000, None, None],                   # row 4: typo -> fuzzy
    ["1st Street", "13/08/2026", 50, 300, None, None],                      # row 5: two separate streets
    ["Nowhere Lane", "13/08/2026", 10, 50, None, None],                     # row 6: not found
    ["Usman Road", "14/08/2026", "lots", 10, None, None],                   # row 7: bad number
    [None, "14/08/2026", 700, 3000, LAT + 0.00005, LON + 0.0015],           # row 8: lat/lon on Usman Road
    [None, "14/08/2026", 700, 3000, LON + 0.0025, LAT + 0.00005],           # row 9: lat/lon swapped
    [None, "14/08/2026", 700, 3000, 12.97, 77.59],                          # row 10: Bengaluru, outside city
    ["Official Only Street", "15/08/2026", 20, 90, None, None],             # row 11: name only in official file
]
TRAFFIC_MAP = {"road_name": "Road Name", "count_date": "Date", "cars": "Cars", "total_vehicles": "Total",
               "latitude": "Lat", "longitude": "Lon"}


@pytest.fixture(scope="module")
def traffic(client):
    sid = upload(client, "counts.csv", csv(TRAFFIC_ROWS, TRAFFIC_HEADER), "people")
    r = run(client, sid, "traffic_counts", TRAFFIC_MAP)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_registers_in_manifest(client, traffic):
    src = catalog.get_source(traffic["source_id"])
    assert src["topic"] == "people" and src["sha256"] and src["path"].startswith("raw")
    assert "uploads" in src["path"] and src["abs_path"].is_file()


def test_import_counts(traffic):
    s = traffic["stats"]
    assert s["rows_in_file"] == 10
    assert s["invalid"] == 2                   # bad number + outside the city
    assert s["imported"] == 8
    assert s["linked"] == 6
    assert s["unmatched"] == 2                 # 1st Street (ambiguous) + Nowhere Lane
    assert s["by_link_method"] == {"name": 3, "name_fuzzy": 1, "location": 2}
    assert any("swapped" in w for w in s["warnings"])
    assert not s["is_sample"]


def test_rejected_rows_explained(traffic):
    by_row = {p["row_no"]: p["errors"] for p in traffic["problems"]["invalid"]}
    assert by_row[7] == ["Cars: 'lots' is not a number"]
    assert "outside the city" in by_row[10][0]


def test_unmatched_rows_carry_reasons_and_candidates(traffic):
    u = {x["row_no"]: x for x in traffic["problems"]["unmatched"]}
    assert "2 separate streets" in u[5]["reason"] and len(u[5]["candidates"]) == 2
    assert all(c["seg_ids"] for c in u[5]["candidates"])
    assert "no road named" in u[6]["reason"]


def test_rows_linked_to_the_right_segments(client, traffic):
    fc = client.get("/api/cities/chennai/layers/traffic_counts/features").json()
    rows = {f["properties"]["row_no"]: f["properties"] for f in fc["features"]}
    for r in (2, 3, 4):
        assert set(rows[r]["seg_ids"]) == set(MAIN_ROAD_SEGS), r
        assert rows[r]["road_name_matched"] == "Usman Road"
    assert "Spelling differs" in rows[4]["link_note"]
    assert "shorter street" in rows[2]["link_note"]           # the short namesake is mentioned
    assert rows[8]["seg_ids"] == ["2-3-0"] and rows[8]["link_distance_m"] < 10
    assert rows[9]["seg_ids"] == ["3-4-0"]                     # swapped lat/lon still lands right
    assert rows[11]["seg_ids"] == ["16-17-0"]
    assert 5 not in rows and 6 not in rows                     # no geometry -> not on the map


def test_road_panel_lists_linked_data(client, traffic):
    r = client.get("/api/roads/chennai/segments/2-3-0").json()
    tc = next(d for d in r["linked_data"] if d["layer_id"] == "traffic_counts")
    assert sorted(x["row_no"] for x in tc["rows"]) == [2, 3, 4, 8]
    assert tc["summary_fields"][0]["label"] == "Count date"


def test_features_bbox_filter(client, traffic):
    near = client.get("/api/cities/chennai/layers/traffic_counts/features",
                      params={"bbox": f"{LON + 0.0055},{LAT + 0.0045},{LON + 0.0075},{LAT + 0.0055}"}).json()
    assert [f["properties"]["row_no"] for f in near["features"]] == [11]
    assert client.get("/api/cities/chennai/layers/traffic_counts/features", params={"bbox": "1,2"}).status_code == 422
    assert client.get("/api/cities/chennai/layers/nope/features").status_code == 404


def test_manual_link_fixes_a_row_and_survives_reimport(client, traffic):
    iid = traffic["import_id"]
    cand = next(x for x in traffic["problems"]["unmatched"] if x["row_no"] == 5)["candidates"][0]
    r = client.post(f"{CITY}/imports/{iid}/links", json={"row_no": 5, "seg_ids": cand["seg_ids"], "road_name": "1st Street"}).json()
    assert r["stats"]["unmatched"] == 1 and r["stats"]["by_link_method"]["manual"] == 1
    # Import again with the same mapping: the fix is kept, rows are replaced not duplicated.
    again = run(client, traffic["source_id"], "traffic_counts", TRAFFIC_MAP).json()
    assert again["import_id"] == iid and again["stats"]["by_link_method"]["manual"] == 1
    assert catalog.get_layer("chennai", "traffic_counts")["feature_count"] == 8
    # Clearing the link puts the row back on the unmatched list.
    r = client.post(f"{CITY}/imports/{iid}/links", json={"row_no": 5, "seg_ids": []}).json()
    assert r["stats"]["unmatched"] == 2


def test_import_detail_and_list(client, traffic):
    d = client.get(f"{CITY}/imports/{traffic['import_id']}").json()
    assert d["mapping"] == TRAFFIC_MAP and "manual_links" in d
    assert any(i["import_id"] == traffic["import_id"] for i in client.get(f"{CITY}/imports").json())
    assert client.get(f"{CITY}/imports/nope").status_code == 404


# ---------- GIS files ----------

def test_geojson_points_lines_and_areas(client):
    near_stop = Point(LON + 0.0005, LAT + 0.0001)                           # ~11 m from Usman Road
    far_stop = Point(LON + 0.02, LAT + 0.02)                                # nowhere near a road
    stops = gpd.GeoDataFrame({"Stop": ["Near", "Far"], "Boardings": [100, 5]}, geometry=[near_stop, far_stop], crs=4326)
    r = run(client, upload(client, "stops.geojson", geojson(stops), "surroundings"), "bus_stops",
            {"stop_name": "Stop", "daily_boardings": "Boardings"}).json()
    assert r["stats"]["linked"] == 1 and r["stats"]["on_map"] == 2
    assert "No road within 30 m" in r["problems"]["unmatched"][0]["reason"]

    along = LineString([NODES[1], NODES[5]])                                # the whole of Usman Road
    zone = Polygon([(LON + 0.0055, LAT + 0.0045), (LON + 0.0075, LAT + 0.0045), (LON + 0.0075, LAT + 0.0055), (LON + 0.0055, LAT + 0.0055)])
    wl = gpd.GeoDataFrame({"Depth": [30, 15]}, geometry=[along, zone], crs=4326)
    r = run(client, upload(client, "flood.geojson", geojson(wl), "surroundings"), "waterlogging", {"depth_cm": "Depth"}).json()
    fc = client.get("/api/cities/chennai/layers/waterlogging/features").json()
    segs = {f["properties"]["row_no"]: set(f["properties"]["seg_ids"]) for f in fc["features"]}
    assert segs[1] == set(MAIN_ROAD_SEGS)           # a line along the road links every segment, not the cross street
    assert segs[2] == {"16-17-0"}                   # an area links the segments inside it


def test_file_without_crs_needs_epsg(client, tmp_path):
    g = gpd.GeoDataFrame({"Layer": ["ROAD"]}, geometry=[LineString([(0, 0), (100, 0)])])
    g.to_file(tmp_path / "plan.dxf", driver="DXF")
    sid = upload(client, "plan.dxf", (tmp_path / "plan.dxf").read_bytes(), "roads")
    r = run(client, sid, "width_surveys", {"width_m": "Layer"})
    assert r.status_code == 422  # width 'ROAD' isn't a number, but first: no coordinate system
    assert "coordinate system" in r.json()["detail"] or "EPSG" in r.json()["detail"]


# ---------- width surveys -> verified ----------

def test_width_survey_upgrades_roads_to_verified_and_delete_reverts(client):
    data = csv([["Usman Road", "24.5 m", "01/09/2026", "Test surveyor"]], ["Road", "ROW Width", "Date", "By"])
    sid = upload(client, "survey.csv", data, "roads")
    r = run(client, sid, "width_surveys", {"road_name": "Road", "width_m": "ROW Width",
                                           "survey_date": "Date", "surveyed_by": "By"}).json()
    assert r["stats"]["effects"]["verified_segments"] == 4
    seg = client.get("/api/roads/chennai/segments/1-2-0").json()["segment"]
    assert seg["width_source"] == "verified" and seg["width_m"] == 24.5
    assert "survey.csv, row 2, 2026-09-01, by Test surveyor" in seg["width_source_detail"]
    assert client.get("/api/roads/chennai/segments/3-6-0").json()["segment"]["width_source"] == "estimated"

    d = client.delete(f"{CITY}/imports/{r['import_id']}").json()
    assert d["effects"]["verified_segments"] == 0
    assert client.get("/api/roads/chennai/segments/1-2-0").json()["segment"]["width_source"] == "estimated"
    assert catalog.get_layer("chennai", "width_surveys") is None      # last import gone -> layer gone
    assert catalog.get_source(sid) is not None                        # the raw file is never deleted


# ---------- samples ----------

def test_sample_files_are_labelled_everywhere(client):
    sid = upload(client, "SAMPLE_bus_stops.kml", (SAMPLES / "SAMPLE_bus_stops.kml").read_bytes(), "surroundings")
    src = catalog.get_source(sid)
    assert "SAMPLE" in src["name"] and "made-up" in src["licence"]
    r = run(client, sid, "bus_stops", {"stop_name": "stop_name"}).json()
    assert r["stats"]["is_sample"]
    fc = client.get("/api/cities/chennai/layers/bus_stops/features").json()
    assert any(f["properties"]["is_sample"] for f in fc["features"])
    layers = {l["layer_id"]: l for l in client.get("/api/cities/chennai/layers").json()}
    assert layers["bus_stops"]["has_sample_data"]


# ---------- errors ----------

def test_import_errors_are_explained(client):
    sid = upload(client, "plain.csv", csv([["x", 5]], ["Road", "Width"]), "roads")
    no_loc = run(client, sid, "width_surveys", {"width_m": "Width"})
    assert no_loc.status_code == 422 and "need a location" in no_loc.json()["detail"]
    no_req = run(client, sid, "width_surveys", {"road_name": "Road"})
    assert no_req.status_code == 422 and "Required" in no_req.json()["detail"]
    bad_col = run(client, sid, "width_surveys", {"road_name": "Road", "width_m": "Nope"})
    assert bad_col.status_code == 422 and "Nope" in bad_col.json()["detail"]
    bad_field = run(client, sid, "width_surveys", {"road_name": "Road", "width_m": "Width", "colour": "Road"})
    assert bad_field.status_code == 422
    assert run(client, "no-such-source", "width_surveys", {}).status_code == 422
    assert client.post(f"{CITY}/upload", files={"file": ("a.csv", b"a")}, data={"topic": "weather"}).status_code == 422


def test_stored_only_files(client):
    sid = upload(client, "scan.pdf", b"%PDF-1.4 not really", "roads")
    r = client.get(f"{CITY}/sources/{sid}/preview")
    assert r.status_code == 422 and "not built yet" in r.json()["detail"]
    f = next(s for s in client.get(f"{CITY}/files").json()["sources"] if s["source_id"] == sid)
    assert f["kind"] == "stored_only" and not f["system"]


# ---------- files, preview, suggest ----------

def test_same_upload_twice_is_one_source(client):
    a = upload(client, "twice.csv", b"Road,Cars\nA,1\n", "people")
    b = upload(client, "twice.csv", b"Road,Cars\nA,1\n", "people")
    c = upload(client, "twice.csv", b"Road,Cars\nA,2\n", "people")     # same name, new content: kept separately
    assert a == b and c != a
    assert catalog.get_source(c)["path"].endswith("twice (2).csv")


def test_dropped_files_are_listed_and_registered(client):
    p = settings.data_dir / "raw" / "people" / "partner" / "2026-09-01" / "footfall.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("Road,Pedestrians\nUsman Road,400\n", encoding="utf-8")
    listed = client.get(f"{CITY}/files").json()["unregistered"]
    entry = next(u for u in listed if u["name"] == "footfall.csv")
    assert entry["topic"] == "people"
    sid = client.post(f"{CITY}/register", json={"path": entry["path"]}).json()["source_id"]
    assert catalog.get_source(sid)["origin"] == "dropped into the raw folder"
    assert all(u["name"] != "footfall.csv" for u in client.get(f"{CITY}/files").json()["unregistered"])
    assert client.post(f"{CITY}/register", json={"path": "raw/nope.csv"}).status_code == 404


def test_preview_and_suggest_endpoints(client):
    sid = upload(client, "counts2.csv", csv(TRAFFIC_ROWS[:2], TRAFFIC_HEADER), "people")
    p = client.get(f"{CITY}/sources/{sid}/preview").json()
    assert p["row_count"] == 2 and [c["name"] for c in p["columns"]] == TRAFFIC_HEADER
    s = client.post(f"{CITY}/sources/{sid}/suggest", json={"layer_id": "traffic_counts"}).json()
    assert {f: v["column"] for f, v in s["mapping"].items()} == TRAFFIC_MAP
    assert s["llm"]["provider"] == "ollama" and not s["llm"]["external"]
    assert client.post(f"{CITY}/sources/{sid}/suggest", json={"layer_id": "nope"}).status_code == 404


def test_layer_types_endpoint(client):
    types = {t["layer_id"]: t for t in client.get("/api/inbox/layer-types").json()}
    assert {"traffic_counts", "footfall", "width_surveys", "bus_stops", "schools", "waterlogging"} <= set(types)
    assert types["width_surveys"]["effects"] == ["verified_width"]
    fields = {f["field"]: f for f in types["width_surveys"]["fields"]}
    assert fields["width_m"]["required"] and "aliases" not in fields["width_m"]
    assert "road_name" in fields
