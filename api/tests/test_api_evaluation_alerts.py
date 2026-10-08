"""Tests for GET /evaluation and GET /alerts — both are explicit empty
states (eval_results/alerts tables don't exist until T14/T13), so neither
touches app/store/cache.py at all."""


def test_evaluation_returns_explicit_empty_state(api_client):
    response = api_client.get("/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "T14" in body["message"]
    assert body["meta"] == {"seed": 42, "facts_source": "truth"}


def test_alerts_returns_empty_list(api_client):
    response = api_client.get("/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["alerts"] == []
    assert body["meta"] == {"seed": 42, "facts_source": "truth"}
