"""Hypothesis -> Critic (tools) -> revision orchestration
(docs/ARCHITECTURE.md §4). run_agent_loop is the single entry point and is
fully testable against a fake LLMClient (app/llm.py's Protocol) — nothing
in this module makes a network call itself.

processor_context: {
    "processor": {processor_id, capacity_t_per_year, permitted_categories,
        consent_valid_from, consent_valid_to},
    "certificates": [...], "shipments": [...], "duplicate_keys": {...},
    "as_of_month": "YYYY-MM" (the run's cutoff — build_capacity_status
        shows C1's own FY-to-date basis at exactly this point, the same
        "as_of_month" scripts/run_pipeline.py/scorer.py already use),
    "check_results": [dict, ...]  (already CheckResult.model_dump()'d —
        app/agents/tools.py's build_tools expects plain dicts, matching
        its own test fixture, not Pydantic objects),
    "site_assessment": dict | None,
    "documents": [{"doc_id", "doc_type", "lang", "gcs_path", "fields"}],
    "gcs_client": optional, only needed if a tool call reads a document,
}

Every field that reaches a prompt or a tool result is document-observable
or check-computed — never a ground-truth-only evaluation label (T10's
leak guard; see docs/PROGRESS.md and tests/test_agent_leak_guard.py).
"""

import json
import logging
import time

from app.agents import tools as agent_tools
from app.agents.prompts import (
    CRITIC_FINAL_PROMPT,
    CRITIC_TOOLS_PROMPT,
    HYPOTHESIS_PROMPT,
    REVISION_PROMPT,
)
from app.checks import params
from app.checks.capacity import capacity_limit_t, certified_t_fy_to_date, months_elapsed_in_fy
from app.checks.mass_balance import verified_inbound_shipment_ids, verified_inbound_tonnes
from app.llm import LLMClient
from app.models.agent import (
    ConclusionsResponse,
    HypothesisConclusion,
    Objection,
    ObjectionsResponse,
    RevisionsResponse,
)

logger = logging.getLogger(__name__)


def _build_capacity_status(processor: dict, certificates: list[dict], as_of_month: str) -> dict:
    """Capacity shown exactly as C1 itself judges it (docs/PROGRESS.md) —
    a single FY-to-date figure at the run's as_of_month, not a per-month
    breakdown. C1 is a cumulative comparison (certified tonnes so far
    this FY vs capacity available so far), not something each month has
    its own independent share of; a prior per-month "capacity_limit_t"
    table column (itself a fix for an even earlier flat annual/12 share)
    still implied a false month-by-month capacity judgement that doesn't
    match what the actual hard check computes. Reuses
    app/checks/capacity.py's own functions, the same ones check_c1 itself
    calls — never a second, independent computation of the same figure."""
    return {
        "as_of_month": as_of_month,
        "certified_t_fy_to_date": round(certified_t_fy_to_date(certificates, as_of_month), 2),
        "capacity_limit_t_fy_to_date": round(
            capacity_limit_t(processor["capacity_t_per_year"], months_elapsed_in_fy(as_of_month)),
            2,
        ),
    }


def _build_monthly_table(
    certificates: list[dict], shipments: list[dict], duplicate_keys: dict
) -> list[dict]:
    """Per-period_month certified tonnes (that month's own slice, not
    cumulative) and verified-inbound tonnes — for the Hypothesis's
    per-batch judgement (docs/ARCHITECTURE.md §4). Capacity is
    deliberately NOT a column here — see _build_capacity_status, a
    single FY-to-date figure shown once, not implied per month.
    verified_inbound_t reuses mass_balance.py's own C3-C5 pass logic
    (filtered to that month's shipments), never a re-derivation of it —
    this is contextual, not the authoritative FY-to-date figure (that's
    app/agents/scorer.py's job, included separately in check_results)."""
    months = sorted(
        {c["period_month"] for c in certificates}
        | {s["month"] for s in shipments if s.get("month")}
    )
    table = []
    for month in months:
        certified_t = sum(c["quantity_t"] for c in certificates if c["period_month"] == month)
        month_shipments = [s for s in shipments if s.get("month") == month]
        verified_inbound_t = verified_inbound_tonnes(month_shipments, duplicate_keys)
        table.append(
            {
                "month": month,
                "certified_t": round(certified_t, 2),
                "verified_inbound_t": round(verified_inbound_t, 2),
            }
        )
    return table


