# FormaDigital Pocket — Guía para agentes

## Stack

- **Pocket API**: FastAPI (Python 3.12) en `pocket_api.py`
- **Harv3st**: Flask + Playwright (scraper de Google Maps) en `/home/yura/formadigital_app/services/harv3st/`
- **Servicios**: Pocket API en puerto 3123, Harv3st en puerto 5050
- **Datos**: resultados de búsqueda en `/home/yura/formadigital_app/pocket/runs/`

## Estado actual (23/06/2026)

- Pocket API: ✅ funcionando en `0.0.0.0:3123`
- Harv3st: ✅ funcionando en `127.0.0.1:5050`
- Playwright/Chromium: ✅ instalado en `~/.cache/ms-playwright/`
- Cloudflare Tunnel: ✅ activo en `https://keywords-roads-magnet-trio.trycloudflare.com`
- Git: subido a `git@github.com:yura9011/harv3st_digital.git` (rama `master`)

## Endpoints Pocket API

| Endpoint | Método | Descripción |
|---|---|---|
| `/health` | GET | Health check |
| `/` | GET | Frontend HTML (Tailwind) |
| `/search` | POST | Inicia scraping + devuelve leads c/scoring |
| `/leads/{search_id}` | GET | Resultados guardados |
| `/analyze/{search_id}/{idx}` | POST | Análisis 360 de un lead (web check + Instagram + heurísticas) |
| `/export/{search_id}` | GET | Exporta texto plano para el vendedor |

## Lo que hice en esta sesión

### 1. Análisis real (`/analyze`)
- **Web checker**: visita la URL del negocio con httpx, extrae título, meta description, detecta CMS (WordPress/Shopify/Wix). Timeout 10s.
- **Instagram enrichment**: llama al endpoint `/api/instagram/enrich` de Harv3st (usa Instaloader). Rate limited a 10 req/min.
- **Análisis heurístico**: genera fortalezas, debilidades, oportunidades y ángulo de venta basado en datos reales (rating, reseñas, web, redes, categoría del negocio).
- Antes devolvía todo placeholders, ahora usa datos concretos.

### 2. OpenRouter (opcional, desactivado por defecto)
- Si se setea `OPENROUTER_API_KEY` en el entorno, el análisis usa un LLM vía OpenRouter.
- Modelo default: `mistralai/mistral-7b-instruct` (configurable con `OPENROUTER_MODEL`).
- Envía contexto completo del lead (web, Instagram, reseñas, etc.) y pide análisis estructurado.

### 3. Export (`/export`)
- Devuelve texto plano con todos los leads y sus datos para pasarle al vendedor.

### 4. Frontend
- Muestra cada lead con su análisis inline (fortalezas, debilidades, oportunidades, ángulo de venta).
- Si hay análisis de OpenRouter, se muestra en un bloque separado.
- Link a export de texto.

### 5. Pipeline completo
- `POST /search` → Harv3st scrapea Google Maps → Pocket API scorea leads → guarda en `runs/`
- `POST /analyze/{id}/{idx}` → web check + Instagram enrichment + análisis heurístico/LLM
- `GET /export/{id}` → texto plano

### 6. Cloudflare Tunnel
- Se usa `cloudflared tunnel --url http://127.0.0.1:3123` para exponer sin abrir puertos.
- Binario descargado en `/tmp/cloudflared`.
- URL actual: `https://keywords-roads-magnet-trio.trycloudflare.com` (cambia si se reinicia el tunnel).

## Para arrancar servicios

```bash
# Harv3st
setsid /home/yura/formadigital_app/services/harv3st/.venv/bin/python \
  /home/yura/formadigital_app/services/harv3st/manager.py server \
  </dev/null &>/tmp/harv3st.log &

# Pocket API
setsid /home/yura/formadigital-pocket/.venv/bin/python -m uvicorn \
  pocket_api:app --host 0.0.0.0 --port 3123 \
  </dev/null &>/tmp/pocket.log &

# Cloudflare Tunnel
/tmp/cloudflared tunnel --url http://127.0.0.1:3123 > /tmp/cloudflared.log 2>&1 &
```

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `HARV3ST_URL` | `http://127.0.0.1:5050` | URL del scraper |
| `POCKET_AUTH_TOKEN` | `changeme` | Token de acceso |
| `OPENROUTER_API_KEY` | `""` | API key de OpenRouter (vacío = sin IA) |
| `OPENROUTER_MODEL` | `mistralai/mistral-7b-instruct` | Modelo OpenRouter |

## Pendientes / mejoras posibles

- El scraper de Google Maps (Harv3st) a veces falla si Google cambia su HTML. Playwright necesita mantenimiento.
- El Instagram enrichment usa Instaloader, que puede pedir login si Instagram cambia su API.
- Agregar más fuentes de datos (Facebook, web scraping más profundo).
- Hacer que el análisis LLM vía OpenRouter sea el default cuando haya API key configurada.
- El Cloudflare Tunnel es efímero (trycloudflare) — para producción usar named tunnel con dominio propio.
- El token `changeme` está hardcodeado como default en `pocket_api.py:13`.
