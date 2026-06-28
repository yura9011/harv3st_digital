from typing import Any
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from datetime import datetime

from pocket_api.domain.models import SearchRequest
from pocket_api.api.auth import require_auth

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

    search_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")

    try:
        await _harv3st.start_search(body.query, body.near)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Harv3st error: {e}")

    leads = await _harv3st.poll_scored_data()
    scored = [_scoring_engine.score(lead or {}) for lead in (leads or [])]

    payload = {
        "search_id": search_id,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "query": body.query,
        "filters": body.filters or {},
        "enriched": False,
        "leads": scored,
    }
    _storage.save(search_id, payload)
    return {"search_id": search_id, "leads_count": len(scored)}


@router.get("/leads/{search_id}")
def get_leads(search_id: str, _token: str = Depends(require_auth)):
    data = _storage.load(search_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Search not found")
    return JSONResponse(data)


@router.post("/analyze/{search_id}/{idx}")
async def analyze(search_id: str, idx: int, _token: str = Depends(require_auth)):
    data = _storage.load(search_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Search not found")
    leads = data.get("leads", [])
    if idx < 0 or idx >= len(leads):
        raise HTTPException(status_code=404, detail="Lead index not found")

    lead = leads[idx]
    result = await _analysis.analyze(lead)

    lead["analysis"] = result
    data["leads"][idx] = lead
    _storage.save(search_id, data)
    return result


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
