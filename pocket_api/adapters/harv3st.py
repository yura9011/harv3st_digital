import httpx


class Harv3stClient:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def start_search(self, query: str, near: str | None = None) -> dict:
        payload = {"query": query}
        if near:
            payload["near"] = near
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{self._base_url}/api/search", json=payload)
            r.raise_for_status()
            return r.json()

    async def poll_scored_data(self, max_attempts: int = 120, delay: float = 2.0) -> list[dict]:
        import asyncio
        async with httpx.AsyncClient(timeout=180) as client:
            for _ in range(max_attempts):
                await asyncio.sleep(delay)
                try:
                    r = await client.get(f"{self._base_url}/api/data/scored")
                    data = r.json()
                    leads = self._extract_leads(data)
                    if leads:
                        return leads
                except Exception:
                    pass
        return []

    def _extract_leads(self, data) -> list[dict]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("leads", "data", "results", "businesses", "items"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            if "data" in data and isinstance(data["data"], dict):
                for key in ("leads", "results", "businesses", "items"):
                    v = data["data"].get(key)
                    if isinstance(v, list):
                        return v
        return []
