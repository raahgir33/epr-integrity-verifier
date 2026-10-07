"""Tests for app/agents/orchestrator.py against a fake LLMClient — no
network call. Covers every code-level rule in docs/ARCHITECTURE.md §4:
no-evidence findings discarded, invented IDs filtered, a failed hard check
can't be overruled, the tool-cap and timeout/error paths never raise.
"""

import time

from app.agents.orchestrator import build_context_pack, run_agent_loop
from app.models.agent import (
    ConclusionsResponse,
    CriticVerdict,
    HypothesisConclusion,
    HypothesisFindingResponse,
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
        "as_of_month": "2026-01",
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
                effect="raises_concern",
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
                effect="raises_concern",
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
                effect="raises_concern",
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
                effect="raises_concern",
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


def _clean_shipment(i: int) -> dict:
    return {
        "shipment_id": f"SHP-{i}",
        "invoice_doc_id": f"DOC-INV-{i}",
        "eway_doc_id": f"DOC-EWB-{i}",
        "weighbridge_doc_id": f"DOC-WB-{i}",
        "match_status": "matched",
        "month": "2026-01",
        "distance_km": 110.0,
        "eway_generated_at": "2026-01-14T06:20:00+00:00",
        "eway_valid_until": "2026-01-15T18:29:00+00:00",
        "weighbridge_in_time": "2026-01-14T10:00:00+00:00",
        "invoice_qty_t": 100.0,
        "weighbridge_net_t": 100.0,
    }


def _multi_shipment_context(n: int) -> dict:
    """n fully clean, matched, C3/C4/C5-passing shipments — every one of
    them counts toward verified_inbound_shipment_ids, so the systemic-
    finding guard's share calculation has a known, exact denominator."""
    shipments = [_clean_shipment(i) for i in range(1, n + 1)]
    documents = [
        {
            "doc_id": f"DOC-INV-{i}",
            "doc_type": "inbound_invoice",
            "lang": "en",
            "gcs_path": f"gs://bucket/DOC-INV-{i}.pdf",
            "fields": {"item_description": "post-consumer plastic waste", "hsn": "3915"},
        }
        for i in range(1, n + 1)
    ]
    return _processor_context(shipments=shipments, documents=documents, duplicate_keys={})


def _run_with_one_objection(
    context: dict, cited_shipment_ids: list[str], evidence_ids: list[str] | None = None
) -> dict:
    # Default evidence: each cited shipment's own invoice doc (DOC-INV-<n>
    # for SHP-<n>) — so these tests exercise the systemic-share rule in
    # isolation, not entangled with the own-evidence rule (own-evidence
    # has its own dedicated tests below). Pass evidence_ids explicitly to
    # test a finding resting on processor-level evidence only.
    if evidence_ids is None:
        evidence_ids = [f"DOC-INV-{sid.rsplit('-', 1)[-1]}" for sid in cited_shipment_ids]
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="x",
                effect="raises_concern",
                cited_shipment_ids=cited_shipment_ids,
                evidence_ids=evidence_ids,
                explanation="y",
            )
        ]
    )
    revisions = RevisionsResponse(revisions=[])
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )
    return run_agent_loop(context, fake, deadline=time.monotonic() + 60)


def test_finding_citing_minority_of_verified_shipments_is_deductible():
    # 1 of 4 verified shipments cited = 25%, well under the 50% threshold.
    context = _multi_shipment_context(4)

    result = _run_with_one_objection(context, ["SHP-1"])

    assert len(result["confirmed_findings"]) == 1
    assert len(result["deductible_findings"]) == 1
    assert result["systemic_findings"] == []


def test_finding_citing_exactly_half_of_verified_shipments_is_deductible():
    # 2 of 4 = exactly the threshold — the guard requires MORE than the
    # share, so this stays deductible (confirms the ">" is strict, not ">=").
    context = _multi_shipment_context(4)

    result = _run_with_one_objection(context, ["SHP-1", "SHP-2"])

    assert len(result["deductible_findings"]) == 1
    assert result["systemic_findings"] == []


