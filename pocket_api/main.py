from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from datetime import datetime
import os
from pathlib import Path

from pocket_api.domain.models import SearchRequest
from pocket_api.domain.scoring import ScoringEngine
from pocket_api.domain.analysis import AnalysisOrchestrator
from pocket_api.api.auth import require_auth, AUTH_TOKEN, OPENROUTER_KEY, OPENROUTER_MODEL
from pocket_api.adapters.harv3st import Harv3stClient
from pocket_api.adapters.web_checker import WebChecker
from pocket_api.adapters.instagram import InstagramEnricher
from pocket_api.adapters.openrouter import OpenRouterClient
from pocket_api.adapters.storage import FileRunRepository

app = FastAPI(title="FormaDigital Pocket")

HARV3ST_URL = os.getenv("HARV3ST_URL", "http://127.0.0.1:5050")
STATE_DIR = Path(os.getenv("POCKET_STATE_DIR", "/home/yura/formadigital_app/pocket/runs"))

scoring_engine = ScoringEngine()
web_checker = WebChecker()
instagram = InstagramEnricher(HARV3ST_URL)
openrouter = OpenRouterClient(OPENROUTER_KEY, OPENROUTER_MODEL) if OPENROUTER_KEY else None
harv3st = Harv3stClient(HARV3ST_URL)
storage = FileRunRepository(STATE_DIR)
analysis = AnalysisOrchestrator(web_checker, instagram, openrouter)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/search")
async def search(body: SearchRequest, _token: str = Depends(require_auth)):
    if not body.query or not str(body.query).strip():
        raise HTTPException(status_code=400, detail="query requerido")

    search_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")

    try:
        await harv3st.start_search(body.query, body.near)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Harv3st error: {e}")

    leads = await harv3st.poll_scored_data()
    scored = [scoring_engine.score(lead or {}) for lead in (leads or [])]

    payload = {
        "search_id": search_id,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "query": body.query,
        "filters": body.filters or {},
        "enriched": False,
        "leads": scored,
    }
    storage.save(search_id, payload)
    return {"search_id": search_id, "leads_count": len(scored)}


@app.get("/leads/{search_id}")
def get_leads(search_id: str, _token: str = Depends(require_auth)):
    data = storage.load(search_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Search not found")
    return JSONResponse(data)


@app.post("/analyze/{search_id}/{idx}")
async def analyze(search_id: str, idx: int, _token: str = Depends(require_auth)):
    data = storage.load(search_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Search not found")
    leads = data.get("leads", [])
    if idx < 0 or idx >= len(leads):
        raise HTTPException(status_code=404, detail="Lead index not found")

    lead = leads[idx]
    result = await analysis.analyze(lead)

    data["leads"][idx] = lead
    storage.save(search_id, data)
    return result


@app.get("/export/{search_id}")
def export(search_id: str, _token: str = Depends(require_auth)):
    data = storage.load(search_id)
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


FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse((FRONTEND_DIR / "index.html").read_text())
