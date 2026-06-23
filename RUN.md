# FormaDigital Pocket — Runbook

## Estado actual (23/06/2026)

| Componente | Puerto | PID | Estado |
|------------|--------|-----|--------|
| Pocket API (FastAPI) | 0.0.0.0:3123 | (ver ps) | ✅ Activo |
| Harv3st (Flask) | 127.0.0.1:5050 | 28422 | ✅ Activo |
| Playwright/Chromium | — | — | ✅ Instalado y funcional |
| Base de datos Harv3st | `data/leads.json` | — | ✅ Con datos (según scraping) |
| Resultados Pocket | `pocket/runs/` | — | ✅ Búsquedas guardadas |

## Dependencias del sistema (Chromium/Playwright)

### Fix libatk — PENDIENTE

Ejecutar (requiere sudo):

```bash
sudo apt-get update -qq
sudo apt-get install -y libatk1.0-0t64 libatk-bridge2.0-0 \
  libgdk-pixbuf2.0-0 libgtk-3-0 libasound2 libnss3 \
  libnspr4 libdrm2 libxkbcommon0
```

Si no recordás la clave de sudo, podés ejecutar como root directo:

```bash
su -
# (si sabés la clave de root)
```

O intentar que Playwright instale las dependencias automáticamente:

```bash
cd /home/yura/formadigital_app/services/harv3st
.venv/bin/python -m playwright install-deps chromium
```

### Verificar que Chromium funciona

```bash
cd /home/yura/formadigital_app/services/harv3st
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.launch(headless=True)
b.close()
p.stop()
print('✅ Chromium OK')
"
```

Si no tira error, el scraper ya funciona.

## Dependencias Python

```bash
# Pocket API
cd /home/yura/formadigital-pocket
.venv/bin/python -m pip install -r requirements.pocket.txt

# Harv3st
cd /home/yura/formadigital_app/services/harv3st
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

## Arranque

### 1. Harv3st (scraper server)

```bash
setsid /home/yura/formadigital_app/services/harv3st/.venv/bin/python \
  /home/yura/formadigital_app/services/harv3st/manager.py server \
  </dev/null &>/tmp/harv3st.log &
```

### 2. Pocket API

```bash
setsid /home/yura/formadigital-pocket/.venv/bin/python -m uvicorn \
  pocket_api:app --host 0.0.0.0 --port 3123 \
  </dev/null &>/tmp/pocket.log &
```

### 3. Verificar health

```bash
curl http://127.0.0.1:3123/health
# → {"ok":true}
```

## Uso

### Buscar leads
```bash
curl -X POST http://127.0.0.1:3123/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer changeme" \
  -d '{"query":"cafeterías en Haedo"}'
```

### Ver resultados de una búsqueda
```bash
curl http://127.0.0.1:3123/leads/<search_id> \
  -H "Authorization: Bearer changeme"
```

### Frontend web
Abrir `http://<ip>:3123/` en el navegador.
Token por defecto: `changeme`

## APIs Harv3st (directas)

```bash
# Estado del scraper
curl -s http://127.0.0.1:5050/api/status

# Datos crudos (leads scrapeados)
curl -s http://127.0.0.1:5050/api/data

# Datos con scoring
curl -s http://127.0.0.1:5050/api/data/scored

# Iniciar scraping directo (sin Pocket)
curl -X POST http://127.0.0.1:5050/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"cafeterías en Haedo"}'
```

## Bugs conocidos (ya fixeados en el código)

### 1. Pocket API — polling fuera del `async with` (FIXEADO)

El `httpx.AsyncClient` se usaba fuera de su bloque `async with`. Se movió el loop de polling adentro.  
Archivo: `pocket_api.py`

Antes:
```python
async with httpx.AsyncClient(...) as client:
    r = await client.post(...)
    raw_start = r.json()

leads = []
for _ in range(120):          # ← client ya cerrado acá
    r2 = await client.get(...)
```

Después:
```python
async with httpx.AsyncClient(...) as client:
    r = await client.post(...)
    raw_start = r.json()
    leads = []
    for _ in range(120):
        r2 = await client.get(...)
```

### 2. import asyncio faltante (FIXEADO)

Se usaba `await __import__("asyncio").sleep(2)` en vez de `import asyncio` al inicio.

## Logs

```bash
# Harv3st
tail -f /home/yura/formadigital_app/services/harv3st/scraper.log
tail -f /tmp/harv3st.log

# Pocket API
tail -f /tmp/pocket.log
```

## Matar servicios

```bash
kill 24805   # Harv3st
kill 24852   # Pocket API
```
