"""Integration test for app/events/run_processor.py's run_certificate_batch
— the full stage sequence (reading_documents -> checking -> reasoning ->
drafting_memo -> done, and the failure path), against a fake BigQuery
table dict (same FAKE_DB/_fetch_rows pattern as tests/test_cache.py), a
fake GeminiClient, and monkeypatched run_agent_loop_with_retry/memo
functions. No real BigQuery/Gemini/GCS call.
"""

import datetime
import json

import pytest

from app.events import run_processor

SEED = 42
FACTS_SOURCE = "extracted"

_PROCESSOR_ROW = {
    "processor_id": "PWP-01",
    "name": "Sahyadri Green Recyclers Pvt. Ltd.",
    "type": "recycler",
    "capacity_t_per_year": 192.0,
    "permitted_categories": ["I", "II"],
    "consent_no": "CTO/MH/770487",
    "consent_valid_from": datetime.date(2022, 4, 1),
    "consent_valid_to": datetime.date(2028, 3, 31),
    "registration_no": "EPR-REG/MH/216739",
}

_DEMO_BATCH_ROW = {
    "batch_id": "BATCH-PWP-01-001",
    "processor_id": "PWP-01",
    "period_month": "2026-03",
    "quantity_t": 7.82,
    "pushes_over_verifiable": False,
    "extra_document_ids": [],
}


def _run_row(run_id: str, snapshot_before=None) -> dict:
    return {
        "run_id": run_id,
        "batch_id": "BATCH-PWP-01-001",
        "processor_id": "PWP-01",
        "seed": SEED,
        "facts_source": FACTS_SOURCE,
        "status": "queued",
        "created_at": datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
        "updated_at": datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
        "stage_timestamps_json": "{}",
        "error_message": None,
        "snapshot_before_json": json.dumps(snapshot_before or {"risk_band": None, "findings": []}),
        "alert_id": None,
    }


class _FakeGeminiClient:
    def __init__(self):
        self.call_log = []

    def flush_call_log(self):
        return []


class _FakeMemoDoc:
    def model_dump_json(self) -> str:
        return '{"subject": "fake"}'


