from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime
import httpx, os, json, time
from pathlib import Path
from urllib.parse import urlparse

app = FastAPI(title="FormaDigital Pocket")

HARV3ST_URL = os.getenv("HARV3ST_URL", "http://127.0.0.1:5050")
AUTH_TOKEN = os.getenv("POCKET_AUTH_TOKEN", "changeme")
STATE_DIR = Path("/home/yura/formadigital_app/pocket/runs")
STATE_DIR.mkdir(parents=True, exist_ok=True)
security = HTTPBearer(auto_error=False)


class SearchRequest(BaseModel):
    query: str
    filters: dict | None = None


async def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    token = (credentials.credentials if credentials and credentials.credentials else "").strip()
    if not token or token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token


def _extract_leads(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("leads", "data", "results", "businesses", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
        if "data" in data and isinstance(data["data"], dict):
            for key in ("leads", "results", "businesses", "items"):
                v = data["data"].get(key)
                if isinstance(v, list):
                    return v
    return []


def _norm_url(u: str | None):
    if not u:
        return None
    u = u.strip()
    if not u:
        return None
    if not u.startswith("http"):
        u = "https://" + u
    try:
        p = urlparse(u)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return u


def _cms_hint(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    if any(k in host for k in ["wordpress", "wp-content"]):
        return "wordpress"
    if "shopify" in host:
        return "shopify"
    if any(k in host for k in ["wixsite", "wix.com"]):
        return "wix"
    return None


def sample_reviews_text(lead: dict) -> str:
    for key in ("google_reviews", "reviews", "reviews_sample", "reviews_text", "comments"):
        val = lead.get(key)
        if not val:
            continue
        if isinstance(val, list):
            texts = []
            for item in val[:5]:
                if isinstance(item, dict):
                    texts.append(item.get("text") or item.get("review") or item.get("content") or item.get("comment") or "")
                elif isinstance(item, str):
                    texts.append(item)
            txt = " ".join([t for t in texts if t])
            if txt.strip():
                return txt
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def score_lead(lead: dict) -> dict:
    website = lead.get("website") or lead.get("url") or lead.get("link")
    website_norm = _norm_url(website)
    has_web = bool(website_norm)

    ig = lead.get("instagram") or lead.get("social_instagram")
    fb = lead.get("facebook") or lead.get("social_facebook")
    has_social = any([ig, fb])

    rating = None
    try:
        rating = float(lead.get("rating")) if lead.get("rating") is not None else None
    except Exception:
        rating = None

    reviews_count = None
    try:
        reviews_count = int(lead.get("reviews_count")) if lead.get("reviews_count") is not None else None
    except Exception:
        reviews_count = None

    reviews_text = sample_reviews_text(lead).lower()
    text_context = " ".join([
        str(lead.get("category") or ""),
        str(lead.get("description") or ""),
        reviews_text,
    ])

    web_score = 100.0 if not has_web else 0.0
    gmb_score = 20.0 if rating is not None else 0.0
    gmb_score += 20.0 if reviews_count and reviews_count >= 50 else 0.0
    gmb_score += 30.0 if bool(lead.get("address") or lead.get("location")) else 0.0
    gmb_score += 30.0 if bool(lead.get("phone") or lead.get("telephone") or lead.get("contact_phone")) else 0.0

    whatsapp_score = 0.0
    if any(k in text_context for k in ["turnos", "reserva", "pedidos", "delivery", "consulta", "horario", "precios"]):
        whatsapp_score += 40.0
    if rating is not None and rating < 4.0:
        whatsapp_score += 20.0
    if not has_web:
        whatsapp_score += 10.0

    erp_score = 0.0
    if any(k in text_context for k in ["stock", "depósito", "mayorista", "menú", "carta", "servicios", "pedidos"]):
        erp_score += 40.0
    if reviews_count and reviews_count >= 200:
        erp_score += 30.0

    lead.update({
        "website_norm": website_norm,
        "has_web": has_web,
        "has_social": has_social,
        "rating": rating,
        "reviews_count": reviews_count,
        "cms": _cms_hint(website_norm),
        "web_alive": None,
        "web_score": max(0.0, min(100.0, float(web_score))),
        "gmb_score": max(0.0, min(100.0, float(gmb_score))),
        "whatsapp_score": max(0.0, min(100.0, float(whatsapp_score))),
        "erp_score": max(0.0, min(100.0, float(erp_score))),
        "reviews_sample": sample_reviews_text(lead),
    })
    return lead


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/search")
async def search(body: SearchRequest, _token: str = Depends(require_auth)):
    if not body.query or not str(body.query).strip():
        raise HTTPException(status_code=400, detail="query requerido")

    search_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    target = STATE_DIR / f"{search_id}.json"
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            r = await client.post(f"{HARV3ST_URL}/api/search", json={"query": body.query})
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Harv3st error: {e}")
        raw_start = r.json()

    leads = []
    for _ in range(120):
        await __import__("asyncio").sleep(2)
        try:
            r2 = await client.get(f"{HARV3ST_URL}/api/data/scored")
            data = r2.json()
            leads = _extract_leads(data)
            if leads:
                break
        except Exception:
            pass

    payload = {
        "search_id": search_id,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "query": body.query,
        "filters": body.filters or {},
        "harv3st_start_response": raw_start,
        "enriched": False,
        "leads": [score_lead(lead or {}) for lead in (leads or [])],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return {"search_id": search_id, "leads_count": len(payload["leads"])}


@app.get("/leads/{search_id}")
def leads(search_id: str, _token: str = Depends(require_auth)):
    target = STATE_DIR / f"{search_id}.json"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Search not found")
    return JSONResponse(json.loads(target.read_text()))


@app.post("/analyze/{search_id}/{idx}")
async def analyze(search_id: str, idx: int, _token: str = Depends(require_auth)):
    target = STATE_DIR / f"{search_id}.json"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Search not found")
    data = json.loads(target.read_text())
    leads = data.get("leads", [])
    if idx < 0 or idx >= len(leads):
        raise HTTPException(status_code=404, detail="Lead index not found")
    lead = leads[idx]
    return {
        "ok": True,
        "summary": {
            "name": lead.get("name"),
            "opportunity": [
                {"service": "Web", "score": lead.get("web_score")},
                {"service": "GMB", "score": lead.get("gmb_score")},
                {"service": "WhatsApp IA", "score": lead.get("whatsapp_score")},
                {"service": "ERP", "score": lead.get("erp_score")},
            ],
        },
        "rationale": "Contexto inicial: completitud de ficha y señales visibles.",
        "weaknesses": ["Sin web" if not lead.get("has_web") else None, "Sin celular" if not (lead.get("phone") or lead.get("telephone")) else None],
        "strengths": ["Reseñas" if lead.get("reviews_count") else None],
        "sales_angle": "Prosigue con validación por llamada y captura de consultas habituales.",
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>FormaDigital Pocket</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <style>
        .fade { opacity: .6; }
      </style>
    </head>
    <body class="bg-gray-50 text-gray-900">
      <div class="max-w-6xl mx-auto p-4">
        <h1 class="text-2xl font-bold mb-1">FormaDigital Pocket</h1>
        <p class="text-sm text-gray-600 mb-4">Prospección real + contexto 360. Datos desde Google Maps; sin inventos.</p>

        <form id="form" class="bg-white border rounded p-3 space-y-2">
          <input id="q" placeholder="Rubro + zona, ej: cafeterías en Haedo" class="w-full border rounded p-2" required />
          <input id="token" type="password" placeholder="Token de acceso" class="w-full border rounded p-2 text-sm" required />
          <input id="filters" placeholder="Filtros JSON opcionales" class="w-full border rounded p-2 text-sm" />
          <button type="submit" class="bg-black text-white px-4 rounded">Buscar</button>
        </form>

        <div id="status" class="text-sm mt-2 fade">—</div>
        <div id="results" class="mt-4"></div>
      </div>

      <script>
        const form = document.getElementById('form');
        const status = document.getElementById('status');
        const results = document.getElementById('results');
        form.onsubmit = async (e) => {
          e.preventDefault();
          results.innerHTML = '';
          status.textContent = 'Buscando leads...';
          const token = document.getElementById('token').value || '';
          let filters = {};
          try { filters = JSON.parse(document.getElementById('filters').value || '{}'); } catch {}
          const res = await fetch('/search', {
            method:'POST',
            headers:{'Content-Type':'application/json','Authorization':'Bearer ' + token},
            body:JSON.stringify({ query: document.getElementById('q').value, filters })
          });
          const init = await res.json();
          if (!res.ok) { status.textContent = 'Error: ' + JSON.stringify(init); return; }
          status.textContent = 'Leads reportados: ' + (init.leads_count ?? 0) + ' | Cargando...';
          const data = await fetch('/leads/' + init.search_id, { headers:{'Authorization':'Bearer ' + token} }).then(r => r.json());
          status.textContent = 'Leads: ' + data.leads.length + ' | ' + data.created_at;
          const rows = data.leads.map((lead, idx) => {
            const opportunity = [
              { key: 'Web', score: lead.web_score },
              { key: 'GMB', score: lead.gmb_score },
              { key: 'WhatsApp', score: lead.whatsapp_score },
              { key: 'ERP', score: lead.erp_score },
            ].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 2);
            const angles = opportunity.map(o => o.key + ' (' + (o.score ?? 0) + ')').join(' + ');
            const contact = [lead.phone, lead.telephone, lead.contact_phone].find(Boolean) || '';
            const address = lead.address || lead.location || '';
            const website = lead.website_norm || lead.website || '';
            const reviews = lead.reviews_count != null ? lead.reviews_count : '?';
            const cms = lead.cms || '';
            return `
              <div class="bg-white border rounded p-3 mb-2">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="font-semibold text-lg">${escapeHtml(lead.name || 'Sin nombre')}</div>
                    <div class="text-sm text-gray-600">${escapeHtml(lead.category || '')}${address ? ' • ' + escapeHtml(address) : ''}</div>
                    <div class="text-sm">${contact ? '📞 ' + escapeHtml(contact) + ' • ' : ''}${website ? '🌐 <a href="${website}" target="_blank" rel="noreferrer">${escapeHtml(website)}</a>' + (cms ? ' (' + escapeHtml(cms) + ')' : '') + ' • ' : ''}⭐ ${lead.rating != null ? lead.rating + ' (' + reviews + ' reseñas)' : 'sin rating'}</div>
                    <div class="text-sm mt-1">Oportunidad: <strong>${escapeHtml(angles || 'sin señal clara')}</strong></div>
                  </div>
                </div>
              </div>
            `;
          }).join('');
          results.innerHTML = '<h2 class="text-xl font-semibold mb-2">Resultados</h2>' + (rows || '<p class="text-sm">Sin resultados.</p>');
        };

        function escapeHtml(s) { return String(s || '').replace(/[&<>"']/g, m => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[m]); }
      </script>
    </body>
    </html>
    """
