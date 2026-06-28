import httpx


class InstagramEnricher:
    def __init__(self, harv3st_url: str):
        self._url = f"{harv3st_url.rstrip('/')}/api/instagram/enrich"

    async def enrich(self, handle: str) -> dict:
        if not handle:
            return {"success": False, "error": "sin handle"}
        handle = handle.strip().lstrip("@")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(self._url, json={"handle": handle})
                return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)[:100]}
