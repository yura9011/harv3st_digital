class AnalysisOrchestrator:
    def __init__(self, web_checker, instagram_enricher, openrouter_client=None):
        self._web_checker = web_checker
        self._instagram = instagram_enricher
        self._openrouter = openrouter_client

    async def analyze(self, lead: dict) -> dict:
        web_info = None
        website = lead.get("website_norm") or lead.get("website")
        if website:
            web_info = await self._web_checker.check(website)
            lead["web_alive"] = web_info.get("alive")
            lead["web_title"] = web_info.get("title")
            if web_info.get("cms"):
                lead["cms"] = web_info.get("cms")

        ig_data = None
        ig_handle = self._get_ig_handle(lead)
        if ig_handle:
            ig_data = await self._instagram.enrich(ig_handle)
            if ig_data.get("success"):
                lead["instagram_data"] = ig_data.get("data")

        result = self._heuristic_analysis(lead, web_info, ig_data)

        if self._openrouter:
            context = self._build_llm_context(lead, web_info, ig_handle, ig_data)
            llm_result = await self._openrouter.analyze(context)
            if llm_result and not llm_result.startswith("Error"):
                result["llm_analysis"] = llm_result
                result["analysis_source"] = "llm"

        return result

    def _get_ig_handle(self, lead: dict) -> str | None:
        for key in ("instagram", "social_instagram"):
            v = lead.get(key)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        return None

    def _get(self, lead: dict, *keys):
        for k in keys:
            v = lead.get(k)
            if v is not None:
                if isinstance(v, str) and v.strip():
                    return v.strip()
                if not isinstance(v, str):
                    return v
        return None

    def _build_llm_context(self, lead: dict, web_info, ig_handle, ig_data) -> dict:
        return {
            "name": lead.get("name"),
            "category": lead.get("category"),
            "address": lead.get("address"),
            "phone": lead.get("phone"),
            "rating": lead.get("rating"),
            "reviews_count": lead.get("reviews_count"),
            "has_web": lead.get("has_web"),
            "website": lead.get("website_norm") or lead.get("website"),
            "cms": lead.get("cms"),
            "web_alive": lead.get("web_alive"),
            "web_title": lead.get("web_title"),
            "web_description": web_info.get("description") if web_info else None,
            "has_instagram": bool(ig_handle),
            "instagram_handle": ig_handle,
            "instagram_data": ig_data.get("data") if ig_data and ig_data.get("success") else {},
            "has_facebook": bool(self._get(lead, "facebook", "social_facebook")),
            "reviews_sample": lead.get("reviews_sample", ""),
        }

    def _heuristic_analysis(self, lead: dict, web_info: dict | None, ig_data: dict | None) -> dict:
        has_web = lead.get("has_web", False)
        has_social = lead.get("has_social", False)
        rating = lead.get("rating")
        reviews = lead.get("reviews_count")
        phone = lead.get("phone") or lead.get("telephone")
        category = str(lead.get("category") or lead.get("categories", ""))
        web_alive = web_info.get("alive") if web_info else None
        web_title = web_info.get("title") if web_info else None
        web_cms = lead.get("cms")
        if web_info:
            web_cms = web_cms or web_info.get("cms")
        ig_active = ig_data.get("success") if ig_data else False
        ig_info = ig_data.get("data", {}) if ig_data and ig_data.get("success") else {}

        strengths = []
        weaknesses = []
        opportunities = []
        sales_angle_parts = []

        if rating and rating >= 4.0:
            strengths.append(f"Buena reputación ({rating}/5 en Google)")
        elif rating and rating < 3.5:
            weaknesses.append(f"Rating bajo ({rating}/5) — pueden estar perdiendo clientes")

        if reviews and reviews >= 50:
            strengths.append(f"Alto volumen de reseñas ({reviews}) — el negocio tiene tráfico constante")
        elif reviews and reviews < 10:
            weaknesses.append("Muy pocas reseñas — poca presencia digital")

        if has_web:
            if web_alive is True:
                strengths.append("Tiene sitio web funcionando")
                if web_title:
                    strengths.append("Web activa con título descriptivo")
                if web_cms:
                    strengths.append(f"Usa {web_cms} — fácil de mantener/mejorar")
            elif web_alive is False:
                weaknesses.append("Sitio web caído o no responde")
            else:
                weaknesses.append("No tiene sitio web — oportunidad para desarrollo web")
        else:
            weaknesses.append("No tiene sitio web — oportunidad para desarrollo web")

        if has_social:
            if ig_active and ig_info.get("followers", 0) > 0:
                strengths.append(f"Instagram activo con {ig_info.get('followers', 0)} seguidores")
                if ig_info.get("posts", 0) > 0:
                    strengths.append(f"Publica contenido en Instagram ({ig_info.get('posts', 0)} posts)")
        else:
            weaknesses.append("Sin presencia en redes sociales")

        food_keywords = ["restaurant", "café", "cafetería", "bar", "comida", "delivery", "pizzería", "heladería", "panadería"]
        retail_keywords = ["tienda", "local", "ferretería", "librería", "indumentaria", "comercio"]

        cat_lower = category.lower()
        if any(k in cat_lower for k in food_keywords):
            opportunities.append("WhatsApp con IA para gestión de pedidos/delivery")
            sales_angle_parts.append("tiene alta rotación de clientes y necesita agilizar la atención")
        if any(k in cat_lower for k in retail_keywords):
            opportunities.append("Odoo/ERP para control de stock y facturación")
            sales_angle_parts.append("maneja inventario y podría optimizar sus ventas con un sistema")
        if not has_web:
            opportunities.append("Sitio web profesional con presencia digital completa")
            sales_angle_parts.append("no tiene web y está perdiendo clientes que buscan online")

        if phone and not has_web:
            opportunities.append("Landing page + WhatsApp automatizado")
            sales_angle_parts.append("tiene consultas por teléfono y podría automatizarlas")

        if rating and rating < 4.0 and reviews and reviews > 10:
            opportunities.append("Google Business Profile optimizado para mejorar reputación")
            sales_angle_parts.append("tiene reseñas regulares pero su rating es mejorable")

        if not sales_angle_parts:
            sales_angle_parts.append("es candidato a una revisión digital completa")

        reviews_sample = lead.get("reviews_sample", "") or ""
        if "mal" in reviews_sample.lower() or "lento" in reviews_sample.lower() or "queja" in reviews_sample.lower():
            weaknesses.append("Quejas recurrentes en reseñas")

        return {
            "name": lead.get("name", "?"),
            "strengths": [s for s in strengths if s],
            "weaknesses": [w for w in weaknesses if w],
            "opportunities": opportunities,
            "sales_angle": f"Este negocio {', '.join(sales_angle_parts)}. " if sales_angle_parts else "Contactar para ofrecer diagnóstico digital gratuito.",
            "recommended_services": opportunities,
            "web_check": {
                "alive": web_alive,
                "title": web_title,
                "cms": web_cms,
            } if web_info else None,
            "instagram": {
                "found": ig_active,
                "followers": ig_info.get("followers", 0) if ig_active else None,
                "posts": ig_info.get("posts", 0) if ig_active else None,
            } if ig_active else None,
            "analysis_source": "heuristic",
        }
