import urllib.parse

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


async def geocode(location: str) -> tuple[float, float] | None:
    """Resolve a location string to (lat, lon) via OSM Nominatim."""
    params = {"q": location, "format": "json", "limit": "1"}
    headers = {"User-Agent": "FormaDigitalPocket/1.0"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(NOMINATIM_URL, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            pass
    return None