def test_finding_citing_majority_of_verified_shipments_is_systemic():
    # 3 of 4 = 75%, over the 50% threshold — kept as a finding, not deducted.
    context = _multi_shipment_context(4)

    result = _run_with_one_objection(context, ["SHP-1", "SHP-2", "SHP-3"])

    assert len(result["confirmed_findings"]) == 1
    assert result["deductible_findings"] == []
    assert len(result["systemic_findings"]) == 1
    assert result["systemic_findings"][0].cited_shipment_ids == ["SHP-1", "SHP-2", "SHP-3"]


def test_resolves_concern_objection_is_not_a_finding_but_stays_in_trail():
    context = _multi_shipment_context(4)
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="raises one",
                effect="raises_concern",
                cited_shipment_ids=["SHP-1"],
                evidence_ids=["DOC-INV-1"],
                explanation="a",
            ),
            Objection(
                finding_type="resolves one",
                effect="resolves_concern",
                cited_shipment_ids=["SHP-1"],
                evidence_ids=["DOC-INV-1"],
                explanation="actually fine given the evidence",
            ),
        ]
    )
    revisions = RevisionsResponse(revisions=[])
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    # Only the raises_concern objection survives into objections/confirmed_findings.
    assert len(result["objections"]) == 1
    assert result["objections"][0].finding_type == "raises one"
    assert len(result["confirmed_findings"]) == 1
    assert len(result["deductible_findings"]) == 1
    # But the resolves_concern objection still reached the raw critic_final
    # trail step, logged before any effect/evidence filtering.
    critic_final_step = next(s for s in result["trail"] if s["step_type"] == "critic_final")
    assert "resolves one" in critic_final_step["output_json"]
    assert "raises one" in critic_final_step["output_json"]


def test_only_resolves_concern_objection_yields_no_findings_and_no_revision_call():
    context = _multi_shipment_context(4)
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="resolves one",
                effect="resolves_concern",
                cited_shipment_ids=["SHP-1"],
                evidence_ids=["DOC-INV-1"],
                explanation="actually fine given the evidence",
            )
        ]
    )
    fake = _FakeLLMClient([conclusions, objections], tool_loop_side_effect=_text_turn_side_effect)

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    assert result["objections"] == []
    assert result["confirmed_findings"] == []
    assert result["excluded_shipment_ids"] == frozenset()
    # No raises_concern objection survived, so no revision round should run.
    assert "agent_revision" not in fake.generate_structured_calls
    critic_final_step = next(s for s in result["trail"] if s["step_type"] == "critic_final")
    assert "resolves one" in critic_final_step["output_json"]


def test_finding_resting_only_on_processor_level_evidence_is_not_deducted():
    """A finding citing shipments in a low-energy month, evidenced only by
    that month's electricity bill — never any of those shipments' own
    invoice/e-way-bill/weighbridge documents. Kept as a finding, flagged
    for review, but deducts nothing."""
    context = _multi_shipment_context(4)
    context["documents"].append(
        {
            "doc_id": "DOC-ELEC-1",
            "doc_type": "electricity_bill",
            "lang": "en",
            "gcs_path": "gs://bucket/DOC-ELEC-1.pdf",
            "fields": {"billing_month": "2026-01"},
        }
    )

    result = _run_with_one_objection(context, ["SHP-1", "SHP-2"], evidence_ids=["DOC-ELEC-1"])

    assert len(result["confirmed_findings"]) == 1
    assert result["deductible_findings"] == []
    assert result["systemic_findings"] == []
    assert len(result["no_evidence_findings"]) == 1
    assert result["excluded_shipment_ids"] == frozenset()


def test_finding_mixing_shipment_and_processor_level_evidence_is_not_deducted():
    """PWP-07's real pattern (third canary, docs/PROGRESS.md): the
    finding's evidence included BOTH the cited shipments' own invoices
    AND the electricity bill its F7 concern actually rested on. Valid
    shipment-level evidence being present does not offset processor-
    level evidence also being present — the whole finding stays a
    review flag, not partially deducted."""
    context = _multi_shipment_context(4)
    context["documents"].append(
        {
            "doc_id": "DOC-ELEC-1",
            "doc_type": "electricity_bill",
            "lang": "en",
            "gcs_path": "gs://bucket/DOC-ELEC-1.pdf",
            "fields": {"billing_month": "2026-01"},
        }
    )

    result = _run_with_one_objection(
        context, ["SHP-1", "SHP-2"], evidence_ids=["DOC-INV-1", "DOC-INV-2", "DOC-ELEC-1"]
    )

    assert len(result["confirmed_findings"]) == 1
    assert result["deductible_findings"] == []
    assert result["systemic_findings"] == []
    assert len(result["no_evidence_findings"]) == 1
    assert result["excluded_shipment_ids"] == frozenset()


