from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime
import httpx, os, json, asyncio, re
from pathlib import Path
from urllib.parse import urlparse

app = FastAPI(title="FormaDigital Pocket")

HARV3ST_URL = os.getenv("HARV3ST_URL", "http://127.0.0.1:5050")
AUTH_TOKEN = os.getenv("POCKET_AUTH_TOKEN", "changeme")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")
STATE_DIR = Path("/home/yura/formadigital_app/pocket/runs")
STATE_DIR.mkdir(parents=True, exist_ok=True)
security = HTTPBearer(auto_error=False)


class SearchRequest(BaseModel):
    query: str
    near: str | None = None
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


def _get(lead: dict, *keys):
    for k in keys:
        v = lead.get(k)
        if v is not None:
            if isinstance(v, str) and v.strip():
                return v.strip()
            if not isinstance(v, str):
                return v
    return None


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
        netloc = p.netloc.lower()
        if any(skip in netloc for skip in ["search.google.com", "google.com/search"]):
            return None
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
    website = _get(lead, "website", "url", "link")
    website_norm = _norm_url(website)
    has_web = bool(website_norm)

    ig = _get(lead, "instagram", "social_instagram")
    fb = _get(lead, "facebook", "social_facebook")
    has_social = bool(ig or fb)

    rating = None
    try:
        rating = float(lead.get("rating") or lead.get("averageRating") or 0) or None
    except Exception:
        rating = None

    reviews_count = None
    try:
        reviews_count = int(lead.get("reviews_count") or lead.get("reviewCount") or 0) or None
    except Exception:
        reviews_count = None

    reviews_text = sample_reviews_text(lead).lower()
    text_context = " ".join([
        str(lead.get("category") or lead.get("categories") or ""),
        str(lead.get("description") or lead.get("businessDescription") or ""),
        reviews_text,
    ])

    address = _get(lead, "address", "location", "fullAddress")
    phone = _get(lead, "phone", "telephone", "contact_phone", "phones")

    web_score = 100.0 if not has_web else 0.0
    gmb_score = 20.0 if rating is not None else 0.0
    gmb_score += 20.0 if reviews_count and reviews_count >= 50 else 0.0
    gmb_score += 30.0 if bool(address) else 0.0
    gmb_score += 30.0 if bool(phone) else 0.0

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
        "address": address or lead.get("address"),
        "phone": phone or lead.get("phone"),
        "category": lead.get("category") or lead.get("categories", ""),
        "cms": _cms_hint(website_norm),
        "web_alive": None,
        "web_score": max(0.0, min(100.0, float(web_score))),
        "gmb_score": max(0.0, min(100.0, float(gmb_score))),
        "whatsapp_score": max(0.0, min(100.0, float(whatsapp_score))),
        "erp_score": max(0.0, min(100.0, float(erp_score))),
        "reviews_sample": sample_reviews_text(lead),
    })
    return lead


async def check_website(url: str) -> dict:
    if not url:
        return {"alive": False, "error": "sin url"}
    result = {"url": url, "alive": False, "status": None, "title": None, "description": None, "cms": None, "error": None}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, verify=False) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            result["status"] = r.status_code
            result["alive"] = r.status_code < 500
            html = r.text
            m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
            if m:
                result["title"] = m.group(1).strip()[:200]
            m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.I)
            if m:
                result["description"] = m.group(1).strip()[:300]
            cms = _cms_hint(url)
            if not cms:
                if "wp-content" in html or "wordpress" in html:
                    cms = "wordpress"
                elif "shopify" in html:
                    cms = "shopify"
                elif "wix" in html:
                    cms = "wix"
            result["cms"] = cms
    except httpx.TimeoutException:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)[:100]
    return result


async def enrich_instagram(handle: str) -> dict:
    if not handle:
        return {"success": False, "error": "sin handle"}
    handle = handle.strip().lstrip("@")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{HARV3ST_URL}/api/instagram/enrich", json={"handle": handle})
            return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)[:100]}


