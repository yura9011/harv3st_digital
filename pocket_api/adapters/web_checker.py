import httpx, re
from urllib.parse import urlparse


class WebChecker:
    def __init__(self, timeout: int = 10):
        self._timeout = timeout

    async def check(self, url: str) -> dict:
        if not url:
            return {"alive": False, "error": "sin url"}
        result = {"url": url, "alive": False, "status": None, "title": None, "description": None, "cms": None, "error": None}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, verify=False) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                result["status"] = r.status_code
                result["alive"] = r.status_code < 500
                html = r.text
                m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
                if m:
                    result["title"] = m.group(1).strip()[:200]
                m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.I)
                if m:
                    result["description"] = m.group(1).strip()[:300]
                cms = self._cms_hint(url)
                if not cms:
                    if "wp-content" in html or "wordpress" in html:
                        cms = "wordpress"
                    elif "shopify" in html:
                        cms = "shopify"
                    elif "wix" in html:
                        cms = "wix"
                result["cms"] = cms
        except httpx.TimeoutException:
            result["error"] = "timeout"
        except Exception as e:
            result["error"] = str(e)[:100]
        return result

    def _cms_hint(self, url: str | None) -> str | None:
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
