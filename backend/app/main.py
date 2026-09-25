"""FastAPI entry point. Core endpoints live here; each module mounts its own router."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core import modules
from core.config import APP_VERSION, settings
from core.layers import registry
from core.store import catalog

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