@pytest.fixture
def fake_env(monkeypatch):
    runs_table = [_run_row("RUN-1")]
    fake_db = {
        "runs": runs_table,
        "demo_batches": [dict(_DEMO_BATCH_ROW)],
        "processors": [dict(_PROCESSOR_ROW)],
        "documents": [],
        "extracted_facts": [],
        "shipments": [],
        "certificates": [
            {
                "certificate_id": "EXISTING",
                "processor_id": "PWP-01",
                "category": "I",
                "quantity_t": 129.41,
                "period_month": "2026-03",
                "generation_date": datetime.date(2026, 3, 31),
            }
        ],
        "outputs": [],
        "energy_monthly": [],
        "site_assessments": [],
        "alerts": [],
    }
    loaded = []
    deleted = []

    def fake_fetch_rows(client, table, columns, seed, processor_id=None, facts_source=None):
        return list(fake_db.get(table, []))

    def fake_load_rows(client, table, rows):
        # Mirrors google.cloud.bigquery.Client.load_table_from_json's own
        # internal json.dumps(item) per row — a real live bug (2026-10-09,
        # docs/PROGRESS.md) let a raw datetime slip through get_run's
        # result and back into a load_rows call, which only fails this
        # way in production; a fake that just records the dicts as-is
        # would never have caught it.
        for row in rows:
            json.dumps(row)
        loaded.append((table, [dict(r) for r in rows]))
        if table == "runs" and rows:
            runs_table[:] = [rows[0]]
        return len(rows)

    def fake_delete(*args, **kwargs):
        deleted.append(args)

    monkeypatch.setattr(run_processor.bq, "get_client", lambda: object())
    monkeypatch.setattr(run_processor.bq, "fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(run_processor.bq, "load_rows", fake_load_rows)
    for name in (
        "delete_by_run_id",
        "delete_by_ids",
        "delete_shipments_by_processor",
        "delete_check_results_by_processor",
        "delete_assessments_by_processor_and_stage",
        "delete_agent_runs_by_processor",
        "delete_memos_by_processor",
    ):
        monkeypatch.setattr(run_processor.bq, name, fake_delete)

    monkeypatch.setattr(run_processor.gcs, "get_client", lambda: object())
    monkeypatch.setattr(run_processor, "GeminiClient", _FakeGeminiClient)

    fake_loop_result = {
        "conclusions": [],
        "hypothesis_findings": [],
        "verdicts": [],
        "objections": [],
        "revisions": [],
        "hypothesis_finding_responses": [],
        "confirmed_findings": [],
        "review_flag_findings": [],
        "withdrawn_findings": [],
        "deductible_findings": [],
        "systemic_findings": [],
        "no_evidence_findings": [],
        "concurs_with_check_findings": [],
        "excluded_shipment_ids": frozenset(),
        "trail": [],
        "tool_cap_reached": False,
        "agent_status": "ok",
    }
    monkeypatch.setattr(
        run_processor,
        "run_agent_loop_with_retry",
        lambda *a, **kw: (
            fake_loop_result,
            [{"attempt": 1, "trail": [], "agent_status": "ok"}],
        ),
    )
    monkeypatch.setattr(
        run_processor.memo,
        "build_memo_context",
        lambda **kwargs: {"doc_type": "verification_statement"},
    )
    monkeypatch.setattr(
        run_processor.memo,
        "generate_verification_statement",
        lambda ctx, llm: (_FakeMemoDoc(), "ok"),
    )
    monkeypatch.setattr(
        run_processor.memo,
        "generate_clarification_memo",
        lambda ctx, llm: (_FakeMemoDoc(), "ok"),
    )

    cache_calls = []
    monkeypatch.setattr(
        run_processor.cache, "invalidate", lambda key=None: cache_calls.append("invalidate")
    )
    monkeypatch.setattr(
        run_processor.cache, "preload", lambda seed, fs: cache_calls.append("preload")
    )

    return {
        "loaded": loaded,
        "deleted": deleted,
        "runs_table": runs_table,
        "cache_calls": cache_calls,
    }


def _run_statuses(loaded) -> list[str]:
    return [rows[0]["status"] for table, rows in loaded if table == "runs"]


def test_run_certificate_batch_happy_path_reaches_done_in_order(fake_env):
    run_processor.run_certificate_batch("RUN-1")

    statuses = _run_statuses(fake_env["loaded"])
    # Each stage writes a start + finish pair with the same status name;
    # "done" is written once, at the very end.
    assert statuses[0] == "reading_documents"
    assert "checking" in statuses
    assert "reasoning" in statuses
    assert "drafting_memo" in statuses
    assert statuses[-1] == "done"
    assert statuses.index("checking") > statuses.index("reading_documents")
    assert statuses.index("reasoning") > statuses.index("checking")
    assert statuses.index("drafting_memo") > statuses.index("reasoning")


def test_run_certificate_batch_invalidates_and_rewarms_the_cache(fake_env):
    run_processor.run_certificate_batch("RUN-1")

    assert fake_env["cache_calls"] == ["invalidate", "preload"]


def test_run_certificate_batch_clears_the_active_run_tracker_on_success(fake_env):
    run_processor.run_certificate_batch("RUN-1")

    assert run_processor.get_active_run_steps("RUN-1") is None


def test_run_certificate_batch_unknown_batch_marks_the_run_failed(fake_env, monkeypatch):
    monkeypatch.setattr(run_processor.bq, "fetch_rows", lambda *a, **kw: [])
    # runs table still needs to resolve for get_run — patch selectively.
    runs_table = fake_env["runs_table"]

    def fake_fetch_rows(client, table, columns, seed, processor_id=None, facts_source=None):
        if table == "runs":
            return list(runs_table)
        return []  # demo_batches empty -> batch not found

    monkeypatch.setattr(run_processor.bq, "fetch_rows", fake_fetch_rows)

    run_processor.run_certificate_batch("RUN-1")

    statuses = _run_statuses(fake_env["loaded"])
    assert statuses[-1] == "failed"
    last_table, last_rows = fake_env["loaded"][-1]
    assert last_rows[0]["error_message"] is not None
    assert "not found" in last_rows[0]["error_message"]


def test_run_certificate_batch_is_a_noop_for_an_already_terminal_run(fake_env):
    fake_env["runs_table"][:] = [{**_run_row("RUN-1"), "status": "done"}]

    run_processor.run_certificate_batch("RUN-1")

    assert fake_env["loaded"] == []  # never even started