def _build_shipment_table(shipments: list[dict]) -> list[dict]:
    """Compact, context-pack-level shipment index (docs/PROGRESS.md: tool
    efficiency) — every shipment's month, quantities, match status and
    its own document IDs, all reachable without a get_shipments tool
    call. The fourth canary's PWP-08 trail spent 5 of its 8 tool calls
    re-fetching shipment data already available this way."""
    return [
        {
            "shipment_id": s["shipment_id"],
            "month": s.get("month"),
            "invoice_qty_t": s.get("invoice_qty_t"),
            "weighbridge_net_t": s.get("weighbridge_net_t"),
            "match_status": s.get("match_status"),
            **_shipment_doc_ids(s),
        }
        for s in shipments
    ]


def _shipment_doc_ids(shipment: dict) -> dict:
    """This shipment's own document IDs — invoice, e-way bill,
    weighbridge slip — exactly what the own-evidence rule (docs/
    PROGRESS.md) requires a citing finding's evidence_ids to include at
    least one of. Merged into every digest entry that names a shipment,
    so the Critic can satisfy that rule from the digest alone, without a
    separate get_shipments tool call (the call still works too — same
    data, just also reachable without it)."""
    return {
        "invoice_doc_id": shipment.get("invoice_doc_id"),
        "eway_doc_id": shipment.get("eway_doc_id"),
        "weighbridge_doc_id": shipment.get("weighbridge_doc_id"),
    }


def _build_dossier_digest(shipments: list[dict], documents: list[dict]) -> dict:
    """docs/ARCHITECTURE.md §4: distinct inbound item descriptions with
    HSN + shipment IDs, non-empty weighbridge remarks, unmatched records
    — what lets the agents notice semantic contradictions without
    re-reading every file. Every shipment reference here carries its own
    document IDs (_shipment_doc_ids above) alongside its shipment_id.
    Only document-observable fields (printed invoice/weighbridge content,
    shipment linkage) — never a ground-truth-only label."""
    shipments_by_id = {s["shipment_id"]: s for s in shipments}
    invoice_doc_to_shipment = {
        s["invoice_doc_id"]: s["shipment_id"] for s in shipments if s.get("invoice_doc_id")
    }
    weighbridge_doc_to_shipment = {
        s["weighbridge_doc_id"]: s["shipment_id"] for s in shipments if s.get("weighbridge_doc_id")
    }

    def _shipment_entry(shipment_id: str) -> dict:
        return {
            "shipment_id": shipment_id,
            **_shipment_doc_ids(shipments_by_id.get(shipment_id, {})),
        }

    item_descriptions: dict[tuple[str, str | None], list[str]] = {}
    weighbridge_remarks = []
    for doc in documents:
        fields = doc.get("fields") or {}
        if doc.get("doc_type") == "inbound_invoice":
            description = fields.get("item_description")
            shipment_id = invoice_doc_to_shipment.get(doc.get("doc_id"))
            if description and shipment_id:
                key = (description, fields.get("hsn"))
                item_descriptions.setdefault(key, []).append(shipment_id)
        elif doc.get("doc_type") == "weighbridge_slip":
            remarks = (fields.get("remarks") or "").strip()
            shipment_id = weighbridge_doc_to_shipment.get(doc.get("doc_id"))
            if remarks and shipment_id:
                weighbridge_remarks.append({"shipment_id": shipment_id, "remarks": remarks})

    unmatched_shipment_ids = [
        s["shipment_id"] for s in shipments if s.get("match_status") != "matched"
    ]

    return {
        "item_descriptions": [
            {
                "description": desc,
                "hsn": hsn,
                "shipments": [_shipment_entry(sid) for sid in ids],
            }
            for (desc, hsn), ids in item_descriptions.items()
        ],
        "weighbridge_remarks": [
            {**_shipment_entry(r["shipment_id"]), "remarks": r["remarks"]}
            for r in weighbridge_remarks
        ],
        "unmatched_shipments": [_shipment_entry(sid) for sid in unmatched_shipment_ids],
    }


def build_context_pack(processor_context: dict) -> dict:
    processor = processor_context["processor"]
    return {
        "processor_profile": {
            "processor_id": processor["processor_id"],
            "capacity_t_per_year": processor["capacity_t_per_year"],
            "permitted_categories": processor["permitted_categories"],
            "consent_valid_from": processor["consent_valid_from"],
            "consent_valid_to": processor["consent_valid_to"],
        },
        "capacity_status": _build_capacity_status(
            processor, processor_context["certificates"], processor_context["as_of_month"]
        ),
        "monthly_table": _build_monthly_table(
            processor_context["certificates"],
            processor_context["shipments"],
            processor_context["duplicate_keys"],
        ),
        "shipment_table": _build_shipment_table(processor_context["shipments"]),
        "check_results": processor_context["check_results"],
        "site_assessment": processor_context.get("site_assessment"),
        "dossier_digest": _build_dossier_digest(
            processor_context["shipments"], processor_context["documents"]
        ),
    }


