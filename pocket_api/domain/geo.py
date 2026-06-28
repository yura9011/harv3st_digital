import math
from typing import Any


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two lat/lon points (Haversine formula)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def filter_by_distance(
    leads: list[dict],
    target_lat: float,
    target_lon: float,
    radius_km: float,
) -> list[dict]:
    """Return only leads whose lat/lon is within radius_km of target."""
    filtered: list[dict] = []
    for lead in leads:
        lat = lead.get("latitude")
        lon = lead.get("longitude")
        if lat is None or lon is None:
            continue
        try:
            d = haversine(target_lat, target_lon, float(lat), float(lon))
            if d <= radius_km:
                lead["_distance_km"] = round(d, 2)
                filtered.append(lead)
        except (ValueError, TypeError):
            continue
    return filtered
