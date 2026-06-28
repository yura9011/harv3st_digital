# ADR-004: Scoring con estrategias separadas

**Fecha:** 2026-06-28

## Contexto

El scoring calculaba 4 scores (Web, GMB, WhatsApp, ERP) en una sola función
con lógica mezclada.

## Decisión

Creamos una interfaz `LeadScorer` con implementaciones separadas:
`WebScore`, `GMBScore`, `WhatsAppScore`, `ERPUrl`. El `ScoringEngine`
los orquesta.

## Consecuencias

- Cada estrategia se testea por separado
- Se pueden agregar/quitar estrategias sin tocar el engine
- Nuevos scores se implementan como una clase de 10-20 líneas
