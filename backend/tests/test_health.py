from fastapi.testclient import TestClient

from app.main import app


def test_health_and_core_endpoints():
    with TestClient(app) as client:
        h = client.get("/health").json()
        assert h["status"] == "ok", h
        assert h["spatial_ok"] is True

        cities = client.get("/api/cities").json()
        assert any(c["city_id"] == "chennai" for c in cities)

        topics = {t["topic"] for t in client.get("/api/topics").json()}
        assert {"roads", "people", "surroundings"} <= topics

        assert {"name": "roads", "label": "Roads"} in client.get("/api/modules").json()
