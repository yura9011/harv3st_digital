import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pocket_api.domain.scoring import (
    ScoringEngine, WebScore, GMBScore, WhatsAppScore, ERPUrl
)


def test_web_score_no_website():
    engine = WebScore()
    assert engine.score({"name": "Test", "website": None}) == 100.0
    assert engine.score({"name": "Test"}) == 100.0


def test_web_score_has_website():
    engine = WebScore()
    assert engine.score({"name": "Test", "website": "https://example.com"}) == 0.0


def test_web_score_empty_string():
    engine = WebScore()
    assert engine.score({"name": "Test", "website": ""}) == 100.0


def test_gmb_score_no_data():
    engine = GMBScore()
    s = engine.score({"name": "Test"})
    assert s == 0.0


def test_gmb_score_with_rating():
    engine = GMBScore()
    s = engine.score({"name": "Test", "rating": 4.5})
    assert s >= 20.0


def test_gmb_score_with_all_data():
    engine = GMBScore()
    s = engine.score({
        "name": "Test",
        "rating": 4.5,
        "reviews_count": 100,
        "address": "Calle 123",
        "phone": "123456789",
    })
    assert s == 100.0


def test_whatsapp_score_low_rating_no_web():
    engine = WhatsAppScore()
    s = engine.score({
        "name": "Test",
        "rating": 3.0,
        "website": None,
        "category": "restaurant",
    })
    assert s > 0.0


def test_whatsapp_score_high_rating_with_web():
    engine = WhatsAppScore()
    s = engine.score({
        "name": "Test",
        "rating": 4.8,
        "website": "https://example.com",
    })
    assert s == 0.0


def test_erp_score_stock_keywords():
    engine = ERPUrl()
    s = engine.score({
        "name": "Test",
        "category": "ferretería con depósito y stock mayorista",
    })
    assert s >= 40.0


def test_erp_score_high_reviews():
    engine = ERPUrl()
    s = engine.score({
        "name": "Test",
        "reviews_count": 300,
    })
    assert s >= 30.0


def test_scoring_engine_full_pipeline():
    engine = ScoringEngine()
    result = engine.score({
        "name": "Cafetería Test",
        "website": "https://cafetest.com",
        "rating": 4.2,
        "reviews_count": 80,
        "address": "Av. Siempre Viva 123",
        "phone": "1144445555",
        "category": "cafetería",
        "instagram": "@cafetest",
    })
    assert result["web_score"] == 0.0
    assert result["gmb_score"] > 0.0
    assert result["has_web"] is True
    assert result["has_social"] is True
    assert result["rating"] == 4.2
    assert result["website_norm"] == "https://cafetest.com"


def test_scoring_engine_no_lead():
    engine = ScoringEngine()
    result = engine.score({})
    assert "web_score" in result
    assert "gmb_score" in result
    assert "whatsapp_score" in result
    assert "erp_score" in result
    assert result["has_web"] is False
