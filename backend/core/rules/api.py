r"""HTTP API for rules and standards documents.

Flow for a standards PDF: upload -> ingest (chunk) -> embed -> extract (LLM proposes rules into
rules/proposed/) -> a person reviews each proposal (sees the quote, page, statement) -> approve
(moves to rules/active/) or reject (deleted). Retrieval (/documents/search) works once a document
is embedded, independent of extraction -- it's what M4's citations will use later.

Flow for the expert-rules sheet: upload -> preview + auto-mapped columns -> confirm -> straight
into rules/active/ (no proposed step: these are the partner's own judgement, not an LLM guess).
"""
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from core.inbox import files, readers
from core.rules import documents, embeddings, expert_sheet, extract, loader, retrieve
from core.rules.schema import Rule, RuleError
from core.store import catalog

router = APIRouter(prefix="/api/rules", tags=["rules"])


def rule_out(r: Rule) -> dict:
    d = r.to_dict()
    d["file"] = r.file
    return d


def _source(source_id: str) -> dict:
    src = catalog.get_source(source_id)
    if src is None:
        raise HTTPException(404, f"Unknown source '{source_id}'")
    return src


@router.get("")
def list_rules(status: str | None = None, category: str | None = None):
    try:
        rules = loader.load_all()
    except RuleError as e:
        raise HTTPException(500, f"A rule file has a problem: {e}") from e
    if status:
        rules = [r for r in rules if r.status == status]
    if category:
        rules = [r for r in rules if r.category == category]
    return [rule_out(r) for r in rules]


@router.get("/{rule_id}")
def get_rule(rule_id: str):
    r = loader.get(rule_id)
    if r is None:
        raise HTTPException(404, f"No rule '{rule_id}'")
    return rule_out(r)


@router.post("/{rule_id}/approve")
def approve_rule(rule_id: str):
    try:
        return rule_out(loader.approve(rule_id))
    except RuleError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/{rule_id}/reject")
def reject_rule(rule_id: str):
    try:
        loader.reject(rule_id)
        return {"rejected": rule_id}
    except RuleError as e:
        raise HTTPException(422, str(e)) from e


# ---------- standards documents ----------

@router.get("/documents/list")
def list_documents():
    out = []
    for s in catalog.list_sources():
        if s["topic"] != "standards":
            continue
        chunks = documents.load_chunks(s["topic"], s["source_id"])
        out.append({
            "source_id": s["source_id"], "name": s["name"], "origin": s["origin"],
            "licence": s["licence"], "received_at": s["received_at"], "authority": s["authority"],
            "doc_year": s["doc_year"], "jurisdiction": s["jurisdiction"],
            "chunks": len(chunks), "embedded": embeddings.load_embeddings(s["topic"], s["source_id"]) is not None,
            "sample": files.is_sample(Path(s["path"]).name),  # the file on disk, not the (renamable) display name
        })
    return out


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...), title: str | None = Form(None),
    authority: str = Form(...), doc_year: int | None = Form(None), jurisdiction: str | None = Form(None),
):
    if authority not in ("active", "superseded"):
        raise HTTPException(422, "authority must be 'active' or 'superseded'")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(422, "Only PDF is supported for standards documents right now.")
    data = await file.read()
    sid = files.save_upload(data, file.filename or "document.pdf", topic="standards",
                            authority=authority, doc_year=doc_year, jurisdiction=jurisdiction)
    if title:
        sample_suffix = " (SAMPLE: made-up test data)" if files.is_sample(file.filename or "") else ""
        catalog.rename_source(sid, title + sample_suffix)
    src = _source(sid)
    try:
        rep = documents.ingest(src)
    except Exception as e:
        raise HTTPException(422, f"Could not read this PDF: {e}") from e
    return {"source_id": sid, "ingest": rep}


@router.post("/documents/{source_id}/embed")
def embed_document(source_id: str):
    src = _source(source_id)
    try:
        return embeddings.embed_document(src["topic"], src["source_id"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


class ExtractBody(BaseModel):
    max_chunks: int | None = None


@router.post("/documents/{source_id}/extract")
def extract_rules(source_id: str, body: ExtractBody = ExtractBody()):
    src = _source(source_id)
    if not documents.load_chunks(src["topic"], src["source_id"]):
        raise HTTPException(422, "This document has not been ingested yet.")
    if src.get("authority") == "superseded":
        raise HTTPException(422, "This document is marked superseded; it cannot be used to propose rules.")
    rules, stats = extract.extract_document(src, max_chunks=body.max_chunks)
    if not rules:
        return {"stats": stats, "rules": []}
    path = loader.write_proposed(f"doc_{source_id[-12:]}", rules)
    written = loader.load_all()
    ids = {r["rule_id"] for r in rules}
    return {"stats": stats, "path": str(path), "rules": [rule_out(r) for r in written if r.rule_id in ids]}


class SearchBody(BaseModel):
    query: str


@router.post("/documents/search")
def search_documents(body: SearchBody):
    res = retrieve.search_with_relevance(body.query)
    return {
        "found": res["found"], "message": res["message"],
        "best": _hit_out(res["best"]) if res["best"] else None,
        "checked": [{"applies": c["applies"], "reason": c["reason"], **_hit_out(c["hit"])} for c in res["checked"]],
    }


def _hit_out(h) -> dict:
    return {"source_id": h.source_id, "doc_title": h.doc_title, "page": h.page, "text": h.text, "score": round(h.score, 3)}


# ---------- expert-rules sheet ----------

@router.get("/expert-sheet/{source_id}/preview")
def preview_expert_sheet(source_id: str, sheet: str | None = None):
    src = _source(source_id)
    try:
        res, pv, cmap = expert_sheet.preview_and_map(src, sheet)
    except readers.UnsupportedFile as e:
        raise HTTPException(422, str(e)) from e
    return {"preview": pv, "mapping": cmap, "fields": list(expert_sheet.FIELDS)}


class ImportExpertSheetBody(BaseModel):
    sheet: str | None = None
    mapping: dict[str, str | None] = {}


@router.post("/expert-sheet/{source_id}/import")
def import_expert_sheet(source_id: str, body: ImportExpertSheetBody):
    src = _source(source_id)
    cmap = {k: v for k, v in body.mapping.items() if v} or None
    try:
        return expert_sheet.import_sheet(src, body.sheet, cmap)
    except (readers.UnsupportedFile, RuleError) as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # validate.Invalid, etc.
        raise HTTPException(422, str(e)) from e
