"""Hypothesis -> Critic (tools) -> revision orchestration
(docs/ARCHITECTURE.md §4). run_agent_loop is the single entry point and is
fully testable against a fake LLMClient (app/llm.py's Protocol) — nothing
in this module makes a network call itself.

processor_context: {
    "processor": {processor_id, capacity_t_per_year, permitted_categories,
        consent_valid_from, consent_valid_to},
    "certificates": [...], "shipments": [...], "duplicate_keys": {...},
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


def _build_monthly_table(
    processor: dict, certificates: list[dict], shipments: list[dict], duplicate_keys: dict
) -> list[dict]:
    """Per-period_month verified-inbound tonnes (that month's own actual)
    paired with C1's own basis — FY-to-date cumulative certified tonnes
    vs FY-to-date pro-rated capacity through that month — rather than a
    flat annual/12 monthly share compared against that month's own
    certified slice in isolation (docs/PROGRESS.md: the flat share didn't
    match what C1, the actual hard check, judges — a flat share could make
    an early, well-within-capacity month look worse than C1 itself would
    ever find it). verified_inbound_t reuses mass_balance.py's own C3-C5
    pass logic (filtered to that month's shipments), never a re-derivation
    of it — this is contextual, not the authoritative FY-to-date figure
    (that's app/agents/scorer.py's job, included separately in
    check_results)."""
    months = sorted(
        {c["period_month"] for c in certificates}
        | {s["month"] for s in shipments if s.get("month")}
    )
    table = []
    for month in months:
        month_shipments = [s for s in shipments if s.get("month") == month]
        verified_inbound_t = verified_inbound_tonnes(month_shipments, duplicate_keys)
        certified_fy_to_date = certified_t_fy_to_date(certificates, month)
        capacity_fy_to_date = capacity_limit_t(
            processor["capacity_t_per_year"], months_elapsed_in_fy(month)
        )
        table.append(
            {
                "month": month,
                "verified_inbound_t": round(verified_inbound_t, 2),
                "certified_t_fy_to_date": round(certified_fy_to_date, 2),
                "capacity_limit_t_fy_to_date": round(capacity_fy_to_date, 2),
            }
        )
    return table


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
        "monthly_table": _build_monthly_table(
            processor,
            processor_context["certificates"],
            processor_context["shipments"],
            processor_context["duplicate_keys"],
        ),
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


def _valid_shipment_ids(processor_context: dict) -> set[str]:
    return {s["shipment_id"] for s in processor_context["shipments"]}


def _filter_objection(objection: Objection, processor_context: dict) -> Objection | None:
    """Code-level ID validation (docs/ARCHITECTURE.md §4: "a finding
    without at least one valid evidence ID is discarded") — never trusted
    from the model. Returns None if no valid evidence survives filtering;
    an invented shipment ID is dropped from cited_shipment_ids without
    discarding the whole finding, since the evidence may still be real."""
    valid_evidence = _valid_evidence_ids(processor_context)
    evidence_ids = [e for e in objection.evidence_ids if e in valid_evidence]
    if not evidence_ids:
        return None
    cited_shipment_ids = [
        s for s in objection.cited_shipment_ids if s in _valid_shipment_ids(processor_context)
    ]
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
    objections=None,
    revisions=None,
    confirmed_findings=None,
    deductible_findings=None,
    systemic_findings=None,
    no_evidence_findings=None,
    excluded_shipment_ids=None,
    trail=None,
    tool_cap_reached=False,
) -> dict:
    return {
        "conclusions": conclusions or [],
        "objections": objections or [],
        "revisions": revisions or [],
        "confirmed_findings": confirmed_findings or [],
        "deductible_findings": deductible_findings or [],
        "systemic_findings": systemic_findings or [],
        "no_evidence_findings": no_evidence_findings or [],
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


def _classify_findings(
    confirmed_findings: list[Objection],
    verified_shipment_ids: frozenset[str],
    shipments_by_id: dict[str, dict],
    documents_by_id: dict[str, dict],
) -> tuple[list[Objection], list[Objection], list[Objection], frozenset[str]]:
    """Two guards against over-broad deduction, applied in order, per
    finding (docs/PROGRESS.md):

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

    Both app/agents/scorer.py's build_no_own_evidence_finding_check_result
    and build_systemic_finding_check_result turn their respective
    non-empty list into a soft-signal risk-band bump instead of a tonnage
    deduction. excluded_shipment_ids is the union of deductible findings'
    (full) cited_shipment_ids — computed once here, the single source of
    truth callers use for the actual deduction, rather than each caller
    re-deriving it.

    With zero verified shipments, "cites more than half of them" has no
    meaningful denominator — every evidenced finding is deductible in
    that case, same as before the systemic guard existed.
    """
    deductible: list[Objection] = []
    systemic: list[Objection] = []
    no_evidence: list[Objection] = []
    excluded_shipment_ids: set[str] = set()
    for finding in confirmed_findings:
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
    return deductible, systemic, no_evidence, frozenset(excluded_shipment_ids)


def run_agent_loop(
    processor_context: dict,
    llm_client: LLMClient,
    deadline: float,
    thinking_level: str | None = None,
) -> dict:
    """Returns {conclusions, objections, revisions, confirmed_findings,
    deductible_findings, systemic_findings, no_evidence_findings,
    excluded_shipment_ids, trail, tool_cap_reached, agent_status}.
    confirmed_findings is the full "raises_concern" list (for the UI/
    trail); deductible_findings/systemic_findings/no_evidence_findings
    partition it (see _classify_findings) and excluded_shipment_ids is
    the ready-made deduction set — the single thing callers need to pass
    to app/agents/scorer.py's score_processor. Never raises — on a
    timeout or an unhandled Gemini error at any step, returns
    agent_status="timeout" or "error" with whatever was built so far;
    the caller (scripts/run_pipeline.py's --stage agents) falls back to
    checks_only scoring in that case, never a partial/guessed agent
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

        # 1. Hypothesis
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

        if _deadline_exceeded():
            return _result("timeout", conclusions=conclusions, trail=trail)

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
        critic_seed = [
            CRITIC_TOOLS_PROMPT,
            context_json,
            f"Hypothesis conclusions:\n{conclusions_response.model_dump_json()}",
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
                "timeout", conclusions=conclusions, trail=trail, tool_cap_reached=tool_cap_reached
            )

        # 2b. Critic phase 2: final structured call, no tools
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
            and (filtered := _filter_objection(o, processor_context)) is not None
        ]

        if _deadline_exceeded():
            return _result(
                "timeout",
                conclusions=conclusions,
                objections=objections,
                trail=trail,
                tool_cap_reached=tool_cap_reached,
            )

        # 3. Hypothesis revision — at most one round, only if there's
        # something to revise.
        revisions = []
        if objections:
            earlier_conclusions_json = json.dumps(
                [c.model_dump() for c in conclusions], default=str
            )
            objections_json = json.dumps([o.model_dump() for o in objections], default=str)
            revisions_response = llm_client.generate_structured(
                [
                    REVISION_PROMPT,
                    f"Earlier conclusions:\n{earlier_conclusions_json}",
                    f"Objections:\n{objections_json}",
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

        # 4. Confirmed findings: an objection is confirmed unless a
        # revision explicitly rejected it. A failed hard check is never
        # overruled here either — confirmed_findings only ever subtracts
        # shipment tonnage (app/agents/scorer.py), it never touches a
        # check's own pass/fail status.
        rejected_indices = {r.objection_index for r in revisions if not r.accepted}
        confirmed_findings = [o for i, o in enumerate(objections) if i not in rejected_indices]

        verified_shipment_ids = verified_inbound_shipment_ids(
            processor_context["shipments"], processor_context["duplicate_keys"]
        )
        shipments_by_id = {s["shipment_id"]: s for s in processor_context["shipments"]}
        documents_by_id = {d["doc_id"]: d for d in processor_context["documents"]}
        deductible_findings, systemic_findings, no_evidence_findings, excluded_shipment_ids = (
            _classify_findings(
                confirmed_findings, verified_shipment_ids, shipments_by_id, documents_by_id
            )
        )

        return _result(
            "ok",
            conclusions=conclusions,
            objections=objections,
            revisions=revisions,
            confirmed_findings=confirmed_findings,
            deductible_findings=deductible_findings,
            systemic_findings=systemic_findings,
            no_evidence_findings=no_evidence_findings,
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
