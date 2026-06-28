# ADR-002: Frontend HTML estático

**Fecha:** 2026-06-28

## Contexto

El frontend actual es una SPA con fetch() que llama a los endpoints de la
API. El HTML estaba embebido como string en pocket_api.py.

## Decisión

Movemos el frontend a `pocket_api/frontend/index.html` como archivo estático.
FastAPI lo sirve via `Path.read_text()` en la ruta `/`.

## Consecuencias

- Editor con syntax highlighting, ESLint, Prettier
- Separación clara frontend/backend
- Fácil migrar a un SPA real (React/Vue) en el futuro
- No necesita Jinja2 ni template engine
