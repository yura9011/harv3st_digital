# FormaDigital Pocket — Documento de Diseño

## Visión del Producto

Herramienta de prospección B2B para vendedores de FormaDigital.
Encuentra negocios en Google Maps, analiza automáticamente su presencia
digital, y los presenta priorizados para que el humano decida a quién
contactar.

## Stack

| Capa | Tecnología |
|------|-----------|
| API | FastAPI (Python 3.12) |
| Scraper | Harv3st (Flask + Playwright) |
| Frontend | HTML estático + Tailwind + Leaflet |
| Persistencia | Archivos JSON en disco |
| Autenticación | Bearer token único compartido |
| Análisis opcional | OpenRouter (LLM) |

## Usuarios

- Vendedores de FormaDigital (equipo pequeño, ~2-5 personas)
- Un token compartido — no usan concurrentemente

## Flujo de Usuario

1. Abre la app → ingresa token compartido
2. Busca por rubro + zona (ej: "cafeterías" + "Haedo")
3. (Futuro) radio en km alrededor de la zona
4. Sistema scrapea Google Maps via Harv3st
5. Cada lead se analiza automáticamente: web check + Instagram + scoring
6. Resultados se muestran con código de colores:
   - **Verde** = presencia digital completa (oportunidad baja/lead frío)
   - **Amarillo** = presencia incompleta (oportunidad media)
   - **Rojo** = poca presencia digital (oportunidad alta)
7. El humano revisa, analiza y decide contactar

## Arquitectura

```
pocket_api/                  ← Paquete principal
├── __init__.py
├── main.py                  ← FastAPI app, StaticFiles, startup
├── api/                     ← Capa de interfaz HTTP (thin)
│   ├── __init__.py
│   ├── auth.py              ← Token auth compartido
│   └── routes.py            ← Endpoints (solo orquestan)
├── domain/                  ← Lógica de negocio (deep module)
│   ├── __init__.py
│   ├── models.py            ← SearchRequest, Lead, AnalysisResult
│   ├── scoring.py           ← ScoringEngine + estrategias
│   └── analysis.py          ← AnalysisOrchestrator
├── adapters/                ← Infraestructura con seams
│   ├── __init__.py
│   ├── harv3st.py           ← Harv3stClient
│   ├── web_checker.py       ← WebChecker
│   ├── instagram.py         ← InstagramEnricher
│   ├── openrouter.py        ← OpenRouterClient (opcional)
│   └── storage.py           ← RunRepository (file-based)
├── frontend/
│   └── index.html           ← Frontend SPA
tests/
├── __init__.py
├── test_scoring.py
└── test_analysis.py
```

## Plan de Implementación

### Fase 1: Estructura base
- Crear directorios y `__init__.py` en cada subpaquete
- Mover modelos a `domain/models.py`
- Mover auth a `api/auth.py`
- Crear `main.py` con app factory
- `pocket_api.py` pasa a ser entrypoint que re-exporta `app`

### Fase 2: Extraer adapters
- `adapters/storage.py`: RunRepository interface + FileRunRepository
- `adapters/harv3st.py`: extraer HTTP calls de /search
- `adapters/web_checker.py`: extraer check_website()
- `adapters/instagram.py`: extraer enrich_instagram()
- `adapters/openrouter.py`: extraer analyze_with_openrouter()

### Fase 3: Deepen domain module
- `domain/scoring.py`: ScoringEngine con LeadScorer interface y estrategias
- `domain/analysis.py`: AnalysisOrchestrator que coordina adapters
- Migrar score_lead() y heuristic_analysis()

### Fase 4: Thin routes
- `api/routes.py`: endpoints que solo parsean request, llaman domain, devuelven response
- Sin lógica de negocio en routes

### Fase 5: Frontend extraction
- Extraer inline HTML/JS/CSS a `frontend/index.html`
- Servir con FastAPI StaticFiles

### Fase 6: Tests
- Tests unitarios para scoring strategies
- Tests para analysis orchestrator con mocks

### Fase 7: Runner + docs
- Scripts de arranque actualizados
- ADRs documentando decisiones clave

## Decisiones Técnicas (ADR track)

| ID | Decisión | Alternativas | Motivo |
|----|----------|-------------|--------|
| ADR-001 | Scraper vía Harv3st (Playwright) | Google Places API (costo) | Gratis total |
| ADR-002 | Frontend HTML estático | Jinja2 templates | Ya es SPA con fetch() |
| ADR-003 | Paquete pocket_api/ | src/, harv3st_digital/ | No rompe imports |
| ADR-004 | Token único compartido | Auth por usuario | Equipo pequeño |
| ADR-005 | File storage con interface | DB, S3 | Simplicidad + preparado para migrar |
| ADR-006 | Scoring con estrategias separadas | Función única | Testabilidad |

## Glosario (Ubiquitous Language)

| Término | Significado |
|---------|------------|
| Lead | Negocio encontrado en Google Maps candidato a cliente |
| Scoring | Puntuación 0-100 por categoría de servicio |
| Web Score | Oportunidad de venta de desarrollo web |
| GMB Score | Oportunidad de venta de optimización GMB |
| WhatsApp Score | Oportunidad de venta de WhatsApp con IA |
| ERP Score | Oportunidad de venta de Odoo/ERP |
| Análisis 360 | Web check + Instagram + heurísticas + (opcional) LLM |
| Run | Una ejecución completa de búsqueda + scoring |
| Harv3st | Scraper de Google Maps vía Playwright |
| Código de color | Sistema de priorización visual |
