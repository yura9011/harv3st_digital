# ADR-003: Paquete pocket_api/

**Fecha:** 2026-06-28

## Contexto

El proyecto era un solo archivo `pocket_api.py` de 705 líneas con toda la
lógica mezclada.

## Decisión

Convertimos en paquete Python `pocket_api/` con subpaquetes:
- `api/` — routes thin + auth
- `domain/` — lógica de negocio (deep module)
- `adapters/` — infraestructura con seams
- `frontend/` — HTML estático

## Consecuencias

- `uvicorn pocket_api:app` sigue funcionando (__init__.py re-exporta app)
- Cada capa es testeable independientemente
- Nuevos desarrolladores encuentran rápido dónde va cada cosa
