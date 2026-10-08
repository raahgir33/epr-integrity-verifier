from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.store import cache

client = TestClient(app)


def test_health_returns_status_model_region():
    # main_module._consistency_status is process-global, set by the app's
    # lifespan — reset it explicitly so this test doesn't depend on
    # whether an earlier test's `with TestClient(app)` already ran (and
    # thus already populated it).
    main_module._consistency_status = None

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"status", "model", "region", "consistency_ok"}
    assert body["status"] == "ok"
    # This client never enters the app's lifespan (no `with TestClient(...)`),
    # so cache.preload/check_consistency never ran — consistency_ok must
    # report that honestly as unknown, not a false "ok".
    assert body["consistency_ok"] is None


def test_health_reports_consistency_ok_after_lifespan(monkeypatch):
    monkeypatch.setattr(cache, "preload", lambda seed, facts_source: None)
    monkeypatch.setattr(
        cache, "check_consistency", lambda seed, facts_source: {"ok": True, "mismatches": []}
    )

    with TestClient(app) as lifespan_client:
        body = lifespan_client.get("/health").json()

    assert body["consistency_ok"] is True


def test_health_reports_consistency_not_ok_on_mismatch(monkeypatch):
    monkeypatch.setattr(cache, "preload", lambda seed, facts_source: None)
    monkeypatch.setattr(
        cache,
        "check_consistency",
        lambda seed, facts_source: {
            "ok": False,
            "mismatches": [
                {
                    "processor_id": "PWP-05",
                    "stored_verifiable_t": 100.0,
                    "recomputed_verifiable_t": 95.0,
                }
            ],
        },
    )

    with TestClient(app) as lifespan_client:
        body = lifespan_client.get("/health").json()

    assert body["consistency_ok"] is False
