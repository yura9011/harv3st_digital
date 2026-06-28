import httpx, json


class OpenRouterClient:
    def __init__(self, api_key: str, model: str = "mistralai/mistral-7b-instruct"):
        self._api_key = api_key
        self._model = model

    async def analyze(self, context: dict) -> str | None:
        if not self._api_key:
            return None
        prompt = self._build_prompt(context)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                    }
                )
                data = r.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"Error al llamar a OpenRouter: {e}"

    def _build_prompt(self, ctx: dict) -> str:
        return f"""Eres un analista de negocios experto en prospección digital para Forma Digital, una agencia que ofrece: desarrollo web, optimización de Google Business Profile, WhatsApp con IA para atención al cliente, y sistemas Odoo/ERP.

Analiza este negocio y genera un análisis de prospección:

NOMBRE: {ctx.get('name', '?')}
CATEGORÍA: {ctx.get('category', '?')}
DIRECCIÓN: {ctx.get('address', '?')}
TELÉFONO: {ctx.get('phone', '?')}
RATING: {ctx.get('rating', '?')}
CANTIDAD DE RESEÑAS: {ctx.get('reviews_count', '?')}
TIENE WEB: {ctx.get('has_web', '?')}
WEB: {ctx.get('website', '?')}
CMS DETECTADO: {ctx.get('cms', '?')}
WEB VIVA: {ctx.get('web_alive', '?')}
TÍTULO WEB: {ctx.get('web_title', '?')}
DESCRIPCIÓN WEB: {ctx.get('web_description', '?')}
TIENE INSTAGRAM: {ctx.get('has_instagram', '?')}
INSTAGRAM: {ctx.get('instagram_handle', '?')}
INSTAGRAM DATA: {json.dumps(ctx.get('instagram_data', {}), ensure_ascii=False)}
TIENE FACEBOOK: {ctx.get('has_facebook', '?')}
RESEÑAS SAMPLE: {ctx.get('reviews_sample', '?')[:500]}

Genera un análisis estructurado con:
1. FORTALEZAS: qué está haciendo bien el negocio (basado en datos reales, no inventes)
2. DEBILIDADES: qué le falta o puede mejorar (solo datos reales)
3. OPORTUNIDADES: qué servicios de Forma Digital le vendrían bien y por qué
4. ANGULO DE VENTA: cómo encarar la conversación con el dueño
5. RESUMEN: un párrafo corto que describa el negocio

IMPORTANTE: No inventes datos. Basate únicamente en la información provista."""