async def analyze_with_openrouter(context: dict) -> str:
    if not OPENROUTER_KEY:
        return None
    prompt = f"""Eres un analista de negocios experto en prospección digital para Forma Digital, una agencia que ofrece: desarrollo web, optimización de Google Business Profile, WhatsApp con IA para atención al cliente, y sistemas Odoo/ERP.

Analiza este negocio y genera un análisis de prospección:

NOMBRE: {context.get('name', '?')}
CATEGORÍA: {context.get('category', '?')}
DIRECCIÓN: {context.get('address', '?')}
TELÉFONO: {context.get('phone', '?')}
RATING: {context.get('rating', '?')}
CANTIDAD DE RESEÑAS: {context.get('reviews_count', '?')}
TIENE WEB: {context.get('has_web', '?')}
WEB: {context.get('website', '?')}
CMS DETECTADO: {context.get('cms', '?')}
WEB VIVA: {context.get('web_alive', '?')}
TÍTULO WEB: {context.get('web_title', '?')}
DESCRIPCIÓN WEB: {context.get('web_description', '?')}
TIENE INSTAGRAM: {context.get('has_instagram', '?')}
INSTAGRAM: {context.get('instagram_handle', '?')}
INSTAGRAM DATA: {json.dumps(context.get('instagram_data', {}), ensure_ascii=False)}
TIENE FACEBOOK: {context.get('has_facebook', '?')}
RESEÑAS SAMPLE: {context.get('reviews_sample', '?')[:500]}

Genera un análisis estructurado con:
1. FORTALEZAS: qué está haciendo bien el negocio (basado en datos reales, no inventes)
2. DEBILIDADES: qué le falta o puede mejorar (solo datos reales)
3. OPORTUNIDADES: qué servicios de Forma Digital le vendrían bien y por qué
4. ANGULO DE VENTA: cómo encarar la conversación con el dueño
5. RESUMEN: un párrafo corto que describa el negocio

IMPORTANTE: No inventes datos. Basate únicamente en la información provista."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                }
            )
            data = r.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"Error al llamar a OpenRouter: {e}"


def heuristic_analysis(lead: dict, web_info: dict | None, ig_data: dict | None) -> dict:
    name = lead.get("name", "?")
    has_web = lead.get("has_web", False)
    has_social = lead.get("has_social", False)
    rating = lead.get("rating")
    reviews = lead.get("reviews_count")
    phone = lead.get("phone") or lead.get("telephone")
    category = str(lead.get("category") or lead.get("categories", ""))
    address = lead.get("address") or lead.get("location") or ""
    web_alive = web_info.get("alive") if web_info else None
    web_title = web_info.get("title") if web_info else None
    web_cms = lead.get("cms")
    if web_info:
        web_cms = web_cms or web_info.get("cms")
    ig_active = ig_data.get("success") if ig_data else False
    ig_info = ig_data.get("data", {}) if ig_data and ig_data.get("success") else {}

    strengths = []
    weaknesses = []
    opportunities = []
    sales_angle_parts = []

    if rating and rating >= 4.0:
        strengths.append(f"Buena reputación ({rating}/5 en Google)")
    elif rating and rating < 3.5:
        weaknesses.append(f"Rating bajo ({rating}/5) — pueden estar perdiendo clientes")

    if reviews and reviews >= 50:
        strengths.append(f"Alto volumen de reseñas ({reviews}) — el negocio tiene tráfico constante")
    elif reviews and reviews < 10:
        weaknesses.append("Muy pocas reseñas — poca presencia digital")

    if has_web:
        if web_alive is True:
            strengths.append("Tiene sitio web funcionando")
            if web_title:
                strengths.append(f"Web activa con título descriptivo")
            if web_cms:
                strengths.append(f"Usa {web_cms} — fácil de mantener/mejorar")
        elif web_alive is False:
            weaknesses.append("Sitio web caído o no responde")
        else:
            weaknesses.append("No tiene sitio web — oportunidad para desarrollo web")
    else:
        weaknesses.append("No tiene sitio web — oportunidad para desarrollo web")

    if has_social:
        if ig_active and ig_info.get("followers", 0) > 0:
            strengths.append(f"Instagram activo con {ig_info.get('followers', 0)} seguidores")
            if ig_info.get("posts", 0) > 0:
                strengths.append(f"Publica contenido en Instagram ({ig_info.get('posts', 0)} posts)")
        else:
            pass
    else:
        weaknesses.append("Sin presencia en redes sociales")

    food_keywords = ["restaurant", "café", "cafetería", "bar", "comida", "delivery", "pizzería", "heladería", "panadería"]
    retail_keywords = ["tienda", "local", "ferretería", "librería", "indumentaria", "comercio"]
    service_keywords = ["turnos", "reserva", "consulta", "horario", "precios", "servicios", "taller"]

    cat_lower = category.lower()
    if any(k in cat_lower for k in food_keywords):
        opportunities.append("WhatsApp con IA para gestión de pedidos/delivery")
        sales_angle_parts.append("tiene alta rotación de clientes y necesita agilizar la atención")
    if any(k in cat_lower for k in retail_keywords):
        opportunities.append("Odoo/ERP para control de stock y facturación")
        sales_angle_parts.append("maneja inventario y podría optimizar sus ventas con un sistema")
    if not has_web:
        opportunities.append("Sitio web profesional con presencia digital completa")
        sales_angle_parts.append("no tiene web y está perdiendo clientes que buscan online")

    if phone and not has_web:
        opportunities.append("Landing page + WhatsApp automatizado")
        sales_angle_parts.append("tiene consultas por teléfono y podría automatizarlas")

    if rating and rating < 4.0 and reviews and reviews > 10:
        opportunities.append("Google Business Profile optimizado para mejorar reputación")
        sales_angle_parts.append("tiene reseñas regulares pero su rating es mejorable")

    if not sales_angle_parts:
        sales_angle_parts.append("es candidato a una revisión digital completa")

    reviews_sample = lead.get("reviews_sample", "") or ""
    if "mal" in reviews_sample.lower() or "lento" in reviews_sample.lower() or "queja" in reviews_sample.lower():
        weaknesses.append("Quejas recurrentes en reseñas")

    return {
        "name": name,
        "strengths": [s for s in strengths if s],
        "weaknesses": [w for w in weaknesses if w],
        "opportunities": opportunities,
        "sales_angle": f"Este negocio {', '.join(sales_angle_parts)}. " if sales_angle_parts else "Contactar para ofrecer diagnóstico digital gratuito.",
        "recommended_services": opportunities,
        "web_check": {
            "alive": web_alive,
            "title": web_title,
            "cms": web_cms,
        } if web_info else None,
        "instagram": {
            "found": ig_active,
            "followers": ig_info.get("followers", 0) if ig_active else None,
            "posts": ig_info.get("posts", 0) if ig_active else None,
        } if ig_active else None,
        "analysis_source": "heuristic",
    }


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
            search_payload = {"query": body.query}
            if body.near:
                search_payload["near"] = body.near
            r = await client.post(f"{HARV3ST_URL}/api/search", json=search_payload)
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Harv3st error: {e}")
        raw_start = r.json()

        leads = []
        for _ in range(120):
            await asyncio.sleep(2)
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
def get_leads(search_id: str, _token: str = Depends(require_auth)):
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

    web_info = None
    website = lead.get("website_norm") or lead.get("website")
    if website:
        web_info = await check_website(website)
        lead["web_alive"] = web_info.get("alive")
        lead["web_title"] = web_info.get("title")
        if web_info.get("cms"):
            lead["cms"] = web_info.get("cms")

    ig_data = None
    ig_handle = _get(lead, "instagram", "social_instagram")
    if ig_handle:
        ig_data = await enrich_instagram(ig_handle)
        if ig_data.get("success"):
            lead["instagram_data"] = ig_data.get("data")

    result = heuristic_analysis(lead, web_info, ig_data)

    if OPENROUTER_KEY:
        context = {
            "name": lead.get("name"),
            "category": lead.get("category"),
            "address": lead.get("address"),
            "phone": lead.get("phone"),
            "rating": lead.get("rating"),
            "reviews_count": lead.get("reviews_count"),
            "has_web": lead.get("has_web"),
            "website": website,
            "cms": lead.get("cms"),
            "web_alive": lead.get("web_alive"),
            "web_title": lead.get("web_title"),
            "web_description": web_info.get("description") if web_info else None,
            "has_instagram": bool(ig_handle),
            "instagram_handle": ig_handle,
            "instagram_data": ig_data.get("data") if ig_data and ig_data.get("success") else {},
            "has_facebook": bool(_get(lead, "facebook", "social_facebook")),
            "reviews_sample": lead.get("reviews_sample", ""),
        }
        llm_analysis = await analyze_with_openrouter(context)
        if llm_analysis and not llm_analysis.startswith("Error"):
            result["llm_analysis"] = llm_analysis
            result["analysis_source"] = "llm"

    data["leads"][idx] = lead
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return result


@app.get("/export/{search_id}")
def export(search_id: str, _token: str = Depends(require_auth)):
    target = STATE_DIR / f"{search_id}.json"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Search not found")
    data = json.loads(target.read_text())
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


@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>FormaDigital Pocket</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <style>
        .fade { opacity: .6; }
        .analysis { background: #f9fafb; border-left: 3px solid #3b82f6; padding: 0.75rem; margin-top: 0.5rem; font-size: 0.875rem; }
        .analysis strong { color: #1e40af; }
        #map { height: 450px; border-radius: 0.5rem; }
        .leaflet-popup-content { margin: 0.5rem; font-size: 0.8rem; }
        .leaflet-popup-content strong { font-size: 0.9rem; }
      </style>
    </head>
    <body class="bg-gray-50 text-gray-900">
      <div class="max-w-6xl mx-auto p-4">
        <h1 class="text-2xl font-bold mb-1">FormaDigital Pocket</h1>
        <p class="text-sm text-gray-600 mb-4">Prospección para vendedor. Datos reales de Google Maps + web + redes.</p>

        <form id="form" class="bg-white border rounded p-3 space-y-2">
          <div class="flex gap-2">
            <input id="q" placeholder="Rubro, ej: cafeterías" class="w-1/2 border rounded p-2" required />
            <input id="near" placeholder="Zona, ej: Haedo" class="w-1/2 border rounded p-2" />
          </div>
          <input id="token" type="password" placeholder="Token de acceso" class="w-full border rounded p-2 text-sm" required />
          <button type="submit" class="bg-black text-white px-4 py-2 rounded">Buscar</button>
        </form>

        <div id="status" class="text-sm mt-2 fade">Listo. Ingresá un rubro y buscá.</div>

        <div class="flex gap-4 mt-4">
          <div id="results" class="w-1/2"></div>
          <div id="map" class="w-1/2 sticky top-4" style="height:450px"></div>
        </div>
      </div>

      <script>
        let map = null;
        let markers = [];

        function initMap() {
          map = L.map('map').setView([-34.61, -58.38], 12);
          L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'
          }).addTo(map);
        }

        function updateMap(leads) {
          if (!map) initMap();
          markers.forEach(m => map.removeLayer(m));
          markers = [];

          const bounds = [];
          const hasCoords = leads.filter(l => l.latitude && l.longitude);
          hasCoords.forEach(lead => {
            const lat = parseFloat(lead.latitude);
            const lng = parseFloat(lead.longitude);
            if (isNaN(lat) || isNaN(lng)) return;
            const popup = '<strong>' + escapeHtml(lead.name || '?') + '</strong><br>' +
              (lead.rating ? '⭐ ' + lead.rating + ' (' + (lead.reviews_count || '?') + ')' : '') +
              (lead.category ? '<br>' + escapeHtml(lead.category) : '');
            const m = L.marker([lat, lng]).addTo(map).bindPopup(popup);
            markers.push(m);
            bounds.push([lat, lng]);
          });

          if (bounds.length > 0) {
            map.fitBounds(bounds, { padding: [30, 30] });
          } else {
            map.setView([-34.61, -58.38], 12);
          }
        }

        const form = document.getElementById('form');
        const status = document.getElementById('status');
        const results = document.getElementById('results');
        initMap();

        form.onsubmit = async (e) => {
          e.preventDefault();
          results.innerHTML = '';
          status.textContent = 'Buscando leads en Google Maps...';
          const token = document.getElementById('token').value || '';
          const q = document.getElementById('q').value;
          const near = document.getElementById('near').value;
          const body = { query: q };
          if (near) body.near = near;
          const res = await fetch('/search', {
            method:'POST',
            headers:{'Content-Type':'application/json','Authorization':'Bearer ' + token},
            body: JSON.stringify(body)
          });
          const init = await res.json();
          if (!res.ok) { status.textContent = 'Error: ' + JSON.stringify(init); return; }
          status.textContent = 'Leads: ' + (init.leads_count ?? 0) + ' | Cargando detalles...';
          const data = await fetch('/leads/' + init.search_id, { headers:{'Authorization':'Bearer ' + token} }).then(r => r.json());
          status.textContent = data.leads.length + ' leads encontrados';
          updateMap(data.leads);

          const rows = await Promise.all(data.leads.map(async (lead, idx) => {
            const contact = [lead.phone, lead.telephone, lead.contact_phone].find(Boolean) || '';
            const address = lead.address || lead.location || '';
            const website = lead.website_norm || lead.website || '';
            const reviews = lead.reviews_count != null ? lead.reviews_count : '?';
            const cms = lead.cms || '';
            const ig = lead.instagram || '';
            const fb = lead.facebook || '';

            let analysisHtml = '';
            try {
              const ana = await fetch('/analyze/' + init.search_id + '/' + idx, {
                headers:{'Authorization':'Bearer ' + token}
              }).then(r => r.json());
              if (ana.strengths && ana.strengths.length) {
                analysisHtml += '<div class="analysis"><strong>Fortalezas:</strong> ' + escapeHtml(ana.strengths.join('; ')) + '</div>';
              }
              if (ana.weaknesses && ana.weaknesses.length) {
                analysisHtml += '<div class="analysis"><strong>Debilidades:</strong> ' + escapeHtml(ana.weaknesses.join('; ')) + '</div>';
              }
              if (ana.opportunities && ana.opportunities.length) {
                analysisHtml += '<div class="analysis"><strong>Oportunidades:</strong> ' + escapeHtml(ana.opportunities.join('; ')) + '</div>';
              }
              if (ana.sales_angle) {
                analysisHtml += '<div class="analysis" style="border-left-color: #059669;"><strong>Angulo de venta:</strong> ' + escapeHtml(ana.sales_angle) + '</div>';
              }
              if (ana.llm_analysis) {
                analysisHtml += '<div class="analysis" style="border-left-color: #8b5cf6;"><strong>Análisis IA:</strong><pre style="white-space:pre-wrap;margin:0.5rem 0 0">' + escapeHtml(ana.llm_analysis) + '</pre></div>';
              }
            } catch(e) { analysisHtml = '<div class="analysis fade">Error al analizar</div>'; }

            const opportunity = [
              { key: 'Web', score: lead.web_score },
              { key: 'GMB', score: lead.gmb_score },
              { key: 'WhatsApp', score: lead.whatsapp_score },
              { key: 'ERP', score: lead.erp_score },
            ].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 2);
            const angles = opportunity.map(o => o.key + ' (' + (o.score ?? 0) + ')').join(' + ');

            return `
              <div class="bg-white border rounded p-3 mb-2">
                <div class="flex items-start justify-between">
                  <div class="w-full">
                    <div class="font-semibold text-lg">${escapeHtml(lead.name || 'Sin nombre')}</div>
                    <div class="text-sm text-gray-600">${escapeHtml(lead.category || '')}${address ? ' • ' + escapeHtml(address) : ''}</div>
                    <div class="text-sm">${contact ? '📞 ' + escapeHtml(contact) + ' ' : ''}${website ? '🌐 <a href="${website}" target="_blank" rel="noreferrer">${escapeHtml(website)}</a>' + (cms ? ' (' + escapeHtml(cms) + ')' : '') + ' ' : ''}⭐ ${lead.rating != null ? lead.rating + ' (' + reviews + ' reseñas)' : 'sin rating'}${ig ? ' 📷 @' + escapeHtml(ig) : ''}${fb ? ' 👍 ' + escapeHtml(fb) : ''}</div>
                    <div class="text-sm mt-1">Oportunidad: <strong>${escapeHtml(angles || 'sin señal clara')}</strong></div>
                    ${analysisHtml}
                  </div>
                </div>
              </div>
            `;
          }));
          const exportLink = '/export/' + init.search_id;
          results.innerHTML = '<div class="flex justify-between items-center mb-2"><h2 class="text-xl font-semibold">Resultados</h2><a href="' + exportLink + '" target="_blank" class="text-sm text-blue-600 underline">Exportar texto</a></div>' + (rows.join('') || '<p class="text-sm">Sin resultados.</p>');
        };

        function escapeHtml(s) { return String(s || '').replace(/[&<>"']/g, m => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[m]); }
      </script>
    </body>
    </html>
    """
