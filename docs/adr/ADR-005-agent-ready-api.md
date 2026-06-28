# ADR-005: Agent-Ready API

**Fecha:** 2026-06-28

## Contexto

Agentes de IA (Claude, Hermes, etc.) necesitan descubrir capacidades
de la API sin documentación externa. Además, el flujo async (search →
poll → get_leads) es engorroso para agentes que prefieren una respuesta
completa en un solo llamado.

## Decisión

Agregamos tres mecanismos:

1. **`GET /tools`** — endpoint sin auth que expone todas las operaciones
   en formato OpenAI function-calling. Cualquier agente puede llamarlo
   primero para descubrir qué puede hacer.

2. **`POST /search/sync`** — versión bloqueante de `/search` que devuelve
   los leads completos en una sola respuesta (ideal para agentes).

3. **`GET /runs`** — listado de búsquedas anteriores con metadata,
   para que agentes puedan recuperar contexto de sesiones previas.

## Consecuencias

- `/tools` no requiere auth para permitir descubrimiento anónimo
- `/search/sync` duplica lógica de `/search` pero la mantendremos
  sincronizada (mismo flow, distinto return)
- `RunRepository.list()` se agregó a la interfaz abstracta; todas las
  implementaciones concretas deben implementarlo
- Se agregó `radius_km` a `SearchRequest` para control de radio de
  búsqueda (Harv3st lo recibe en el payload)