def _valid_evidence_ids(processor_context: dict) -> set[str]:
    """IDs the Critic is allowed to cite as evidence: this processor's own
    document IDs, plus whatever a deterministic check already cited
    (covers C6's certificate_id and C8's thumbnail path, neither of which
    is a doc_id)."""
    doc_ids = {d["doc_id"] for d in processor_context["documents"]}
    check_evidence = {
        eid for r in processor_context["check_results"] for eid in r.get("evidence_ids", [])
    }
    return doc_ids | check_evidence


def _filter_objection(
    objection: Objection, processor_context: dict, verified_shipment_ids: frozenset[str]
) -> Objection | None:
    """Code-level ID validation (docs/ARCHITECTURE.md §4: "a finding
    without at least one valid evidence ID is discarded") — never trusted
    from the model. Returns None if no valid evidence survives filtering;
    an invented shipment ID is dropped from cited_shipment_ids without
    discarding the whole finding, since the evidence may still be real.

    cited_shipment_ids is filtered against verified_shipment_ids (matched
    AND passing C3a/C3b/C4/C5 — mass_balance.verified_inbound_shipment_ids),
    not merely "exists in this processor's data" (docs/PROGRESS.md): a
    shipment that's unmatched or already failing a hard check was never
    counted in verified inbound tonnes to begin with, so citing it can't
    mean anything for deduction and shouldn't survive into a scored
    finding's cited_shipment_ids."""
    valid_evidence = _valid_evidence_ids(processor_context)
    evidence_ids = [e for e in objection.evidence_ids if e in valid_evidence]
    if not evidence_ids:
        return None
    cited_shipment_ids = [s for s in objection.cited_shipment_ids if s in verified_shipment_ids]
    return objection.model_copy(
        update={"evidence_ids": evidence_ids, "cited_shipment_ids": cited_shipment_ids}
    )


def _any_hard_check_failed(check_results: list[dict]) -> bool:
    return any(r.get("severity") == "hard" and r.get("status") == "fail" for r in check_results)


def _enforce_hard_check_floor(
    conclusions: list[HypothesisConclusion], check_results: list[dict]
) -> list[HypothesisConclusion]:
    """docs/ARCHITECTURE.md §4: "a failed hard deterministic check cannot
    be overruled by an agent." If any hard check failed for this
    processor, no certificate batch's conclusion may claim "supported" —
    downgraded here, in code, never left to the model's own judgement."""
    if not _any_hard_check_failed(check_results):
        return conclusions
    downgraded = []
    for c in conclusions:
        if c.status == "supported":
            c = c.model_copy(
                update={
                    "status": "partly_supported",
                    "explanation": c.explanation
                    + " (downgraded: a hard deterministic check failed for this processor.)",
                }
            )
        downgraded.append(c)
    return downgraded


