"""Tests for GET /portfolio/{brand_id}."""

from app.store import cache


def test_portfolio_happy_path_apportions_by_verifiable_ratio(api_client, monkeypatch):
    monkeypatch.setattr(
        cache, "get_brand", lambda seed, bid: {"brand_id": bid, "name": "Example Brand"}
    )
    monkeypatch.setattr(
        cache,
        "get_certificates_for_brand",
        lambda seed, bid: [
            {
                "certificate_id": "CERT-01-0001",
                "processor_id": "PWP-01",
                "category": "I",
                "quantity_t": 100.0,
                "period_month": "2026-01",
            },
            {
                "certificate_id": "CERT-05-0001",
                "processor_id": "PWP-05",
                "category": "I",
                "quantity_t": 200.0,
                "period_month": "2026-01",
            },
        ],
    )

    def fake_assessments(seed, fs, pid):
        if pid == "PWP-01":
            return {
                "checks_only": {"certified_t": 100.0, "verifiable_t": 100.0, "risk_band": "Low"},
                "full": None,
                "agent_status": None,
            }
        return {
            "checks_only": {"certified_t": 200.0, "verifiable_t": 150.0, "risk_band": "Medium"},
            "full": {"certified_t": 200.0, "verifiable_t": 150.0, "risk_band": "Medium"},
            "agent_status": "ok",
        }

    monkeypatch.setattr(cache, "get_processor_assessments", fake_assessments)

    response = api_client.get("/portfolio/BR-01")

    assert response.status_code == 200
    body = response.json()
    assert body["brand_name"] == "Example Brand"
    assert body["total_certified_t"] == 300.0
    # PWP-01: 100 * (100/100) = 100; PWP-05: 200 * (150/200) = 150 -> 250
    assert body["total_verifiable_t"] == 250.0
    risk_bands = {c["processor_id"]: c["processor_risk_band"] for c in body["certificates"]}
    assert risk_bands == {"PWP-01": "Low", "PWP-05": "Medium"}


def test_portfolio_404_unknown_brand(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_brand", lambda seed, bid: None)

    response = api_client.get("/portfolio/BR-99")

    assert response.status_code == 404
