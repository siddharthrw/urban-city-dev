"""HTTP API for the data inbox. Flow: upload/register -> preview -> suggest mapping -> import -> fix."""
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from core.inbox import files, importer, mapping, readers
from core.layers import registry
from core.llm import client as llm
from core.store import catalog

router = APIRouter(prefix="/api/inbox", tags=["inbox"])
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def _source(source_id: str) -> dict:
    src = catalog.get_source(source_id)
    if src is None:
        raise HTTPException(404, f"Unknown source '{source_id}'")
    return src


def _read(src: dict, sheet: str | None) -> readers.ReadResult:
    try:
        return readers.read_file(src["abs_path"], sheet)
    except readers.UnsupportedFile as e:
        raise HTTPException(422, str(e)) from e


@router.get("/layer-types")
def layer_types():
    loc = registry.location_fields()
    return [{"layer_id": d["layer_id"], "topic": d["topic"], "label": d["label"],
             "description": d.get("description", ""), "color": d.get("color"),
             "effects": d.get("effects", []),
             "fields": [{"field": f, **{k: v for k, v in s.items() if k != "aliases"}}
                        for f, s in {**d.get("fields", {}), **loc}.items()]}
            for d in registry.import_layer_defs()]


@router.get("/{city_id}/files")
def list_files(city_id: str):
    """Registered sources (with their imports) + files dropped under raw\\ but not registered yet."""
    imps: dict[str, list] = {}
    for i in catalog.list_imports(city_id):
        imps.setdefault(i["source_id"], []).append(
            {"import_id": i["import_id"], "layer_id": i["layer_id"], "status": i["status"],
             "stats": i["stats"], "updated_at": i["updated_at"]})
    sources = []
    for s in catalog.list_sources(city_id):
        sources.append({
            "source_id": s["source_id"], "name": s["name"], "topic": s["topic"], "path": s["path"],
            "origin": s["origin"], "licence": s["licence"], "received_at": s["received_at"],
            "bytes": s["bytes"], "kind": readers.kind_of(Path(s["path"])),
            "sample": files.is_sample(Path(s["path"]).name),  # the file on disk, not a (renamable) display name
            "system": not s["source_id"].startswith("file-"),  # built by pipelines, not the inbox
            "imports": imps.get(s["source_id"], []),
        })
    return {"sources": sources, "unregistered": files.unregistered()}


@router.post("/{city_id}/upload")
async def upload(city_id: str, file: UploadFile = File(...), topic: str = Form(...)):
    if topic not in {t["topic"] for t in registry.topics()}:
        raise HTTPException(422, f"Unknown topic '{topic}'")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 500 MB; copy it into the raw folder instead.")
    sid = files.save_upload(data, file.filename or "upload", topic=topic, city_id=city_id)
    return {"source_id": sid}


class RegisterBody(BaseModel):
    path: str


@router.post("/{city_id}/register")
def register(city_id: str, body: RegisterBody):
    try:
        return {"source_id": files.register_dropped(body.path, city_id)}
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(404, f"Can't register '{body.path}': {e}") from e


@router.get("/{city_id}/sources/{source_id}/preview")
def preview(city_id: str, source_id: str, sheet: str | None = None):
    return readers.preview(_read(_source(source_id), sheet))


class SuggestBody(BaseModel):
    layer_id: str
    sheet: str | None = None
    use_llm: bool = False


@router.post("/{city_id}/sources/{source_id}/suggest")
def suggest(city_id: str, source_id: str, body: SuggestBody):
    res = _read(_source(source_id), body.sheet)
    cols = readers.preview(res, n=0)["columns"]
    try:
        fields = registry.import_fields(body.layer_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    out = mapping.suggest(cols, fields, use_llm=body.use_llm, has_geometry=res.has_geometry)
    i = llm.info()
    out["llm"] = {"provider": i.provider, "model": i.model, "external": i.external}
    return out


class ImportBody(BaseModel):
    source_id: str
    layer_id: str
    mapping: dict[str, str | None]
    sheet: str | None = None
    options: dict = {}


@router.post("/{city_id}/imports")
def run_import(city_id: str, body: ImportBody):
    try:
        return importer.run_import(city_id, body.source_id, body.layer_id,
                                   {k: v for k, v in body.mapping.items() if v}, body.sheet, body.options)
    except importer.ImportError_ as e:
        raise HTTPException(422, str(e)) from e


@router.get("/{city_id}/imports")
def list_imports(city_id: str):
    return catalog.list_imports(city_id)


@router.get("/{city_id}/imports/{import_id}")
def get_import(city_id: str, import_id: str):
    rec = catalog.get_import(import_id)
    if rec is None or rec["city_id"] != city_id:
        raise HTTPException(404, "No such import")
    rec["manual_links"] = catalog.get_import_links(import_id)
    return rec


class LinkBody(BaseModel):
    row_no: int
    seg_ids: list[str]
    road_name: str | None = None


@router.post("/{city_id}/imports/{import_id}/links")
def link_row(city_id: str, import_id: str, body: LinkBody):
    """A person links an unmatched row to a road; the import re-runs so the layer picks it up."""
    rec = catalog.get_import(import_id)
    if rec is None:
        raise HTTPException(404, "No such import")
    if body.seg_ids:
        catalog.set_import_link(import_id, body.row_no, body.seg_ids, body.road_name)
    else:
        catalog.clear_import_link(import_id, body.row_no)
    return importer.run_import(city_id, rec["source_id"], rec["layer_id"], rec["mapping"], rec["sheet"], rec["options"])


@router.delete("/{city_id}/imports/{import_id}")
def delete_import(city_id: str, import_id: str):
    """Removes the import's rows from the map (and any verified widths it created). The raw file stays."""
    try:
        return importer.delete_import(import_id)
    except importer.ImportError_ as e:
        raise HTTPException(404, str(e)) from e
