"""Tests for app/agents/orchestrator.py against a fake LLMClient — no
network call. Covers every code-level rule in docs/ARCHITECTURE.md §4:
no-evidence findings discarded, invented IDs filtered, a failed hard check
can't be overruled, the tool-cap and timeout/error paths never raise.
"""

import time

from app.agents.orchestrator import run_agent_loop
from app.models.agent import (
    ConclusionsResponse,
    HypothesisConclusion,
    HypothesisRevision,
    Objection,
    ObjectionsResponse,
    RevisionsResponse,
)


class _FakeLLMClient:
    def __init__(self, structured_responses, tool_loop_side_effect=None, raise_on_call=None):
        self._structured_responses = list(structured_responses)
        self._tool_loop_side_effect = tool_loop_side_effect or (
            lambda contents, tools, cap: (contents, False)
        )
        self._raise_on_call = raise_on_call
        self.generate_structured_calls = []
        self.run_tool_loop_calls = []
        self.thinking_levels_seen = []

    def extract(self, *args, **kwargs):
        raise NotImplementedError

    def generate_structured(self, contents, schema, purpose, thinking_level=None):
        self.generate_structured_calls.append(purpose)
        self.thinking_levels_seen.append(thinking_level)
        if self._raise_on_call == purpose:
            raise RuntimeError("boom")
        response = self._structured_responses.pop(0)
        assert isinstance(response, schema)
        return response

    def run_tool_loop(self, contents, tools, max_tool_calls, purpose, thinking_level=None):
        self.run_tool_loop_calls.append(purpose)
        self.thinking_levels_seen.append(thinking_level)
        return self._tool_loop_side_effect(contents, tools, max_tool_calls)


def _processor_context(**overrides):
    base = {
        "processor": {
            "processor_id": "PWP-01",
            "capacity_t_per_year": 1200.0,
            "permitted_categories": ["I"],
            "consent_valid_from": "01/04/2022",
            "consent_valid_to": "31/03/2028",
        },
        "certificates": [
            {
                "certificate_id": "CERT-1",
                "category": "I",
                "period_month": "2026-01",
                "quantity_t": 100.0,
            }
        ],
        "shipments": [
            {
                "shipment_id": "SHP-1",
                "invoice_doc_id": "DOC-INV-1",
                "eway_doc_id": "DOC-EWB-1",
                "weighbridge_doc_id": "DOC-WB-1",
                "match_status": "matched",
                "month": "2026-01",
                "distance_km": 110.0,
                "eway_generated_at": "2026-01-14T06:20:00+00:00",
                "eway_valid_until": "2026-01-15T18:29:00+00:00",
                "weighbridge_in_time": "2026-01-14T10:00:00+00:00",
                "invoice_qty_t": 100.0,
                "weighbridge_net_t": 100.0,
            }
        ],
        "duplicate_keys": {},
        "check_results": [
            {
                "check_id": "C1",
                "status": "pass",
                "severity": "hard",
                "evidence_ids": [],
                "explanation": "within capacity",
            }
        ],
        "site_assessment": None,
        "documents": [
            {
                "doc_id": "DOC-INV-1",
                "doc_type": "inbound_invoice",
                "lang": "en",
                "gcs_path": "gs://bucket/DOC-INV-1.pdf",
                "fields": {"item_description": "post-consumer plastic waste", "hsn": "3915"},
            },
            {
                "doc_id": "DOC-WB-1",
                "doc_type": "weighbridge_slip",
                "lang": "en",
                "gcs_path": "gs://bucket/DOC-WB-1.png",
                "fields": {"remarks": ""},
            },
        ],
    }
    base.update(overrides)
    return base


def _text_turn_side_effect(contents, tools, max_tool_calls):
    model_turn = {"role": "model", "parts": [{"text": "no further evidence needed"}]}
    return [*contents, model_turn], False


def test_happy_path_confirms_accepted_objection_and_cites_shipment():
    conclusions = ConclusionsResponse(
        conclusions=[
            HypothesisConclusion(
                certificate_batch="2026-01",
                status="supported",
                evidence_ids=["DOC-INV-1"],
                explanation="verified inbound matches certified",
            )
        ]
    )
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="wording/HSN contradiction",
                cited_shipment_ids=["SHP-1"],
                evidence_ids=["DOC-INV-1"],
                explanation="description reads as virgin material",
            )
        ]
    )
    revisions = RevisionsResponse(
        revisions=[HypothesisRevision(objection_index=0, accepted=True, explanation="agreed")]
    )
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    result = run_agent_loop(_processor_context(), fake, deadline=time.monotonic() + 60)

    assert result["agent_status"] == "ok"
    assert result["conclusions"][0].status == "supported"
    assert len(result["confirmed_findings"]) == 1
    assert result["confirmed_findings"][0].cited_shipment_ids == ["SHP-1"]
    assert result["tool_cap_reached"] is False
    assert [step["step_type"] for step in result["trail"]] == [
        "hypothesis",
        "critic_model_turn",
        "critic_final",
        "revision",
    ]


