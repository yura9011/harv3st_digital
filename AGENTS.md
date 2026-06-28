# FormaDigital Pocket — Guía para agentes

## Stack

- **Pocket API**: FastAPI (Python 3.12) en `pocket_api/` (package)
- **Harv3st**: Flask + Playwright (scraper de Google Maps) en `/home/yura/formadigital_app/services/harv3st/`
- **Servicios**: Pocket API en puerto 3123, Harv3st en puerto 5050
- **Datos**: resultados de búsqueda en `/home/yura/formadigital_app/pocket/runs/`

## Arquitectura (paquete pocket_api/)

```
pocket_api/
├── main.py                 ← FastAPI app factory + startup
├── api/
│   ├── auth.py             ← Token auth compartido
│   └── routes.py           ← Endpoints thin (solo orquestan)
├── domain/                 ← Deep module: lógica de negocio
│   ├── models.py           ← SearchRequest, Lead, AnalysisResult
│   ├── scoring.py          ← ScoringEngine + estrategias
│   └── analysis.py         ← AnalysisOrchestrator
├── adapters/               ← Infraestructura con seams
│   ├── harv3st.py          ← Harv3stClient
│   ├── web_checker.py      ← WebChecker
│   ├── instagram.py        ← InstagramEnricher
│   ├── openrouter.py       ← OpenRouterClient (opcional)
│   └── storage.py          ← RunRepository (file-based)
└── frontend/
    └── index.html          ← Frontend SPA
tests/
├── test_scoring.py
└── test_analysis.py
```

### Principios

- **Routes son thin**: solo parsean request, llaman domain, devuelven response
- **Domain es deep**: mucha lógica detrás de interfaces chicas
- **Adapters tienen seams**: toda IO tiene una interfaz intercambiable
- **Ubiquitous Language**: usar términos del glosario (Lead, Scoring, Run, etc.)

### Glosario

| Término | Significado |
|---------|------------|
| Lead | Negocio encontrado en Google Maps candidato a cliente |
| Scoring | Puntuación 0-100 por categoría de servicio |
| Web/GMB/WhatsApp/ERP Score | Oportunidad por servicio |
| Análisis 360 | Web check + Instagram + heurísticas + (opcional) LLM |
| Run | Una ejecución completa de búsqueda + scoring |
| Harv3st | Scraper de Google Maps vía Playwright |
| Código de color | Verde (completa), Amarillo (incompleta), Rojo (oportunidad) |

## Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | GET | Frontend HTML (estático) |
| `/search` | POST | Inicia scraping + scoring |
| `/leads/{search_id}` | GET | Resultados guardados |
| `/analyze/{search_id}/{idx}` | POST | Análisis 360 de un lead |
| `/export/{search_id}` | GET | Export texto plano |

## Estado actual

- Pocket API: ✅ funcionando en `0.0.0.0:3123`
- Harv3st: ✅ funcionando en `127.0.0.1:5050`
- Playwright/Chromium: ✅ instalado
- Cloudflare Tunnel: ✅ activo (efímero)

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `HARV3ST_URL` | `http://127.0.0.1:5050` | URL del scraper |
| `POCKET_AUTH_TOKEN` | `changeme` | Token de acceso |
| `OPENROUTER_API_KEY` | `""` | API key de OpenRouter (vacío = sin IA) |
| `OPENROUTER_MODEL` | `mistralai/mistral-7b-instruct` | Modelo OpenRouter |

## Para arrancar servicios

```bash
# Pocket API (package)
setsid /home/yura/formadigital-pocket/.venv/bin/python -m uvicorn \
  pocket_api:app --host 0.0.0.0 --port 3123 \
  </dev/null &>/tmp/pocket.log &

# Harv3st
setsid /home/yura/formadigital_app/services/harv3st/.venv/bin/python \
  /home/yura/formadigital_app/services/harv3st/manager.py server \
  </dev/null &>/tmp/harv3st.log &

# Cloudflare Tunnel
/tmp/cloudflared tunnel --url http://127.0.0.1:3123 > /tmp/cloudflared.log 2>&1 &
```

## ADRs

Ver `docs/adr/`.
