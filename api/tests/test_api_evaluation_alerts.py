"""Tests for GET /evaluation (T14: cache.get_evaluation is monkeypatched
directly, same pattern as test_api_stats.py's /stats tests — the route
itself does no BigQuery work, so there's nothing to isolate at this layer)
and GET /alerts (T13: real now, reads through cache.get_alerts)."""

from app.store import cache


def test_evaluation_returns_unavailable_state_when_no_heldout_rows(api_client, monkeypatch):
    monkeypatch.setattr(
        cache,
        "get_evaluation",
        lambda: {
            "available": False,
            "message": "Held-out evaluation metrics are not yet available — see "
            "docs/BUILD_PLAN.md T14.",
            "heldout_dataset_label": None,
            "heldout": [],
            "dev_dataset_label": None,
            "dev": [],
            "misses": [],
        },
    )

    response = api_client.get("/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "T14" in body["message"]
    assert body["heldout"] == []
    assert body["meta"] == {"seed": 42, "facts_source": "truth"}


def test_evaluation_returns_heldout_and_dev_rows_when_available(api_client, monkeypatch):
    fake_evaluation = {
        "available": True,
        "message": None,
        "heldout_dataset_label": "heldout-seed7",
        "heldout": [
            {
                "metric": "issue_recall_F3_truth",
                "numerator": 0,
                "denominator": 1,
                "value": 0.0,
                "computed_at": "2026-10-11T00:00:00+00:00",
            }
        ],
        "dev_dataset_label": "dev-seed42",
        "dev": [
            {
                "metric": "key_field_read_accuracy",
                "numerator": 5521,
                "denominator": 5523,
                "value": 5521 / 5523,
                "computed_at": "2026-10-10T00:00:00+00:00",
            }
        ],
        "misses": ["F3 quantity inflation: detected 0/1 planted instance(s) under truth facts."],
    }
    monkeypatch.setattr(cache, "get_evaluation", lambda: dict(fake_evaluation))

    response = api_client.get("/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["heldout_dataset_label"] == "heldout-seed7"
    assert body["heldout"][0]["metric"] == "issue_recall_F3_truth"
    assert body["dev_dataset_label"] == "dev-seed42"
    assert body["dev"][0]["metric"] == "key_field_read_accuracy"
    assert body["misses"] == fake_evaluation["misses"]


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