def test_finding_with_partial_own_evidence_deducts_nothing():
    """A finding citing two shipments but only one of their own documents
    is in evidence — not every cited shipment is evidenced, so (reworked
    own-evidence rule, docs/PROGRESS.md) the whole finding deducts
    nothing, rather than partially deducting the one evidenced shipment."""
    context = _multi_shipment_context(4)

    result = _run_with_one_objection(context, ["SHP-1", "SHP-2"], evidence_ids=["DOC-INV-1"])

    assert result["deductible_findings"] == []
    assert result["systemic_findings"] == []
    assert len(result["no_evidence_findings"]) == 1
    assert result["excluded_shipment_ids"] == frozenset()


def test_finding_with_full_own_evidence_for_every_cited_shipment_is_deducted():
    """F8-style finding: every cited shipment has its own invoice in
    evidence, no processor-level evidence mixed in — fully deductible."""
    context = _multi_shipment_context(4)

    result = _run_with_one_objection(
        context, ["SHP-1", "SHP-2"], evidence_ids=["DOC-INV-1", "DOC-INV-2"]
    )

    assert len(result["deductible_findings"]) == 1
    assert result["systemic_findings"] == []
    assert result["no_evidence_findings"] == []
    assert result["excluded_shipment_ids"] == frozenset({"SHP-1", "SHP-2"})


def _hypothesis_finding(**overrides) -> Objection:
    base = {
        "finding_type": "x",
        "effect": "raises_concern",
        "cited_shipment_ids": ["SHP-1"],
        "evidence_ids": ["DOC-INV-1"],
        "explanation": "the Hypothesis found this",
    }
    base.update(overrides)
    return Objection(**base)


def test_hypothesis_finding_upheld_by_critic_is_confirmed_and_deductible():
    context = _multi_shipment_context(4)
    conclusions = ConclusionsResponse(conclusions=[], findings=[_hypothesis_finding()])
    objections = ObjectionsResponse(
        verdicts=[CriticVerdict(hypothesis_finding_index=0, verdict="upheld", reason="agreed")],
        objections=[],
    )
    fake = _FakeLLMClient([conclusions, objections], tool_loop_side_effect=_text_turn_side_effect)

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    assert len(result["hypothesis_findings"]) == 1
    assert len(result["verdicts"]) == 1
    assert len(result["confirmed_findings"]) == 1
    assert len(result["deductible_findings"]) == 1
    assert result["review_flag_findings"] == []
    assert result["withdrawn_findings"] == []
    assert result["excluded_shipment_ids"] == frozenset({"SHP-1"})
    # Upheld needs no response from the Hypothesis — no revision call at all.
    assert "agent_revision" not in fake.generate_structured_calls


def test_hypothesis_finding_disputed_and_maintained_is_review_flag_only():
    context = _multi_shipment_context(4)
    conclusions = ConclusionsResponse(conclusions=[], findings=[_hypothesis_finding()])
    objections = ObjectionsResponse(
        verdicts=[
            CriticVerdict(hypothesis_finding_index=0, verdict="disputed", reason="doesn't hold up")
        ],
        objections=[],
    )
    revisions = RevisionsResponse(
        hypothesis_finding_responses=[
            HypothesisFindingResponse(
                hypothesis_finding_index=0, decision="maintain", explanation="still stands"
            )
        ]
    )
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    assert result["confirmed_findings"] == []
    assert result["deductible_findings"] == []
    assert len(result["review_flag_findings"]) == 1
    assert result["withdrawn_findings"] == []
    assert result["excluded_shipment_ids"] == frozenset()


