"""Tests for T13's live event path routes: POST /demo/certificate-batch,
GET /runs/{run_id}, POST /events/certificate-batch. All against fakes —
no real BigQuery/Pub/Sub/Gemini. Covers: unknown-batch 404, the abuse
gates (one-run-at-a-time, cooldown, daily cap), push-handler idempotency
(a duplicate message for an already-terminal run never calls
run_certificate_batch again), and the bad-token 401.
"""

import datetime

import app.checks.params as check_params
from app import main as main_module
from app.events import pubsub
from app.events import run_processor as live_run_processor
from app.store import bq, cache

_NOW = datetime.datetime(2026, 4, 1, 12, 0, tzinfo=datetime.UTC)

_DEMO_BATCH = {
    "batch_id": "BATCH-PWP-01-001",
    "processor_id": "PWP-01",
    "period_month": "2026-03",
    "quantity_t": 7.82,
    "pushes_over_verifiable": False,
}


class _FrozenDatetime(datetime.datetime):
    """app/main.py's abuse gates compare against datetime.now(UTC) — fixed
    here so "today"/"elapsed since" are deterministic in tests, rather
    than drifting with whenever the test suite actually runs."""

    @classmethod
    def now(cls, tz=None):
        return _NOW


def _patch_common(monkeypatch, runs=()):
    monkeypatch.setattr(main_module, "datetime", _FrozenDatetime)
    monkeypatch.setattr(cache, "get_demo_batch", lambda seed, batch_id: dict(_DEMO_BATCH))
    monkeypatch.setattr(cache, "get_processor_assessments", lambda seed, fs, pid: None)
    monkeypatch.setattr(cache, "get_findings", lambda seed, fs, pid: [])
    monkeypatch.setattr(bq, "get_client", lambda: object())
    monkeypatch.setattr(bq, "fetch_rows", lambda client, table, columns, seed: list(runs))
    recorded_loads = []
    monkeypatch.setattr(
        bq, "load_rows", lambda client, table, rows: recorded_loads.append((table, rows))
    )
    published = []
    monkeypatch.setattr(
        pubsub, "publish_certificate_batch", lambda run_id, batch_id: published.append(run_id)
    )
    return recorded_loads, published


def _run_row(run_id: str, status: str, created_at: datetime.datetime, **overrides) -> dict:
    return {
        "run_id": run_id,
        "batch_id": "BATCH-PWP-01-001",
        "processor_id": "PWP-01",
        "seed": 42,
        "facts_source": "truth",
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "stage_timestamps_json": "{}",
        "error_message": None,
        "snapshot_before_json": "{}",
        "alert_id": None,
        **overrides,
    }


# ---------- POST /demo/certificate-batch ----------


def test_post_demo_batch_unknown_batch_id_404(api_client, monkeypatch):
    _patch_common(monkeypatch, runs=[])
    monkeypatch.setattr(cache, "get_demo_batch", lambda seed, batch_id: None)

    response = api_client.post("/demo/certificate-batch", json={"batch_id": "NOPE"})

    assert response.status_code == 404