def _get(obj, key, default=None):
    """Works against both plain dicts (fake-client tests) and the real
    google.genai types.Content/Part/FunctionCall objects (attribute
    access) — this module never constructs either, only reads them back
    for the agent_runs trail log."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _summarize_content(content) -> dict:
    if isinstance(content, str):
        return {"text": content}
    parts = _get(content, "parts") or []
    summarized_parts = []
    for part in parts:
        function_call = _get(part, "function_call")
        function_response = _get(part, "function_response")
        inline_data = _get(part, "inline_data")
        text = _get(part, "text")
        if function_call is not None:
            summarized_parts.append({"function_call": _get(function_call, "name")})
        elif function_response is not None:
            summarized_parts.append({"function_response": _get(function_response, "response")})
        elif inline_data is not None:
            summarized_parts.append({"inline_data_mime_type": _get(inline_data, "mime_type")})
        elif text is not None:
            summarized_parts.append({"text": text})
    return {"role": _get(content, "role"), "parts": summarized_parts}


def _trail_step(step_index: int, step_type: str, **fields) -> dict:
    row = {
        "step_index": step_index,
        "step_type": step_type,
        "tool_name": None,
        "tool_args_json": None,
        "input_summary": None,
        "output_json": None,
    }
    row.update(fields)
    return row


def _result(
    agent_status: str,
    conclusions=None,
    hypothesis_findings=None,
    verdicts=None,
    objections=None,
    revisions=None,
    hypothesis_finding_responses=None,
    confirmed_findings=None,
    review_flag_findings=None,
    withdrawn_findings=None,
    deductible_findings=None,
    systemic_findings=None,
    no_evidence_findings=None,
    concurs_with_check_findings=None,
    excluded_shipment_ids=None,
    trail=None,
    tool_cap_reached=False,
) -> dict:
    return {
        "conclusions": conclusions or [],
        "hypothesis_findings": hypothesis_findings or [],
        "verdicts": verdicts or [],
        "objections": objections or [],
        "revisions": revisions or [],
        "hypothesis_finding_responses": hypothesis_finding_responses or [],
        "confirmed_findings": confirmed_findings or [],
        "review_flag_findings": review_flag_findings or [],
        "withdrawn_findings": withdrawn_findings or [],
        "deductible_findings": deductible_findings or [],
        "systemic_findings": systemic_findings or [],
        "no_evidence_findings": no_evidence_findings or [],
        "concurs_with_check_findings": concurs_with_check_findings or [],
        "excluded_shipment_ids": excluded_shipment_ids or frozenset(),
        "trail": trail or [],
        "tool_cap_reached": tool_cap_reached,
        "agent_status": agent_status,
    }


_SHIPMENT_LEVEL_DOC_TYPES = {"inbound_invoice", "eway_bill", "weighbridge_slip"}


def _shipment_own_doc_ids(shipment: dict) -> set[str]:
    return {
        doc_id
        for doc_id in (
            shipment.get("invoice_doc_id"),
            shipment.get("eway_doc_id"),
            shipment.get("weighbridge_doc_id"),
        )
        if doc_id
    }


def _is_shipment_level_evidence_id(evidence_id: str, documents_by_id: dict[str, dict]) -> bool:
    doc = documents_by_id.get(evidence_id)
    return doc is not None and doc.get("doc_type") in _SHIPMENT_LEVEL_DOC_TYPES


def _evidenced_shipment_ids(
    finding: Objection, shipments_by_id: dict[str, dict], documents_by_id: dict[str, dict]
) -> frozenset[str]:
    """Own-evidence rule, reworked after the third canary (docs/
    PROGRESS.md): the first version was satisfiable by attaching a
    shipment's own invoice *alongside* a processor-level document (PWP-07
    did exactly that — invoices plus the electricity bill its F7 finding
    actually rested on) — valid shipment-level evidence being present
    doesn't offset processor-level evidence also being present.

    A finding's evidence must now be shipment-level *only*: if even one
    evidence_id isn't one of the three shipment-level document types
    (invoice, e-way bill, weighbridge slip) — an electricity bill, site
    imagery, a CTO/consent or EPR registration document, an output
    invoice, or any non-document evidence_id (a certificate_id, a site
    thumbnail path) all count as processor-level — the WHOLE finding is
    processor-level, never partially deductible.

    Even with shipment-level-only evidence, every CITED shipment must
    have at least one of its own documents among that evidence for the
    finding to be deductible at all: a finding that evidences some but
    not all of its cited shipments deducts nothing, rather than
    partially deducting the evidenced subset. Returns the empty set in
    both failure cases; returns the full, unfiltered cited_shipment_ids
    (every member individually evidenced, by construction) when the
    finding qualifies.
    """
    evidence_ids = finding.evidence_ids
    if not finding.cited_shipment_ids:
        return frozenset()
    if any(not _is_shipment_level_evidence_id(eid, documents_by_id) for eid in evidence_ids):
        return frozenset()
    evidence = set(evidence_ids)
    for sid in finding.cited_shipment_ids:
        shipment = shipments_by_id.get(sid)
        if shipment is None or not (_shipment_own_doc_ids(shipment) & evidence):
            return frozenset()
    return frozenset(finding.cited_shipment_ids)


_CONCERNING_CHECK_STATUSES = {"fail", "warn"}


def _failed_or_warned_check_evidence_ids(check_results: list[dict]) -> frozenset[str]:
    """Evidence already surfaced by a deterministic check that failed
    (hard) or warned (soft) — C4/C5 fails, C7/C8 warns, etc. (docs/
    PROGRESS.md's concurs-with-check rule)."""
    return frozenset(
        eid
        for r in check_results
        if r.get("status") in _CONCERNING_CHECK_STATUSES
        for eid in r.get("evidence_ids", [])
    )


def _concurs_with_check(
    finding: Objection,
    verified_shipment_ids: frozenset[str],
    failed_or_warned_evidence: frozenset[str],
) -> bool:
    """A confirmed finding adds nothing beyond what a deterministic check
    already flagged if either: every shipment it cites is already
    excluded from verified_inbound_shipment_ids by a hard check (mostly
    moot now that _filter_objection's cited-ID validation only admits
    verified shipment IDs in the first place — kept as a defense-in-depth
    guard matching the rule as specified, in case a finding is ever built
    from an unfiltered cited_shipment_ids list); or its evidence_ids
    overlap with a failed/warned check's own evidence — the same
    documents a check already cited. Neutral, not a new signal: shown in
    the trail, never deducted, never an extra soft-signal risk-band bump
    (docs/PROGRESS.md)."""
    if finding.cited_shipment_ids and all(
        sid not in verified_shipment_ids for sid in finding.cited_shipment_ids
    ):
        return True
    return bool(set(finding.evidence_ids) & failed_or_warned_evidence)


def _classify_findings(
    confirmed_findings: list[Objection],
    verified_shipment_ids: frozenset[str],
    shipments_by_id: dict[str, dict],
    documents_by_id: dict[str, dict],
    check_results: list[dict],
) -> tuple[list[Objection], list[Objection], list[Objection], list[Objection], frozenset[str]]:
    """Three guards against over-broad or redundant deduction, applied in
    order, per finding (docs/PROGRESS.md):

    0. Concurs-with-check: a finding that only restates what a
       deterministic check already caught (see _concurs_with_check) is
       neutral — kept as a finding (shown in the UI/trail) but moved to
       concurs_with_check_findings, never deducted and never contributing
       a soft-signal bump of its own (the check it concurs with already
       did whatever scoring work was warranted).
    1. Own-evidence rule: a finding whose evidence isn't shipment-level
       only, or doesn't cover every one of its cited shipments (see
       _evidenced_shipment_ids), can't deduct anything — it's kept as a
       finding (shown in the UI/trail) but moved to no_evidence_findings,
       a review flag, not a tonnage deduction.
    2. Systemic-finding guard: a finding's (now all-or-nothing) evidenced
       shipments citing more than params.SYSTEMIC_FINDING_SHARE_THRESHOLD
       of the processor's own verified shipments is too broad to treat as
       ordinary per-shipment evidence — deducting all of them would let
       one finding zero out most of the processor's verifiable tonnage.
       Moved to systemic_findings instead of deductible_findings.

    app/agents/scorer.py's build_no_own_evidence_finding_check_result and
    build_systemic_finding_check_result turn their respective non-empty
    list into a soft-signal risk-band bump instead of a tonnage
    deduction; concurs_with_check_findings gets no such synthetic check
    result — it is deliberately scoring-neutral. excluded_shipment_ids is
    the union of deductible findings' (full) cited_shipment_ids —
    computed once here, the single source of truth callers use for the
    actual deduction, rather than each caller re-deriving it.

    With zero verified shipments, "cites more than half of them" has no
    meaningful denominator — every evidenced finding is deductible in
    that case, same as before the systemic guard existed.
    """
    deductible: list[Objection] = []
    systemic: list[Objection] = []
    no_evidence: list[Objection] = []
    concurs_with_check: list[Objection] = []
    excluded_shipment_ids: set[str] = set()
    failed_or_warned_evidence = _failed_or_warned_check_evidence_ids(check_results)
    for finding in confirmed_findings:
        if _concurs_with_check(finding, verified_shipment_ids, failed_or_warned_evidence):
            concurs_with_check.append(finding)
            continue
        evidenced = _evidenced_shipment_ids(finding, shipments_by_id, documents_by_id)
        if not evidenced:
            no_evidence.append(finding)
            continue
        if verified_shipment_ids:
            share = len(evidenced & verified_shipment_ids) / len(verified_shipment_ids)
        else:
            share = 0.0
        if share > params.SYSTEMIC_FINDING_SHARE_THRESHOLD:
            systemic.append(finding)
        else:
            deductible.append(finding)
            excluded_shipment_ids |= evidenced
    return deductible, systemic, no_evidence, concurs_with_check, frozenset(excluded_shipment_ids)


def classify_confirmed_findings(
    confirmed_findings: list[Objection], processor_context: dict
) -> dict:
    """Public entry point to _classify_findings, for callers that already
    have a set of confirmed_findings (an agreement outcome a real
    run_agent_loop call produced) and want to re-run ONLY the
    deductible/systemic/no_evidence/concurs-with-check classification —
    e.g. after a scoring-rule change, against a processor's current
    check_results, without re-calling Gemini at all (docs/PROGRESS.md's
    concurs-with-check rule rollout; scripts/probe_agent_thinking.py's
    --rescore mode). run_agent_loop itself also calls this, so the real
    live path and any offline re-score use the exact same logic.

    Returns {deductible_findings, systemic_findings, no_evidence_findings,
    concurs_with_check_findings, excluded_shipment_ids}."""
    verified_shipment_ids = verified_inbound_shipment_ids(
        processor_context["shipments"], processor_context["duplicate_keys"]
    )
    shipments_by_id = {s["shipment_id"]: s for s in processor_context["shipments"]}
    documents_by_id = {d["doc_id"]: d for d in processor_context["documents"]}
    (
        deductible_findings,
        systemic_findings,
        no_evidence_findings,
        concurs_with_check_findings,
        excluded_shipment_ids,
    ) = _classify_findings(
        confirmed_findings,
        verified_shipment_ids,
        shipments_by_id,
        documents_by_id,
        processor_context["check_results"],
    )
    return {
        "deductible_findings": deductible_findings,
        "systemic_findings": systemic_findings,
        "no_evidence_findings": no_evidence_findings,
        "concurs_with_check_findings": concurs_with_check_findings,
        "excluded_shipment_ids": excluded_shipment_ids,
    }


def run_agent_loop(
    processor_context: dict,
    llm_client: LLMClient,
    deadline: float,
    thinking_level: str | None = None,
) -> dict:
    """Returns {conclusions, hypothesis_findings, verdicts, objections,
    revisions, hypothesis_finding_responses, confirmed_findings,
    review_flag_findings, withdrawn_findings, deductible_findings,
    systemic_findings, no_evidence_findings, concurs_with_check_findings,
    excluded_shipment_ids, trail, tool_cap_reached, agent_status}.

    docs/PROGRESS.md's Hypothesis-findings restructure: the Hypothesis now
    proposes findings of its own (hypothesis_findings, same Objection
    shape as a Critic finding), not only batch-level conclusions. The
    Critic gives each one a verdict (verdicts: upheld/disputed) and may
    also raise new findings of its own (objections, unchanged meaning).
    The Hypothesis then responds to every disputed-or-unaddressed finding
    of its own (hypothesis_finding_responses: maintain/withdraw) and to
    every new Critic finding (revisions: accept/reject, unchanged).

    confirmed_findings = findings both agents agree on (a Hypothesis
    finding the Critic upheld, or a Critic finding the Hypothesis accepted
    or never addressed) — these alone feed _classify_findings
    (deductible/systemic/no_evidence, as before). review_flag_findings =
    findings the agents did NOT agree on (disputed-and-maintained-or-
    unaddressed Hypothesis findings; rejected Critic findings) — kept
    visible, never deducted, contributing a soft-signal risk-band bump
    via app/agents/scorer.py's build_disputed_finding_check_result.
    withdrawn_findings = a Hypothesis finding the Hypothesis itself
    withdrew after the Critic disputed it — visible only in the trail,
    no scoring effect at all; a finding only vanishes from the live
    buckets when EXPLICITLY withdrawn, never by silent omission.

    excluded_shipment_ids is the ready-made deduction set — the single
    thing callers need to pass to app/agents/scorer.py's score_processor.
    Never raises — on a timeout or an unhandled Gemini error at any step,
    returns agent_status="timeout" or "error" with whatever was built so
    far; the caller (scripts/run_pipeline.py's --stage agents) falls back
    to checks_only scoring in that case, never a partial/guessed agent
    adjustment.

    thinking_level is forwarded, unmodified, to every Gemini call in this
    loop — None (the default) sends no thinking config at all. Only
    scripts/probe_agent_thinking.py passes "low"; normal pipeline runs
    never set this (docs/PROGRESS.md's T10 thinking-comparison decision)."""
    trail: list[dict] = []
    step_index = 0

    def _deadline_exceeded() -> bool:
        return time.monotonic() >= deadline

    try:
        context_pack = build_context_pack(processor_context)
        context_json = json.dumps(context_pack, default=str)

        # Computed once, up front: the universe a finding may validly cite
        # (docs/PROGRESS.md — "verified", not merely "exists in this
        # processor's data"). Used both by ID-validation below and by
        # _classify_findings at the end.
        verified_shipment_ids = verified_inbound_shipment_ids(
            processor_context["shipments"], processor_context["duplicate_keys"]
        )

        # 1. Hypothesis — batch-level conclusions AND its own proposed findings.
        conclusions_response = llm_client.generate_structured(
            [HYPOTHESIS_PROMPT, context_json],
            ConclusionsResponse,
            purpose="agent_hypothesis",
            thinking_level=thinking_level,
        )
        trail.append(
            _trail_step(
                step_index,
                "hypothesis",
                input_summary=HYPOTHESIS_PROMPT[:200],
                output_json=conclusions_response.model_dump_json(),
            )
        )
        step_index += 1
        conclusions = _enforce_hard_check_floor(
            conclusions_response.conclusions, processor_context["check_results"]
        )
        # Same objection-direction + ID-validation filtering as any Critic
        # finding — never trusted from the model regardless of origin.
        # Re-indexed 0..N-1 here; this is the ONLY indexing the Critic's
        # verdicts and the Hypothesis's own later responses ever see.
        hypothesis_findings = [
            filtered
            for f in conclusions_response.findings
            if f.effect == "raises_concern"
            and (filtered := _filter_objection(f, processor_context, verified_shipment_ids))
            is not None
        ]

        if _deadline_exceeded():
            return _result(
                "timeout",
                conclusions=conclusions,
                hypothesis_findings=hypothesis_findings,
                trail=trail,
            )

        # 2. Critic phase 1: bounded tool-calling loop
        tool_context = {
            "check_results": processor_context["check_results"],
            "shipments": processor_context["shipments"],
            "site_assessment": processor_context.get("site_assessment"),
            "documents": processor_context["documents"],
        }
        tools = agent_tools.build_tools(
            tool_context, gcs_client=processor_context.get("gcs_client")
        )
        conclusions_only_json = json.dumps(
            [c.model_dump() for c in conclusions_response.conclusions], default=str
        )
        hypothesis_findings_json = json.dumps(
            [
                {"hypothesis_finding_index": i, **f.model_dump()}
                for i, f in enumerate(hypothesis_findings)
            ],
            default=str,
        )
        critic_seed = [
            CRITIC_TOOLS_PROMPT,
            context_json,
            f"Hypothesis conclusions:\n{conclusions_only_json}",
            f"Hypothesis's proposed findings:\n{hypothesis_findings_json}",
        ]
        conversation, tool_cap_reached = llm_client.run_tool_loop(
            contents=critic_seed,
            tools=tools,
            max_tool_calls=params.AGENT_MAX_TOOL_CALLS,
            purpose="agent_critic_tools",
            thinking_level=thinking_level,
        )
        for content in conversation[len(critic_seed) :]:
            parts = _get(content, "parts") or []
            function_call = next(
                (_get(p, "function_call") for p in parts if _get(p, "function_call")), None
            )
            if function_call is not None:
                trail.append(
                    _trail_step(
                        step_index,
                        "critic_tool_call",
                        tool_name=_get(function_call, "name"),
                        tool_args_json=json.dumps(_get(function_call, "args") or {}, default=str),
                    )
                )
            else:
                role = _get(content, "role")
                trail.append(
                    _trail_step(
                        step_index,
                        "critic_tool_result" if role == "user" else "critic_model_turn",
                        output_json=json.dumps(_summarize_content(content), default=str),
                    )
                )
            step_index += 1
        if tool_cap_reached:
            trail.append(
                _trail_step(
                    step_index,
                    "tool_cap_reached",
                    output_json=json.dumps({"tool_cap_reached": True}),
                )
            )
            step_index += 1

        if _deadline_exceeded():
            return _result(
                "timeout",
                conclusions=conclusions,
                hypothesis_findings=hypothesis_findings,
                trail=trail,
                tool_cap_reached=tool_cap_reached,
            )

        # 2b. Critic phase 2: final structured call, no tools — a verdict
        # on every Hypothesis finding, plus any new findings of its own.
        objections_response = llm_client.generate_structured(
            [*conversation, CRITIC_FINAL_PROMPT],
            ObjectionsResponse,
            purpose="agent_critic_final",
            thinking_level=thinking_level,
        )
        trail.append(
            _trail_step(
                step_index,
                "critic_final",
                input_summary=CRITIC_FINAL_PROMPT[:200],
                output_json=objections_response.model_dump_json(),
            )
        )
        step_index += 1

        # Objection-direction rule (docs/PROGRESS.md): only "raises_concern"
        # objections are candidate findings from here on (ID-validated,
        # revised, confirmed, scored/deducted). A "resolves_concern"
        # objection — the Critic correcting an over-harsh Hypothesis
        # conclusion — never becomes a finding; it already reached the
        # trail above, in objections_response's raw, unfiltered JSON.
        objections = [
            filtered
            for o in objections_response.objections
            if o.effect == "raises_concern"
            and (filtered := _filter_objection(o, processor_context, verified_shipment_ids))
            is not None
        ]
        # Verdicts on Hypothesis findings — index-validated the same way
        # as any other model-supplied ID. Silence (no verdict at all) is
        # NOT evidence of agreement: a Hypothesis finding only becomes
        # "agreed" if the Critic actively upholds it.
        verdicts = [
            v
            for v in objections_response.verdicts
            if 0 <= v.hypothesis_finding_index < len(hypothesis_findings)
        ]
        verdict_by_index = {v.hypothesis_finding_index: v for v in verdicts}
        upheld_indices = {i for i, v in verdict_by_index.items() if v.verdict == "upheld"}
        needs_hypothesis_response_indices = set(range(len(hypothesis_findings))) - upheld_indices

        if _deadline_exceeded():
            return _result(
                "timeout",
                conclusions=conclusions,
                hypothesis_findings=hypothesis_findings,
                verdicts=verdicts,
                objections=objections,
                trail=trail,
                tool_cap_reached=tool_cap_reached,
            )

        # 3. Hypothesis revision — at most one round, only if there's
        # something to revise: a new Critic finding, or one of the
        # Hypothesis's own findings that wasn't upheld.
        revisions: list = []
        hypothesis_finding_responses: list = []
        if objections or needs_hypothesis_response_indices:
            earlier_conclusions_json = conclusions_only_json
            disputed_payload = json.dumps(
                [
                    {
                        "hypothesis_finding_index": i,
                        "finding": hypothesis_findings[i].model_dump(),
                        "critic_reason": (
                            verdict_by_index[i].reason if i in verdict_by_index else None
                        ),
                    }
                    for i in sorted(needs_hypothesis_response_indices)
                ],
                default=str,
            )
            objections_json = json.dumps([o.model_dump() for o in objections], default=str)
            revisions_response = llm_client.generate_structured(
                [
                    REVISION_PROMPT,
                    f"Earlier conclusions:\n{earlier_conclusions_json}",
                    f"Your own findings the Critic disputed (or didn't address):\n"
                    f"{disputed_payload}",
                    f"New findings the Critic raised:\n{objections_json}",
                ],
                RevisionsResponse,
                purpose="agent_revision",
                thinking_level=thinking_level,
            )
            trail.append(
                _trail_step(
                    step_index,
                    "revision",
                    input_summary=REVISION_PROMPT[:200],
                    output_json=revisions_response.model_dump_json(),
                )
            )
            step_index += 1
            revisions = [
                r for r in revisions_response.revisions if 0 <= r.objection_index < len(objections)
            ]
            hypothesis_finding_responses = [
                r
                for r in revisions_response.hypothesis_finding_responses
                if r.hypothesis_finding_index in needs_hypothesis_response_indices
            ]

        # 4. Merge agreement outcomes from both origins.
        #
        # Critic-raised findings (objections): confirmed unless explicitly
        # rejected (silence = accepted — unchanged default; the Critic's
        # skepticism is the check here, and not using the one chance to
        # push back means the finding stands).
        rejected_indices = {r.objection_index for r in revisions if not r.accepted}
        agreed_critic_findings = [o for i, o in enumerate(objections) if i not in rejected_indices]
        rejected_critic_findings = [o for i, o in enumerate(objections) if i in rejected_indices]

        # Hypothesis's own findings: confirmed only if the Critic actively
        # upheld it (silence is NOT agreement here — see verdicts above).
        # A disputed-or-unaddressed finding only vanishes entirely if the
        # Hypothesis EXPLICITLY withdrew it; anything else (maintained, or
        # the Hypothesis itself never responded) stays a visible review
        # flag rather than being silently dropped or silently confirmed.
        withdrawn_indices = {
            r.hypothesis_finding_index
            for r in hypothesis_finding_responses
            if r.decision == "withdraw"
        }
        review_flag_indices = needs_hypothesis_response_indices - withdrawn_indices

        agreed_hypothesis_findings = [hypothesis_findings[i] for i in sorted(upheld_indices)]
        review_flag_hypothesis_findings = [
            hypothesis_findings[i] for i in sorted(review_flag_indices)
        ]
        withdrawn_findings = [hypothesis_findings[i] for i in sorted(withdrawn_indices)]

        confirmed_findings = agreed_hypothesis_findings + agreed_critic_findings
        review_flag_findings = review_flag_hypothesis_findings + rejected_critic_findings

        classified = classify_confirmed_findings(confirmed_findings, processor_context)
        deductible_findings = classified["deductible_findings"]
        systemic_findings = classified["systemic_findings"]
        no_evidence_findings = classified["no_evidence_findings"]
        concurs_with_check_findings = classified["concurs_with_check_findings"]
        excluded_shipment_ids = classified["excluded_shipment_ids"]

        return _result(
            "ok",
            conclusions=conclusions,
            hypothesis_findings=hypothesis_findings,
            verdicts=verdicts,
            objections=objections,
            revisions=revisions,
            hypothesis_finding_responses=hypothesis_finding_responses,
            confirmed_findings=confirmed_findings,
            review_flag_findings=review_flag_findings,
            withdrawn_findings=withdrawn_findings,
            deductible_findings=deductible_findings,
            systemic_findings=systemic_findings,
            no_evidence_findings=no_evidence_findings,
            concurs_with_check_findings=concurs_with_check_findings,
            excluded_shipment_ids=excluded_shipment_ids,
            trail=trail,
            tool_cap_reached=tool_cap_reached,
        )
    except Exception:
        logger.exception(
            "agent loop failed for processor_id=%s",
            processor_context.get("processor", {}).get("processor_id"),
        )
        return _result("error", trail=trail)
