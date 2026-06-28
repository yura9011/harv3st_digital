import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pocket_api.domain.geo import haversine, filter_by_distance


def test_haversine_same_point():
    """Distance from a point to itself should be 0."""
    d = haversine(-34.66, -58.73, -34.66, -58.73)
    assert d == 0.0


def test_haversine_known_distance():
    """Buenos Aires (Obelisco) to La Plata (~55 km)."""
    d = haversine(-34.6037, -58.3816, -34.9215, -57.9546)
    assert 50 < d < 65


def test_haversine_merlo_to_libertad():
    """Merlo centro (~-34.66, -58.73) to a point ~1 km away."""
    d = haversine(-34.66, -58.73, -34.67, -58.72)
    assert 0.5 < d < 2.0


def test_filter_keeps_within_radius():
    leads = [
        {"name": "Cerca", "latitude": "-34.66", "longitude": "-58.73"},
        {"name": "Lejos", "latitude": "-34.50", "longitude": "-58.50"},
    ]
    result = filter_by_distance(leads, -34.66, -58.73, 5.0)
    assert len(result) == 1
    assert result[0]["name"] == "Cerca"
    assert "_distance_km" in result[0]
    assert result[0]["_distance_km"] < 1


def test_filter_drops_outside_radius():
    leads = [
        {"name": "Lejos", "latitude": "-34.50", "longitude": "-58.50"},
        {"name": "Muy Lejos", "latitude": "-34.00", "longitude": "-58.00"},
    ]
    result = filter_by_distance(leads, -34.66, -58.73, 5.0)
    assert len(result) == 0


def test_filter_skips_leads_without_coords():
    leads = [
        {"name": "Sin coords"},
        {"name": "Con coords", "latitude": "-34.66", "longitude": "-58.73"},
    ]
    result = filter_by_distance(leads, -34.66, -58.73, 5.0)
    assert len(result) == 1
    assert result[0]["name"] == "Con coords"


def test_filter_all_within_radius():
    leads = [
        {"name": "A", "latitude": "-34.66", "longitude": "-58.73"},
        {"name": "B", "latitude": "-34.67", "longitude": "-58.72"},
        {"name": "C", "latitude": "-34.65", "longitude": "-58.74"},
    ]
    result = filter_by_distance(leads, -34.66, -58.73, 10.0)
    assert len(result) == 3
