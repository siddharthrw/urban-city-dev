"""The design endpoint, on the made-up road network (uses the repo's real rules, read-only)."""
import io

import pytest

D = "/api/roads/chennai/segments"


def design(client, seg_id, **body):
    return client.post(f"{D}/{seg_id}/design", json=body)


def test_design_a_segment_returns_options_that_sum_to_its_width(client):
    r = design(client, "1-2-0")  # secondary, two-way, lanes=2 -> estimated 12 m
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["row_m"] == 12.0 and res["width_source"] == "estimated"
    assert [o["option_id"] for o in res["options"]] == ["traffic", "walking"]
    assert res["dropped"][0]["option_id"] == "balanced" and res["dropped"][0]["reason"]
    assert all(o["total_cm"] == 1200 for o in res["options"])
    assert res["segment"]["seg_id"] == "1-2-0" and res["segment"]["name"] == "Usman Road"
    assert any("ESTIMATE" in w for w in res["warnings"])


def test_manual_width_override_is_marked_manual_and_can_unlock_more_options(client):
    res = design(client, "1-2-0", row_m=20).json()
    assert res["row_m"] == 20 and res["width_source"] == "manual"
    assert [o["option_id"] for o in res["options"]] == ["balanced", "traffic", "walking"]
    assert res["segment"]["road_width_m"] == 12.0  # the road's own width is untouched
    assert not any("ESTIMATE" in w for w in res["warnings"])


def test_same_width_as_the_road_is_not_treated_as_manual(client):
    assert design(client, "1-2-0", row_m=12.0).json()["width_source"] == "estimated"


def test_context_ticks_are_applied(client):
    res = design(client, "1-2-0", row_m=24, context=["bus_route", "school_nearby"]).json()
    assert res["context"] == ["bus_route", "school_nearby"]
    walking = next(o for o in res["options"] if o["option_id"] == "walking")
    assert walking["name"] == "Walking & bus"
    assert any("school" in w.lower() for w in res["warnings"])


def test_one_way_segment_is_designed_one_way(client):
    res = design(client, "18-19-0", row_m=12).json()  # one-way tertiary
    assert res["oneway"] is True
    assert all(not o["metrics"]["has_median"] for o in res["options"])


def test_validation_errors(client):
    assert design(client, "nope").status_code == 404
    assert design(client, "1-2-0", context=["earthquake"]).status_code == 422
    assert design(client, "1-2-0", row_m=1).status_code == 422
    assert design(client, "1-2-0", row_m=500).status_code == 422
    assert client.post("/api/roads/atlantis/segments/1-2-0/design").status_code == 404


@pytest.fixture
def imports(client):
    """Imports made by a test are removed afterwards: the session shares one catalog, and other
    tests assert exact row counts of these layers."""
    made = []

    def upload_and_import(name, csv, layer, mapping, topic):
        sid = client.post("/api/inbox/chennai/upload", files={"file": (name, io.BytesIO(csv.encode()))},
                          data={"topic": topic}).json()["source_id"]
        r = client.post("/api/inbox/chennai/imports", json={"source_id": sid, "layer_id": layer, "mapping": mapping})
        assert r.status_code == 200, r.text
        made.append(r.json()["import_id"])

    yield upload_and_import
    for iid in made:
        client.delete(f"/api/inbox/chennai/imports/{iid}")


def test_linked_traffic_footfall_and_bus_data_feed_the_design(client, imports):
    upload_and_import = imports

    # "Cross Street" is a unique street in the test network (segments 3-6-0 and 3-7-0).
    upload_and_import("SAMPLE_design_traffic.csv", "Road,Cars,Buses\nCross Street,6000,20\n", "traffic_counts",
                      {"road_name": "Road", "cars": "Cars", "buses": "Buses"}, "people")
    upload_and_import("SAMPLE_design_foot.csv", "Road,People\nCross Street,12000\n", "footfall",
                      {"road_name": "Road", "pedestrians": "People"}, "people")
    upload_and_import("SAMPLE_design_bus.csv", "Road,Stop\nCross Street,Stop A\n", "bus_stops",
                      {"road_name": "Road", "stop_name": "Stop"}, "surroundings")

    res = design(client, "3-6-0", row_m=40).json()
    names = {i["name"]: i for i in res["inputs"]}
    assert names["Lanes needed"]["source"] == "data" and "SAMPLE" in names["Lanes needed"]["detail"]
    assert names["Pedestrians"]["source"] == "data" and "12,000" in names["Pedestrians"]["value"]
    assert names["Bus stops"]["value"] == "1"
    walking = next(o for o in res["options"] if o["option_id"] == "walking")
    assert walking["name"] == "Walking & bus"                    # bus stop data counts as a bus route
    assert walking["metrics"]["footpath_m"] >= 4.49              # 12000/2/1500 + 0.5 = 4.5 m per side
    assert all(o["total_cm"] == 4000 for o in res["options"])
    # 6000 cars + 20 buses = 6060 PCU both ways -> 3030/dir -> 3 lanes/dir wanted, but a residential
    # street is capped at 1 lane per direction, so the traffic option still draws only 2 lanes.
    assert names["Lanes needed"]["value"] == "1 per direction"
    assert next(o for o in res["options"] if o["option_id"] == "traffic")["metrics"]["lanes"] == 2

    other = design(client, "3-7-0", row_m=40).json()  # linked by name to the same street
    assert {i["name"] for i in other["inputs"]} >= {"Pedestrians", "Bus stops"}
    unrelated = design(client, "1-2-0", row_m=40).json()
    assert "Pedestrians" not in {i["name"] for i in unrelated["inputs"]}


def test_design_data_from_a_removed_import_no_longer_applies(client):
    sid = client.post("/api/inbox/chennai/upload", data={"topic": "people"},
                      files={"file": ("SAMPLE_design_foot2.csv", io.BytesIO(b"Road,People\nCross Street,3000\n"))}).json()["source_id"]
    imp = client.post("/api/inbox/chennai/imports", json={"source_id": sid, "layer_id": "footfall",
                                                          "mapping": {"road_name": "Road", "pedestrians": "People"}}).json()
    assert "Pedestrians" in {i["name"] for i in design(client, "3-6-0", row_m=30).json()["inputs"]}
    assert client.delete(f"/api/inbox/chennai/imports/{imp['import_id']}").status_code == 200
    assert "Pedestrians" not in {i["name"] for i in design(client, "3-6-0", row_m=30).json()["inputs"]}
