import re
import urllib.parse

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

_LATLNG_RE = re.compile(r"^(-?\d+\.\d+),(-?\d+\.\d+)$")


async def geocode(location: str) -> tuple[float, float] | None:
    """Resolve a location string to (lat, lon).

    If location is already 'lat,lng' format, parse directly without IO.
    Otherwise query OSM Nominatim.
    """
    m = _LATLNG_RE.match(location.strip())
    if m:
        return float(m.group(1)), float(m.group(2))

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
