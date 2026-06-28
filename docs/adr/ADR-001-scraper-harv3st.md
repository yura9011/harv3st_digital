# ADR-001: Scraper via Harv3st (Playwright)

**Fecha:** 2026-06-28

## Contexto

Necesitamos obtener datos de negocios en Google Maps para prospección.
Opciones: Harv3st (scraper via Playwright), Google Places API (costo),
SerpAPI (costo).

## Decisión

Usamos Harv3st — un scraper via Playwright que parsea HTML de Google Maps.
Es gratis, funciona, y ya estaba implementado.

## Consecuencias

- Google Maps puede cambiar su HTML y romper el scraper (mantenimiento)
- No tenemos límites de API, solo los rate limits de Playwright
- Puede ser más lento que una API oficial
- Para producción futura se puede migrar a Places API sin cambiar la
  interfaz `Harv3stClient`
