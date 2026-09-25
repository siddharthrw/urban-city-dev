"""FastAPI entry point. Core endpoints live here; each module mounts its own router."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from core import modules
from core.config import APP_VERSION, settings
from core.layers import registry
from core.store import catalog, paths

MODULES = modules.discover()


@asynccontextmanager
async def lifespan(app: FastAPI):
    catalog.init_data_dir()
    topic_ids = [t["topic"] for t in registry.topics()]
    for city in registry.city_configs():
        catalog.upsert_city(city, topic_ids)
    yield


app = FastAPI(title="City Planning OS", version=APP_VERSION, lifespan=lifespan)

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
    return {
        "version": APP_VERSION,
        "llm_provider": settings.llm_provider,
        "llm_is_external": settings.llm_is_external,
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
        })
    return out


@app.get("/api/tiles/{city_id}/{topic}/{layer_id}.pmtiles")
def layer_tiles(city_id: str, topic: str, layer_id: str):
    """Serves a PMTiles file; FileResponse handles the HTTP range requests the map makes."""
    f = paths.tiles_path(city_id, topic, layer_id)
    if not f.resolve().is_relative_to(settings.data_dir) or not f.exists():
        raise HTTPException(404, "No tiles for this layer")
    return FileResponse(f, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-cache"})
