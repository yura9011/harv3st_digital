from fastapi import APIRouter

router = APIRouter()

TOOLS = [
    {
        "name": "search_leads",
        "description": "Inicia una búsqueda asincrónica de negocios en Google Maps por rubro y zona. Devuelve un search_id para consultar resultados después.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Rubro o tipo de negocio. Ej: 'cafeterías'"},
                "near": {"type": "string", "description": "Zona o ciudad. Ej: 'Haedo, Buenos Aires'"},
                "radius_km": {"type": "number", "description": "Radio de búsqueda en km. Default: 2"},
            },
            "required": ["query"],
        },
        "returns": "search_id y cantidad de leads encontrados",
    },
    {
        "name": "search_leads_sync",
        "description": "Busca negocios en Google Maps y devuelve los leads completos con scoring en una sola respuesta (bloqueante). Ideal para agentes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Rubro o tipo de negocio. Ej: 'cafeterías'"},
                "near": {"type": "string", "description": "Zona o ciudad. Ej: 'Haedo, Buenos Aires'"},
                "radius_km": {"type": "number", "description": "Radio de búsqueda en km. Default: 2"},
            },
            "required": ["query"],
        },
        "returns": "Objeto con search_id, query, leads (array con scoring incluido)",
    },
    {
        "name": "get_leads",
        "description": "Obtiene los resultados completos de una búsqueda anterior por search_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_id": {"type": "string", "description": "ID de la búsqueda (ej: '20250628120000000000')"},
            },
            "required": ["search_id"],
        },
        "returns": "Objeto completo del run: search_id, query, created_at, leads, enriched",
    },
    {
        "name": "analyze_lead",
        "description": "Ejecuta un análisis 360 de un lead individual: web check + Instagram + (opcional) IA vía OpenRouter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_id": {"type": "string", "description": "ID de la búsqueda"},
                "idx": {"type": "integer", "description": "Índice del lead dentro de la lista (0-based)"},
            },
            "required": ["search_id", "idx"],
        },
        "returns": "Objeto con fortalezas, debilidades, oportunidades, sales_angle y (opcional) llm_analysis",
    },
    {
        "name": "list_runs",
        "description": "Lista las búsquedas anteriores con metadata (fecha, query, cantidad de leads).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad máxima de runs a devolver. Default: 20"},
            },
            "required": [],
        },
        "returns": "Array de objetos con search_id, query, created_at, leads_count, enriched",
    },
    {
        "name": "export_leads",
        "description": "Exporta los resultados de una búsqueda como texto plano formateado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_id": {"type": "string", "description": "ID de la búsqueda"},
            },
            "required": ["search_id"],
        },
        "returns": "Texto plano con datos de cada lead formateados para lectura humana",
    },
]


@router.get("/tools")
def list_tools():
    return {"tools": TOOLS}