def test_hypothesis_finding_disputed_and_withdrawn_is_trail_only():
    context = _multi_shipment_context(4)
    conclusions = ConclusionsResponse(conclusions=[], findings=[_hypothesis_finding()])
    objections = ObjectionsResponse(
        verdicts=[
            CriticVerdict(hypothesis_finding_index=0, verdict="disputed", reason="doesn't hold up")
        ],
        objections=[],
    )
    revisions = RevisionsResponse(
        hypothesis_finding_responses=[
            HypothesisFindingResponse(
                hypothesis_finding_index=0, decision="withdraw", explanation="fair point"
            )
        ]
    )
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    assert result["confirmed_findings"] == []
    assert result["review_flag_findings"] == []
    assert len(result["withdrawn_findings"]) == 1
    assert result["excluded_shipment_ids"] == frozenset()


def test_hypothesis_finding_with_no_critic_verdict_defaults_to_review_flag():
    """Silence isn't agreement: if the Critic never gives a verdict on a
    Hypothesis finding (and the Hypothesis itself never responds either),
    it defaults to a review flag, not silent confirmation or disposal."""
    context = _multi_shipment_context(4)
    conclusions = ConclusionsResponse(conclusions=[], findings=[_hypothesis_finding()])
    objections = ObjectionsResponse(verdicts=[], objections=[])
    revisions = RevisionsResponse(hypothesis_finding_responses=[])
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    assert result["confirmed_findings"] == []
    assert len(result["review_flag_findings"]) == 1
    assert result["withdrawn_findings"] == []


def test_critic_raised_finding_rejected_by_hypothesis_is_review_flag_not_discarded():
    """Reworked default (docs/PROGRESS.md): a rejected Critic finding used
    to be fully discarded; now it's kept as a review flag, visible but
    never deducted."""
    context = _multi_shipment_context(4)
    conclusions = ConclusionsResponse(conclusions=[])
    objections = ObjectionsResponse(
        objections=[
            Objection(
                finding_type="x",
                effect="raises_concern",
                cited_shipment_ids=["SHP-1"],
                evidence_ids=["DOC-INV-1"],
                explanation="critic found this",
            )
        ]
    )
    revisions = RevisionsResponse(
        revisions=[
            HypothesisRevision(objection_index=0, accepted=False, explanation="doesn't hold up")
        ]
    )
    fake = _FakeLLMClient(
        [conclusions, objections, revisions], tool_loop_side_effect=_text_turn_side_effect
    )

    result = run_agent_loop(context, fake, deadline=time.monotonic() + 60)

    assert result["confirmed_findings"] == []
    assert len(result["review_flag_findings"]) == 1
    assert result["review_flag_findings"][0].finding_type == "x"
    assert result["excluded_shipment_ids"] == frozenset()


def test_build_context_pack_shows_capacity_as_a_single_fy_to_date_figure():
    context = _processor_context()

    pack = build_context_pack(context)

    assert pack["capacity_status"] == {
        "as_of_month": "2026-01",
        "certified_t_fy_to_date": 100.0,
        "capacity_limit_t_fy_to_date": 1200.0 * 10 / 12,
    }
    # No per-month capacity column — each monthly_table row is month/
    # certified_t/verified_inbound_t only.
    for row in pack["monthly_table"]:
        assert set(row) == {"month", "certified_t", "verified_inbound_t"}


def test_build_context_pack_includes_compact_shipment_table():
    context = _processor_context()

    pack = build_context_pack(context)

    assert pack["shipment_table"] == [
        {
            "shipment_id": "SHP-1",
            "month": "2026-01",
            "invoice_qty_t": 100.0,
            "weighbridge_net_t": 100.0,
            "match_status": "matched",
            "invoice_doc_id": "DOC-INV-1",
            "eway_doc_id": "DOC-EWB-1",
            "weighbridge_doc_id": "DOC-WB-1",
        }
    ]


def test_unhandled_error_returns_error_status_without_raising():
    fake = _FakeLLMClient([], raise_on_call="agent_hypothesis")

    result = run_agent_loop(_processor_context(), fake, deadline=time.monotonic() + 60)

    assert result["agent_status"] == "error"
    assert result["conclusions"] == []
    assert result["confirmed_findings"] == []
