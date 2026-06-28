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


FRONTEND_HTML = """
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


@app.get("/", response_class=HTMLResponse)
def index():
    return FRONTEND_HTML
