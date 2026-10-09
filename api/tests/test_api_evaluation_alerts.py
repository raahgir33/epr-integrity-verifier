"""Tests for GET /evaluation (still an explicit empty state — eval_results
doesn't exist until T14, so it never touches app/store/cache.py at all)
and GET /alerts (T13: real now, reads through cache.get_alerts)."""


def test_evaluation_returns_explicit_empty_state(api_client):
    response = api_client.get("/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "T14" in body["message"]
    assert body["meta"] == {"seed": 42, "facts_source": "truth"}


def test_alerts_returns_empty_list_when_none_stored(api_client, monkeypatch):
    from app.store import cache

    monkeypatch.setattr(cache, "get_alerts", lambda seed, fs: [])

    response = api_client.get("/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["alerts"] == []
    assert body["meta"] == {"seed": 42, "facts_source": "truth"}


def test_alerts_returns_stored_alerts(api_client, monkeypatch):
    from app.store import cache

    fake_alert = {
        "alert_id": "ALERT-1",
        "run_id": "RUN-1",
        "processor_id": "PWP-01",
        "created_at": "2026-04-01T10:00:00+00:00",
        "risk_band_before": "Low",
        "risk_band_after": "Medium",
        "new_finding_summary": "handwritten remark",
        "message": "Risk band Low -> Medium",
    }
    monkeypatch.setattr(cache, "get_alerts", lambda seed, fs: [fake_alert])

    response = api_client.get("/alerts")

    assert response.status_code == 200
    body = response.json()
    assert len(body["alerts"]) == 1
    returned = body["alerts"][0]
    assert returned["alert_id"] == fake_alert["alert_id"]
    assert returned["message"] == fake_alert["message"]
