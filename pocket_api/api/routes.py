import time
from typing import Any
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from datetime import datetime

from pocket_api.domain.models import SearchRequest
from pocket_api.domain.geo import filter_by_distance
from pocket_api.api.auth import require_auth
from pocket_api.adapters.logger import log_event
from pocket_api.adapters.geocode import geocode as _geocode

router = APIRouter()

_harv3st: Any = None
_storage: Any = None
_scoring_engine: Any = None
_analysis: Any = None


def init_routes(h, s, se, a):
    global _harv3st, _storage, _scoring_engine, _analysis
    _harv3st = h
    _storage = s
    _scoring_engine = se
    _analysis = a


@router.get("/health")
def health():
    return {"ok": True}


@router.post("/search")
async def search(body: SearchRequest, _token: str = Depends(require_auth)):
    if not body.query or not str(body.query).strip():
        raise HTTPException(status_code=400, detail="query requerido")

    t0 = time.time()

    if not body.no_cache:
        cached = _storage.find_by_query(body.query, body.near)
        if cached:
            log_event("cache_hit", query=body.query, near=body.near, search_id=cached.get("search_id"))
            return {"search_id": cached["search_id"], "leads_count": len(cached.get("leads", [])), "cached": True}

    search_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    log_event("search_start", search_id=search_id, query=body.query, near=body.near, radius_km=body.radius_km)

    try:
        await _harv3st.start_search(body.query, body.near, body.radius_km)
    except Exception as e:
        log_event("search_error", search_id=search_id, error=str(e)[:200])
        raise HTTPException(status_code=502, detail=f"Harv3st error: {e}")

    leads = await _harv3st.poll_scored_data()
    scored = [_scoring_engine.score(lead or {}) for lead in (leads or [])]

    if body.near and body.radius_km:
        coords = await _geocode(body.near)
        if coords:
            before = len(scored)
            scored = filter_by_distance(scored, coords[0], coords[1], body.radius_km)
            log_event("geo_filter", search_id=search_id, near=body.near, radius_km=body.radius_km,
                      before=before, after=len(scored), filtered=before - len(scored))

    elapsed_s = round(time.time() - t0, 1)
    payload = {
        "search_id": search_id,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": elapsed_s,
        "query": body.query,
        "near": body.near,
        "filters": body.filters or {},
        "enriched": False,
        "leads": scored,
    }
    _storage.save(search_id, payload)
    log_event("search_done", search_id=search_id, leads=len(scored), duration_s=elapsed_s)
    return {"search_id": search_id, "leads_count": len(scored)}


@router.get("/runs")
def list_runs(limit: int = 20, _token: str = Depends(require_auth)):
    return _storage.list(limit)


@router.post("/search/sync")
async def search_sync(body: SearchRequest, _token: str = Depends(require_auth)):
    if not body.query or not str(body.query).strip():
        raise HTTPException(status_code=400, detail="query requerido")

    t0 = time.time()

    if not body.no_cache:
        cached = _storage.find_by_query(body.query, body.near)
        if cached:
            return cached

    search_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    log_event("search_sync_start", search_id=search_id, query=body.query, near=body.near)

    try:
        await _harv3st.start_search(body.query, body.near, body.radius_km)
    except Exception as e:
        log_event("search_sync_error", search_id=search_id, error=str(e)[:200])
        raise HTTPException(status_code=502, detail=f"Harv3st error: {e}")

    leads = await _harv3st.poll_scored_data()
    scored = [_scoring_engine.score(lead or {}) for lead in (leads or [])]

    if body.near and body.radius_km:
        coords = await _geocode(body.near)
        if coords:
            before = len(scored)
            scored = filter_by_distance(scored, coords[0], coords[1], body.radius_km)
            log_event("geo_filter_sync", search_id=search_id, near=body.near, radius_km=body.radius_km,
                      before=before, after=len(scored), filtered=before - len(scored))

    elapsed_s = round(time.time() - t0, 1)
    payload = {
        "search_id": search_id,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": elapsed_s,
        "query": body.query,
        "near": body.near,
        "filters": body.filters or {},
        "enriched": False,
        "leads": scored,
    }
    _storage.save(search_id, payload)
    log_event("search_sync_done", search_id=search_id, leads=len(scored), duration_s=elapsed_s)
    return payload


@router.get("/leads/{search_id}")
def get_leads(search_id: str, _token: str = Depends(require_auth)):
    data = _storage.load(search_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Search not found")
    return JSONResponse(data)


@router.post("/analyze/{search_id}/{idx}")
async def analyze(search_id: str, idx: int, request: Request, _token: str = Depends(require_auth)):
    data = _storage.load(search_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Search not found")
    leads = data.get("leads", [])
    if idx < 0 or idx >= len(leads):
        raise HTTPException(status_code=404, detail="Lead index not found")

    lead = leads[idx]
    or_key = request.headers.get("x-openrouter-key")
    lead_name = lead.get("name", "?")
    log_event("analyze_start", search_id=search_id, idx=idx, lead=lead_name, has_key=bool(or_key))
    result = await _analysis.analyze(lead, openrouter_key=or_key)

    lead["analysis"] = result
    data["leads"][idx] = lead
    _storage.save(search_id, data)
    log_event("analyze_done", search_id=search_id, idx=idx, lead=lead_name, source=result.get("analysis_source"))
    return result


@router.get("/logs")
def get_logs(lines: int = 40, _token: str = Depends(require_auth)):
    from pocket_api.adapters.logger import get_logger
    logger = get_logger()
    if not logger.handlers:
        return {"lines": []}
    fh = logger.handlers[0]
    if not hasattr(fh, "baseFilename"):
        return {"lines": []}
    log_path = fh.baseFilename
    try:
        with open(log_path, "r") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines:]
        return {"lines": [l.rstrip("\n") for l in tail], "total": len(all_lines)}
    except Exception as e:
        return {"error": str(e), "lines": []}


@router.get("/export/{search_id}")
def export(search_id: str, _token: str = Depends(require_auth)):
    data = _storage.load(search_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Search not found")
    lines = [
        f"FormaDigital Pocket — Export",
        f"Búsqueda: {data['query']}",
        f"Fecha: {data['created_at']}",
        f"Total leads: {len(data['leads'])}",
        "",
    ]
    for i, lead in enumerate(data["leads"], 1):
        lines.append(f"{'='*60}")
        lines.append(f"#{i} — {lead.get('name', '?')}")
        lines.append(f"{'='*60}")
        lines.append(f"  Categoría: {lead.get('category', '?')}")
        lines.append(f"  Dirección: {lead.get('address', lead.get('location', '?'))}")
        lines.append(f"  Teléfono: {lead.get('phone') or lead.get('telephone') or '-'}")
        lines.append(f"  Rating: {lead.get('rating', '?')} ({lead.get('reviews_count', '?')} reseñas)")
        lines.append(f"  Web: {lead.get('website_norm') or lead.get('website') or 'Sin web'}")
        if lead.get("cms"):
            lines.append(f"  CMS: {lead['cms']}")
        if lead.get("instagram"):
            lines.append(f"  Instagram: @{lead['instagram']}")
        if lead.get("facebook"):
            lines.append(f"  Facebook: {lead['facebook']}")
        lines.append(f"  Scores: Web={lead.get('web_score',0)} GMB={lead.get('gmb_score',0)} WhatsApp={lead.get('whatsapp_score',0)} ERP={lead.get('erp_score',0)}")
        lines.append("")

    return PlainTextResponse("\n".join(lines))
