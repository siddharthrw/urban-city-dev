def test_health_and_core_endpoints(client):
    h = client.get("/health").json()
    assert h["status"] == "ok", h
    assert h["spatial_ok"] is True

    cities = client.get("/api/cities").json()
    assert any(c["city_id"] == "chennai" for c in cities)

    topics = [t["topic"] for t in client.get("/api/topics").json()]
    assert topics[:3] == ["roads", "people", "surroundings"]

    assert {"name": "roads", "label": "Roads"} in client.get("/api/modules").json()


def test_system_reports_llm_privacy(client):
    s = client.get("/api/system").json()
    assert s["llm_provider"] == "ollama" and s["llm_is_external"] is False and s["llm_model"]


def test_layers_listing(client):
    roads = next(l for l in client.get("/api/cities/chennai/layers").json() if l["layer_id"] == "roads")
    assert roads["kind"] == "built" and roads["tiles_url"] and roads["feature_count"] == 11
    assert {s["source_id"] for s in roads["sources"]} == {"gcc-chennai-road-centerline-test"}