def test_objection_with_no_valid_evidence_is_discarded():
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="x",
                cited_shipment_ids=["SHP-1"],
                evidence_ids=["DOC-DOES-NOT-EXIST"],
                explanation="unsupported",
            )
        ]
    )
    fake = _FakeLLMClient([conclusions, objections], tool_loop_side_effect=_text_turn_side_effect)

    result = run_agent_loop(_processor_context(), fake, deadline=time.monotonic() + 60)

    assert result["agent_status"] == "ok"
    assert result["objections"] == []
    assert result["confirmed_findings"] == []
    # No objections survived, so no revision round should have been run.
    assert "agent_revision" not in fake.generate_structured_calls


def test_invented_shipment_id_is_filtered_but_evidence_based_finding_survives():
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="x",
                cited_shipment_ids=["SHP-999"],  # invented, not in this processor's shipments
                evidence_ids=["DOC-INV-1"],  # real
                explanation="y",
            )
        ]
    )
    revisions = RevisionsResponse(revisions=[])
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    result = run_agent_loop(_processor_context(), fake, deadline=time.monotonic() + 60)

    assert len(result["objections"]) == 1
    assert result["objections"][0].cited_shipment_ids == []
    # No revision for index 0 -> the finding is confirmed by default.
    assert len(result["confirmed_findings"]) == 1


def test_failed_hard_check_downgrades_supported_conclusion():
    context = _processor_context(
        check_results=[
            {
                "check_id": "C2a",
                "status": "fail",
                "severity": "hard",
                "evidence_ids": [],
                "explanation": "shortfall",
            }
        ]
    )
    conclusions = ConclusionsResponse(
        conclusions=[
            HypothesisConclusion(
                certificate_batch="2026-01",
                status="supported",
                evidence_ids=[],
                explanation="looks fine",
            )
        ]
    )
    objections = ObjectionsResponse(objections=[])
    fake = _FakeLLMClient([conclusions, objections], tool_loop_side_effect=_text_turn_side_effect)

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    assert result["conclusions"][0].status == "partly_supported"
    assert "downgraded" in result["conclusions"][0].explanation


def test_tool_cap_reached_does_not_raise_and_is_recorded():
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(objections=[])
    fake = _FakeLLMClient(
        [conclusions, objections],
        tool_loop_side_effect=lambda contents, tools, cap: (contents, True),
    )

    result = run_agent_loop(_processor_context(), fake, deadline=time.monotonic() + 60)

    assert result["agent_status"] == "ok"
    assert result["tool_cap_reached"] is True
    assert "tool_cap_reached" in [step["step_type"] for step in result["trail"]]


def test_deadline_exceeded_after_hypothesis_returns_timeout_without_calling_critic():
    conclusions = ConclusionsResponse(
        conclusions=[
            HypothesisConclusion(
                certificate_batch="2026-01", status="supported", evidence_ids=[], explanation="x"
            )
        ]
    )
    fake = _FakeLLMClient([conclusions])

    result = run_agent_loop(_processor_context(), fake, deadline=time.monotonic() - 1)

    assert result["agent_status"] == "timeout"
    assert result["confirmed_findings"] == []
    assert len(result["conclusions"]) == 1
    assert fake.run_tool_loop_calls == []


def test_thinking_level_is_forwarded_to_every_gemini_call():
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="x",
                cited_shipment_ids=["SHP-1"],
                evidence_ids=["DOC-INV-1"],
                explanation="y",
            )
        ]
    )
    revisions = RevisionsResponse(
        revisions=[HypothesisRevision(objection_index=0, accepted=True, explanation="z")]
    )
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    run_agent_loop(_processor_context(), fake, deadline=time.monotonic() + 60, thinking_level="low")

    assert fake.thinking_levels_seen == ["low", "low", "low", "low"]


def test_unhandled_error_returns_error_status_without_raising():
    fake = _FakeLLMClient([], raise_on_call="agent_hypothesis")

    result = run_agent_loop(_processor_context(), fake, deadline=time.monotonic() + 60)

    assert result["agent_status"] == "error"
    assert result["conclusions"] == []
    assert result["confirmed_findings"] == []
