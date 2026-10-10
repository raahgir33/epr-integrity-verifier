"""Tests for GET /stats (T13.6) — a single cached read, never a live
BigQuery query (cache.get_stats is monkeypatched directly, same pattern
as test_api_evaluation_alerts.py's /alerts tests)."""

from app.store import cache

FAKE_STATS = {
    "processors_count": 10,
    "documents_read": 714,
    "fields_read": 5523,
    "certified_t_total": 51234.56,
    "unverifiable_t_total": 9876.54,
    "as_of": "2026-03",
    "fy_label": "FY 2025-26 to date",
    "field_read_accuracy_pct": "99.96%",
    "field_read_accuracy_value": 99.96,
    "field_read_correct": 5521,
    "field_read_total": 5523,
    "field_read_dataset_label": "dev-seed42",
}


def test_stats_returns_cached_figures(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_stats", lambda seed, fs: dict(FAKE_STATS))

    response = api_client.get("/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"seed": 42, "facts_source": "truth"}
    for key, value in FAKE_STATS.items():
        assert body[key] == value


def test_stats_field_read_accuracy_fields_are_none_without_an_eval_metrics_row(
    api_client, monkeypatch
):
    no_accuracy = dict(FAKE_STATS)
    for key in (
        "field_read_accuracy_pct",
        "field_read_accuracy_value",
        "field_read_correct",
        "field_read_total",
        "field_read_dataset_label",
    ):
        no_accuracy[key] = None
    monkeypatch.setattr(cache, "get_stats", lambda seed, fs: no_accuracy)

    response = api_client.get("/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["field_read_accuracy_pct"] is None
    assert body["field_read_accuracy_value"] is None
    assert body["field_read_correct"] is None
    assert body["field_read_total"] is None
    assert body["field_read_dataset_label"] is None
