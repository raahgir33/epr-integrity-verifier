"""Tests for app/events/run_processor.py's pure logic (no BigQuery/
Gemini/GCS) — the alert decision, finding classification flattening, and
the in-process live-step tracker. run_certificate_batch's full
BigQuery-orchestrated flow is exercised at the API layer instead
(tests/test_api_runs.py), via monkeypatched bq/cache/llm — building a
full fake BigQuery wire client here would duplicate that coverage.
"""

from app.events import run_processor
from app.models.agent import Objection


def _objection(**overrides) -> Objection:
    defaults = {
        "finding_type": "handwritten remark",
        "effect": "raises_concern",
        "cited_shipment_ids": ["PWP-03-DEMO-SHP-001"],
        "evidence_ids": ["PWP-03-DEMO-WEIGHBRIDGE_SLIP-001"],
        "explanation": "the weighbridge slip's handwritten remark says the load was not unloaded",
    }
    return Objection(**{**defaults, **overrides})


def test_classified_findings_tags_each_bucket_with_its_classification():
    loop_result = {
        "deductible_findings": [_objection()],
        "systemic_findings": [],
        "no_evidence_findings": [],
        "concurs_with_check_findings": [],
        "review_flag_findings": [],
    }

    flat = run_processor._classified_findings(loop_result)

    assert len(flat) == 1
    assert flat[0]["classification"] == "deductible"
    assert flat[0]["cited_shipment_ids"] == ["PWP-03-DEMO-SHP-001"]
    assert flat[0]["finding_type"] == "handwritten remark"


def test_classified_findings_covers_every_bucket():
    loop_result = {
        "deductible_findings": [_objection(finding_type="a")],
        "systemic_findings": [_objection(finding_type="b")],
        "no_evidence_findings": [_objection(finding_type="c")],
        "concurs_with_check_findings": [_objection(finding_type="d")],
        "review_flag_findings": [_objection(finding_type="e")],
    }

    flat = run_processor._classified_findings(loop_result)

    assert {f["classification"] for f in flat} == {
        "deductible",
        "systemic",
        "no_own_evidence",
        "concurs_with_check",
        "review_flag",
    }


def test_decide_alert_none_when_risk_band_unchanged_and_no_new_finding():
    snapshot_before = {"risk_band": "Medium", "findings": []}

    alert = run_processor._decide_alert(snapshot_before, "Medium", [])

    assert alert is None


def test_decide_alert_fires_on_risk_band_increase():
    snapshot_before = {"risk_band": "Medium", "findings": []}

    alert = run_processor._decide_alert(snapshot_before, "High", [])

    assert alert is not None
    assert alert["risk_band_before"] == "Medium"
    assert alert["risk_band_after"] == "High"
    assert alert["new_finding_summary"] is None


def test_decide_alert_fires_on_a_genuinely_new_deductible_finding():
    snapshot_before = {"risk_band": "Medium", "findings": []}
    findings_after = [
        {
            "classification": "deductible",
            "cited_shipment_ids": ["PWP-03-DEMO-SHP-001"],
            "explanation": "goods not unloaded",
        }
    ]

    alert = run_processor._decide_alert(snapshot_before, "Medium", findings_after)

    assert alert is not None
    assert alert["new_finding_summary"] == "goods not unloaded"


def test_decide_alert_ignores_a_finding_that_already_existed_before():
    existing_finding = {
        "classification": "deductible",
        "cited_shipment_ids": ["PWP-05-SHP-003"],
        "explanation": "already known",
    }
    snapshot_before = {"risk_band": "High", "findings": [existing_finding]}

    alert = run_processor._decide_alert(snapshot_before, "High", [existing_finding])

    assert alert is None


def test_decide_alert_ignores_concurs_with_check_and_withdrawn_classifications():
    snapshot_before = {"risk_band": "Low", "findings": []}
    findings_after = [
        {
            "classification": "concurs_with_check",
            "cited_shipment_ids": ["PWP-01-DEMO-SHP-001"],
            "explanation": "already caught by C4",
        }
    ]

    alert = run_processor._decide_alert(snapshot_before, "Low", findings_after)

    assert alert is None


def _raw_trail_step(step_index: int, step_type: str, **fields) -> dict:
    """Same shape as app/agents/orchestrator.py's _trail_step — what
    on_step actually receives. Real trail rows always carry every one
    of these keys (orchestrator.py's _trail_step fills every key with
    None by default); a test fixture that omits step_index entirely
    (the pre-fix version of this test did) can't actually exercise
    get_active_run_steps's real transformation, which is exactly how
    the live ResponseValidationError (missing tool_args/output/result/
    result_summary/tokens/dedup_hit — docs/PROGRESS.md, 2026-10-09)
    went unnoticed until a real deployed run hit it."""
    row = {
        "step_index": step_index,
        "step_type": step_type,
        "tool_name": None,
        "tool_args_json": None,
        "input_summary": None,
        "output_json": None,
        "latency_ms": None,
        "input_tokens": None,
        "output_tokens": None,
        "thinking_tokens": None,
    }
    row.update(fields)
    return row


def test_active_run_steps_tracked_and_cleared():
    run_id = "RUN-TEST-1"
    assert run_processor.get_active_run_steps(run_id) is None

    with run_processor._active_runs_lock:
        run_processor._active_runs[run_id] = []

    def on_step(step: dict) -> None:
        with run_processor._active_runs_lock:
            run_processor._active_runs.setdefault(run_id, []).append(step)

    on_step(_raw_trail_step(0, "hypothesis", output_json='{"conclusions": []}'))
    on_step(_raw_trail_step(1, "critic_final", output_json='{"objections": []}'))

    steps = run_processor.get_active_run_steps(run_id)
    assert [s["step_type"] for s in steps] == ["hypothesis", "critic_final"]

    with run_processor._active_runs_lock:
        run_processor._active_runs.pop(run_id, None)

    assert run_processor.get_active_run_steps(run_id) is None


def test_active_run_steps_validate_as_real_reasoning_step_out():
    """The exact regression this guards: get_active_run_steps's output
    must satisfy app/models/api.py's ReasoningStepOut (what GET /runs/
    {run_id} actually returns through) — not just "look like a dict
    with the right step_type". A raw run_agent_loop trail step (what
    on_step really receives — tool_args_json/output_json as strings, no
    tool_args/output/result/result_summary/tokens/dedup_hit keys at all)
    failed this validation live until get_active_run_steps started
    reusing app/store/cache.py's _merge_tool_steps."""
    from app.models.api import ReasoningStepOut

    run_id = "RUN-TEST-2"
    with run_processor._active_runs_lock:
        run_processor._active_runs[run_id] = [
            _raw_trail_step(0, "hypothesis", output_json='{"conclusions": []}'),
            _raw_trail_step(
                1,
                "critic_tool_call",
                tool_name="run_check",
                tool_args_json='{"check_id": "C1"}',
            ),
            # A dangling tool call with no result yet — the normal
            # in-progress state while the Critic's tool loop is still
            # running; must not crash the merge.
        ]

    try:
        steps = run_processor.get_active_run_steps(run_id)
        for step in steps:
            ReasoningStepOut.model_validate(step)  # raises on any missing/invalid field
    finally:
        with run_processor._active_runs_lock:
            run_processor._active_runs.pop(run_id, None)
