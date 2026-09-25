"""FastAPI entry point. Core endpoints live here; each module mounts its own router."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from core import modules
from core.config import APP_VERSION, settings
from core.inbox import api as inbox_api
from core.layers import registry
from core.llm import client as llm
from core.store import catalog, layers, paths

MODULES = modules.discover()


@asynccontextmanager
async def lifespan(app: FastAPI):
    catalog.init_data_dir()
    topic_ids = [t["topic"] for t in registry.topics()]
    for city in registry.city_configs():
        catalog.upsert_city(city, topic_ids)
    yield


app = FastAPI(title="City Planning OS", version=APP_VERSION, lifespan=lifespan)

app.include_router(inbox_api.router)
for m in MODULES:
    app.include_router(m.router)


@app.get("/health")
def health():
    checks = catalog.health()
    ok = checks["data_dir_writable"] and checks["spatial_ok"]
    return {"status": "ok" if ok else "degraded", "version": APP_VERSION, **checks}


@app.get("/api/system")
def system():
    """What the UI needs to show about the environment (e.g. whether prompts leave the machine)."""
    i = llm.info()
    return {
        "version": APP_VERSION,
        "llm_provider": i.provider,
        "llm_model": i.model,
        "llm_is_external": i.external,
    }


@app.get("/api/cities")
def cities():
    return catalog.list_cities()


@app.get("/api/topics")
def topics():
    return registry.topics()


@app.get("/api/modules")
def list_modules():
    return [{"name": m.NAME, "label": m.LABEL} for m in MODULES]


@app.get("/api/cities/{city_id}/layers")
def city_layers(city_id: str):
    """Built layers for a city, joined with their YAML definitions (label, tiles, ...)."""
    defs = {d["layer_id"]: d for d in registry.layer_defs()}
    out = []
    for layer in catalog.list_layers(city_id):
        d = defs.get(layer["layer_id"], {})
        tiles_file = paths.tiles_path(city_id, layer["topic"], layer["layer_id"])
        out.append({
            "layer_id": layer["layer_id"],
            "topic": layer["topic"],
            "label": d.get("label", layer["layer_id"]),
            "geometry_type": layer["geometry_type"],
            "feature_count": layer["feature_count"],
            "built_at": layer["built_at"],
            "id_column": d.get("id_column"),
            "sources": layer["sources"],
            "tiles_url": (f"/api/tiles/{city_id}/{layer['topic']}/{layer['layer_id']}.pmtiles"
                          if tiles_file.exists() else None),
            "tiles": d.get("tiles"),
            "kind": d.get("kind", "built"),
            "color": d.get("color"),
            "summary_fields": d.get("summary_fields", []),
            "has_sample_data": any(i["stats"].get("is_sample") for i in catalog.list_imports(city_id, layer["layer_id"])),
        })
    return out


@app.get("/api/cities/{city_id}/layers/{layer_id}/features")
def layer_features(city_id: str, layer_id: str, bbox: str | None = None, limit: int = 5000):
    """GeoJSON for small layers (imported data), cut to the map view. Big layers use tiles."""
    box = None
    if bbox:
        try:
            box = tuple(float(v) for v in bbox.split(","))
            assert len(box) == 4
        except (ValueError, AssertionError):
            raise HTTPException(422, "bbox must be minLon,minLat,maxLon,maxLat")
    try:
        return layers.features_geojson(city_id, layer_id, box, min(limit, 20000))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/tiles/{city_id}/{topic}/{layer_id}.pmtiles")
def layer_tiles(city_id: str, topic: str, layer_id: str):
    """Serves a PMTiles file; FileResponse handles the HTTP range requests the map makes."""
    f = paths.tiles_path(city_id, topic, layer_id)
    if not f.resolve().is_relative_to(settings.data_dir) or not f.exists():
        raise HTTPException(404, "No tiles for this layer")
    return FileResponse(f, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-cache"})