def test_post_demo_batch_happy_path_creates_run_and_publishes(api_client, monkeypatch):
    recorded_loads, published = _patch_common(monkeypatch, runs=[])

    response = api_client.post("/demo/certificate-batch", json={"batch_id": "BATCH-PWP-01-001"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    run_id = body["run_id"]
    assert published == [run_id]
    assert recorded_loads
    table, rows = recorded_loads[-1]
    assert table == "runs"
    assert rows[0]["run_id"] == run_id
    assert rows[0]["status"] == "queued"


def test_post_demo_batch_blocked_by_an_active_run(api_client, monkeypatch):
    active_run = _run_row("RUN-ACTIVE", "reasoning", _NOW)
    _patch_common(monkeypatch, runs=[active_run])

    response = api_client.post("/demo/certificate-batch", json={"batch_id": "BATCH-PWP-01-001"})

    assert response.status_code == 429
    assert "already running" in response.json()["error"]


def test_post_demo_batch_allows_through_a_stale_non_terminal_run(api_client, monkeypatch):
    stale_created = _NOW - datetime.timedelta(seconds=check_params.ACTIVE_RUN_STALE_AFTER_S + 60)
    stale_run = _run_row("RUN-STALE", "reasoning", stale_created)
    _, published = _patch_common(monkeypatch, runs=[stale_run])

    response = api_client.post("/demo/certificate-batch", json={"batch_id": "BATCH-PWP-01-001"})

    assert response.status_code == 202
    assert len(published) == 1


def test_post_demo_batch_cooldown_blocks_a_quick_second_click(api_client, monkeypatch):
    recent_done = _run_row(
        "RUN-RECENT",
        "done",
        _NOW - datetime.timedelta(seconds=check_params.DEMO_COOLDOWN_SECONDS - 5),
    )
    _patch_common(monkeypatch, runs=[recent_done])

    response = api_client.post("/demo/certificate-batch", json={"batch_id": "BATCH-PWP-01-001"})

    assert response.status_code == 429
    assert "cooldown" in response.json()["error"]


def test_post_demo_batch_daily_cap_reached(api_client, monkeypatch):
    todays_runs = [
        _run_row(f"RUN-{i}", "done", _NOW - datetime.timedelta(hours=1, minutes=i))
        for i in range(check_params.DEMO_DAILY_RUN_CAP)
    ]
    _patch_common(monkeypatch, runs=todays_runs)

    response = api_client.post("/demo/certificate-batch", json={"batch_id": "BATCH-PWP-01-001"})

    assert response.status_code == 429
    assert "daily demo limit" in response.json()["error"]


# ---------- GET /runs/{run_id} ----------


def test_get_run_not_found_404(api_client, monkeypatch):
    monkeypatch.setattr(bq, "get_client", lambda: object())
    monkeypatch.setattr(bq, "fetch_rows", lambda client, table, columns, seed: [])
    monkeypatch.setattr(live_run_processor, "get_active_run_steps", lambda run_id: None)

    response = api_client.get("/runs/UNKNOWN")

    assert response.status_code == 404


def test_get_run_returns_live_steps_while_in_progress(api_client, monkeypatch):
    run_row = _run_row("RUN-1", "reasoning", _NOW)
    monkeypatch.setattr(bq, "get_client", lambda: object())
    monkeypatch.setattr(bq, "fetch_rows", lambda client, table, columns, seed: [run_row])
    live_steps = [
        {
            "step_index": 0,
            "step_type": "hypothesis",
            "tool_name": None,
            "tool_args": None,
            "output": {"conclusions": []},
            "result": None,
            "result_summary": None,
            "latency_ms": None,
            "tokens": None,
            "dedup_hit": False,
        }
    ]
    monkeypatch.setattr(live_run_processor, "get_active_run_steps", lambda run_id: live_steps)

    response = api_client.get("/runs/RUN-1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reasoning"
    assert len(body["steps"]) == 1
    assert body["steps"][0]["step_type"] == "hypothesis"


def test_get_run_done_reads_reasoning_steps_from_cache_when_not_active_here(
    api_client, monkeypatch
):
    alert_row = {
        "alert_id": "ALERT-1",
        "run_id": "RUN-1",
        "processor_id": "PWP-01",
        "created_at": _NOW,
        "risk_band_before": "Low",
        "risk_band_after": "Medium",
        "new_finding_summary": "goods not unloaded",
        "message": "Risk band Low -> Medium",
    }
    run_row = _run_row("RUN-1", "done", _NOW, alert_id="ALERT-1")

    def fake_fetch_rows(client, table, columns, seed):
        return [alert_row] if table == "alerts" else [run_row]

    monkeypatch.setattr(bq, "get_client", lambda: object())
    monkeypatch.setattr(bq, "fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(live_run_processor, "get_active_run_steps", lambda run_id: None)
    monkeypatch.setattr(cache, "get_reasoning_steps", lambda seed, fs, pid: [])

    response = api_client.get("/runs/RUN-1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["alert"]["alert_id"] == "ALERT-1"
    assert body["alert"]["new_finding_summary"] == "goods not unloaded"


# ---------- POST /events/certificate-batch ----------


def test_push_handler_rejects_bad_token(api_client):
    response = api_client.post(
        "/events/certificate-batch",
        params={"token": "wrong"},
        json={"message": {"data": "", "messageId": "1"}},
    )

    assert response.status_code == 401


def test_push_handler_ignores_an_unknown_run_id(api_client, monkeypatch):
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)
    monkeypatch.setattr(live_run_processor, "get_run", lambda client, run_id: None)
    monkeypatch.setattr(bq, "get_client", lambda: object())
    calls = []
    monkeypatch.setattr(
        live_run_processor, "run_certificate_batch", lambda run_id: calls.append(run_id)
    )

    body = {"message": {"data": _b64({"run_id": "RUN-UNKNOWN", "batch_id": "B"})}}
    response = api_client.post("/events/certificate-batch", params={"token": "x"}, json=body)

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert calls == []


def test_push_handler_is_idempotent_on_an_already_terminal_run(api_client, monkeypatch):
    run_row = _run_row("RUN-1", "done", _NOW)
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)
    monkeypatch.setattr(live_run_processor, "get_run", lambda client, run_id: run_row)
    monkeypatch.setattr(bq, "get_client", lambda: object())
    calls = []
    monkeypatch.setattr(
        live_run_processor, "run_certificate_batch", lambda run_id: calls.append(run_id)
    )

    body = {"message": {"data": _b64({"run_id": "RUN-1", "batch_id": "B"})}}
    # Simulate Pub/Sub re-delivering the same message twice.
    response1 = api_client.post("/events/certificate-batch", params={"token": "x"}, json=body)
    response2 = api_client.post("/events/certificate-batch", params={"token": "x"}, json=body)

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["status"] == "already processed"
    assert response2.json()["status"] == "already processed"
    assert calls == []  # never re-processed — no duplicate alert can be produced


def test_push_handler_processes_a_fresh_queued_run_once(api_client, monkeypatch):
    run_row = _run_row("RUN-1", "queued", _NOW)
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)
    monkeypatch.setattr(live_run_processor, "get_run", lambda client, run_id: run_row)
    monkeypatch.setattr(bq, "get_client", lambda: object())
    calls = []
    monkeypatch.setattr(
        live_run_processor, "run_certificate_batch", lambda run_id: calls.append(run_id)
    )

    body = {"message": {"data": _b64({"run_id": "RUN-1", "batch_id": "B"})}}
    response = api_client.post("/events/certificate-batch", params={"token": "x"}, json=body)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert calls == ["RUN-1"]


def test_push_handler_rejects_missing_token(api_client):
    """T13.8: verify_push_token must fail closed when no token is sent at
    all, not just a wrong one — exercises the real function, not a mock."""
    response = api_client.post(
        "/events/certificate-batch",
        json={"message": {"data": "", "messageId": "1"}},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid push token"


def test_push_handler_malformed_envelope_returns_400_not_500(api_client, monkeypatch):
    """T13.8: pubsub.decode_push_envelope's KeyError/ValueError/
    JSONDecodeError on a malformed envelope must surface as a 400, not an
    unhandled 500 (the module's own docstring already promised this; the
    route didn't actually catch it before this task)."""
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)

    response = api_client.post(
        "/events/certificate-batch",
        params={"token": "x"},
        json={"message": {"not_data": "oops"}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "malformed push envelope"


def _b64(payload: dict) -> str:
    import base64
    import json

    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
