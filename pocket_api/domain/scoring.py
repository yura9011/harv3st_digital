from abc import ABC, abstractmethod
from urllib.parse import urlparse


def _get(lead: dict, *keys):
    for k in keys:
        v = lead.get(k)
        if v is not None:
            if isinstance(v, str) and v.strip():
                return v.strip()
            if not isinstance(v, str):
                return v
    return None


def _norm_url(u: str | None):
    if not u:
        return None
    u = u.strip()
    if not u:
        return None
    if not u.startswith("http"):
        u = "https://" + u
    try:
        p = urlparse(u)
        netloc = p.netloc.lower()
        if any(skip in netloc for skip in ["search.google.com", "google.com/search"]):
            return None
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return u


def _cms_hint(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    if any(k in host for k in ["wordpress", "wp-content"]):
        return "wordpress"
    if "shopify" in host:
        return "shopify"
    if any(k in host for k in ["wixsite", "wix.com"]):
        return "wix"
    return None


def sample_reviews_text(lead: dict) -> str:
    for key in ("google_reviews", "reviews", "reviews_sample", "reviews_text", "comments"):
        val = lead.get(key)
        if not val:
            continue
        if isinstance(val, list):
            texts = []
            for item in val[:5]:
                if isinstance(item, dict):
                    texts.append(item.get("text") or item.get("review") or item.get("content") or item.get("comment") or "")
                elif isinstance(item, str):
                    texts.append(item)
            txt = " ".join([t for t in texts if t])
            if txt.strip():
                return txt
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


class LeadScorer(ABC):
    name: str
    @abstractmethod
    def score(self, lead: dict) -> float: ...


class WebScore(LeadScorer):
    name = "Web"
    def score(self, lead: dict) -> float:
        website = _get(lead, "website", "url", "link")
        website_norm = _norm_url(website)
        # higher score = more opportunity (no web = want to build one)
        return 100.0 if not bool(website_norm) else 0.0


class GMBScore(LeadScorer):
    name = "GMB"
    def score(self, lead: dict) -> float:
        s = 0.0
        rating = None
        try:
            rating = float(lead.get("rating") or lead.get("averageRating") or 0) or None
        except Exception:
            rating = None
        reviews_count = None
        try:
            reviews_count = int(lead.get("reviews_count") or lead.get("reviewCount") or 0) or None
        except Exception:
            reviews_count = None
        address = _get(lead, "address", "location", "fullAddress")
        phone = _get(lead, "phone", "telephone", "contact_phone", "phones")

        s += 20.0 if rating is not None else 0.0
        s += 20.0 if reviews_count and reviews_count >= 50 else 0.0
        s += 30.0 if bool(address) else 0.0
        s += 30.0 if bool(phone) else 0.0
        return s


class WhatsAppScore(LeadScorer):
    name = "WhatsApp"
    def score(self, lead: dict) -> float:
        s = 0.0
        reviews_text = sample_reviews_text(lead).lower()
        text_context = " ".join([
            str(lead.get("category") or lead.get("categories") or ""),
            str(lead.get("description") or lead.get("businessDescription") or ""),
            reviews_text,
        ])
        if any(k in text_context for k in ["turnos", "reserva", "pedidos", "delivery", "consulta", "horario", "precios"]):
            s += 40.0
        rating = None
        try:
            rating = float(lead.get("rating") or lead.get("averageRating") or 0) or None
        except Exception:
            rating = None
        if rating is not None and rating < 4.0:
            s += 20.0
        website = _get(lead, "website", "url", "link")
        if not bool(_norm_url(website)):
            s += 10.0
        return s


class ERPUrl(LeadScorer):
    name = "ERP"
    def score(self, lead: dict) -> float:
        s = 0.0
        text_context = " ".join([
            str(lead.get("category") or lead.get("categories") or ""),
            str(lead.get("description") or lead.get("businessDescription") or ""),
            sample_reviews_text(lead).lower(),
        ])
        if any(k in text_context for k in ["stock", "depósito", "mayorista", "menú", "carta", "servicios", "pedidos"]):
            s += 40.0
        reviews_count = None
        try:
            reviews_count = int(lead.get("reviews_count") or lead.get("reviewCount") or 0) or None
        except Exception:
            reviews_count = None
        if reviews_count and reviews_count >= 200:
            s += 30.0
        return s


class ScoringEngine:
    def __init__(self, scorers: list[LeadScorer] | None = None):
        self._scorers = scorers or [WebScore(), GMBScore(), WhatsAppScore(), ERPUrl()]

    def score(self, lead: dict) -> dict:
        lead = dict(lead)
        website = _get(lead, "website", "url", "link")
        website_norm = _norm_url(website)
        ig = _get(lead, "instagram", "social_instagram")
        fb = _get(lead, "facebook", "social_facebook")
        has_social = bool(ig or fb)

        rating = None
        try:
            rating = float(lead.get("rating") or lead.get("averageRating") or 0) or None
        except Exception:
            rating = None
        reviews_count = None
        try:
            reviews_count = int(lead.get("reviews_count") or lead.get("reviewCount") or 0) or None
        except Exception:
            reviews_count = None
        address = _get(lead, "address", "location", "fullAddress")
        phone = _get(lead, "phone", "telephone", "contact_phone", "phones")

        scores = {s.name: max(0.0, min(100.0, float(s.score(lead)))) for s in self._scorers}

        lead.update({
            "website_norm": website_norm,
            "has_web": bool(website_norm),
            "has_social": has_social,
            "rating": rating,
            "reviews_count": reviews_count,
            "address": address or lead.get("address"),
            "phone": phone or lead.get("phone"),
            "category": lead.get("category") or lead.get("categories", ""),
            "cms": _cms_hint(website_norm),
            "web_alive": None,
            "web_score": scores.get("Web", 0.0),
            "gmb_score": scores.get("GMB", 0.0),
            "whatsapp_score": scores.get("WhatsApp", 0.0),
            "erp_score": scores.get("ERP", 0.0),
            "reviews_sample": sample_reviews_text(lead),
        })
        return lead
