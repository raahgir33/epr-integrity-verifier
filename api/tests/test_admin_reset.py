"""Tests for POST /admin/reset-demo (T13.8) — against fakes, no real
BigQuery. Covers the PUSH_TOKEN gate and that a successful reset
invalidates and re-warms the read cache, and that calling it twice is
idempotent (same calls both times, no error)."""

from app.admin import reset_demo as admin_reset_demo
from app.events import pubsub
from app.store import cache


def test_reset_demo_rejects_bad_token(api_client):
    response = api_client.post("/admin/reset-demo", params={"token": "wrong"})

    assert response.status_code == 401
    assert response.json()["error"] == "invalid push token"


def test_reset_demo_rejects_missing_token(api_client):
    response = api_client.post("/admin/reset-demo")

    assert response.status_code == 401


def test_reset_demo_happy_path_invalidates_and_rewarms_cache(api_client, monkeypatch):
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)
    monkeypatch.setattr(admin_reset_demo, "run_reset_live", lambda seed: ["PWP-01", "PWP-05"])
    calls = []
    monkeypatch.setattr(cache, "invalidate", lambda key=None: calls.append(("invalidate", key)))
    monkeypatch.setattr(
        cache,
        "preload",
        lambda seed, facts_source: calls.append(("preload", seed, facts_source)),
    )

    response = api_client.post("/admin/reset-demo", params={"token": "x"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["processors_restored"] == ["PWP-01", "PWP-05"]
    assert calls[0][0] == "invalidate"
    assert calls[1][0] == "preload"


def test_reset_demo_is_idempotent_called_twice(api_client, monkeypatch):
    """run_reset_live itself is delete-then-load throughout (app.admin.
    reset_demo.run_reset) — calling the endpoint twice must succeed both
    times with no error and no accumulating state."""
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)
    monkeypatch.setattr(admin_reset_demo, "run_reset_live", lambda seed: ["PWP-01"])
    monkeypatch.setattr(cache, "invalidate", lambda key=None: None)
    monkeypatch.setattr(cache, "preload", lambda seed, facts_source: None)

    response1 = api_client.post("/admin/reset-demo", params={"token": "x"})
    response2 = api_client.post("/admin/reset-demo", params={"token": "x"})

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json() == response2.json()


def test_run_reset_live_reads_demo_batches_from_bigquery_not_disk(monkeypatch):
    """T13.8's key design point: the deployed container has no data/
    directory, so run_reset_live must source demo_batches from the cache
    (BigQuery), not a local JSON file."""
    calls = []
    monkeypatch.setattr(admin_reset_demo.bq, "get_client", lambda: object())
    monkeypatch.setattr(
        admin_reset_demo.cache,
        "get_demo_batches",
        lambda seed: calls.append(seed) or [],
    )
    monkeypatch.setattr(
        admin_reset_demo,
        "run_reset",
        lambda bq_client, seed, demo_batches, snapshots: list(snapshots.keys()),
    )

    restored = admin_reset_demo.run_reset_live(42)

    assert calls == [42]
    # the bundled snapshot files copied into api/app/admin/data/ at build
    # time — all three ship, since they're tiny and under app/.
    assert set(restored) == {"PWP-01", "PWP-03", "PWP-05"}
