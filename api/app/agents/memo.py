"""Clarification memo / verification statement generation (docs/
ARCHITECTURE.md's generative-deliverable feature). Turns a processor's
assessment into a document a brand compliance team would actually send:
a neutral clarification request to a flagged processor, or a verification
statement & improvement roadmap for a clean one. Every processor resolves
to exactly one of the two documents (decide_doc_type below).

Pure logic, no I/O — build_memo_context takes already-fetched plain data
(the same "caller builds inputs, this module reasons over them" split
app/agents/orchestrator.py uses), and the two generate_* functions take an
LLMClient (app/llm.py's Protocol), so this is fully testable against a
fake client. scripts/run_pipeline.py's --stage memo does the actual
BigQuery fetching and glue.

Every number and evidence ID in a generated document is code-supplied and
code-checked (internal engineering notes §2.6: the model never does arithmetic that
matters) — Gemini only writes connective prose, under four guards:

1. Evidence-ID subset guard: every item/observation's evidence_ids is
   filtered to a code-supplied allow-list; an item left with none is
   dropped (and an emptied document is itself a guard failure).
2. Number guard: every number in the model's free text must match a
   code-supplied allow-list, after first stripping every known
   identifier (evidence/shipment IDs, consent/registration numbers) from
   the text — otherwise the digits inside an ID like
   "PWP-08-INBOUND_INVOICE-024" or an HSN code like "3915" would be
   mis-flagged as unsupported numbers on every single memo (found during
   planning review, before any code was written).
3. Forbidden-word guard: neutral-tone words (fraud/fake/illegal/
   criminal/violation/scam, English and Hindi) must not appear.
4. Leak guard: no F1-F9/H1-H5 taxonomy code and no internal classification
   label (deductible/systemic/concurs_with_check/etc.) — defense in
   depth, since the prompts never show the model these labels in the
   first place (see _memo_worthy_findings/_statement_context_payload).

Any guard failure triggers exactly one regenerate (a corrective note
naming what to fix), then a code-generated template document if the
second attempt still fails — never a partially-edited model output.
guard_status ("ok"/"regenerated"/"template_fallback") records which.

Hindi translation (generate_hindi_memo) is a second, separate call from
an already-guard-passed English document, checked only against that
document's own numbers/evidence (not the full processor allow-list) —
on any guard failure, no Hindi document is produced at all (English-only).
"""

import json
import re
from datetime import date
from typing import Literal

from app.agents.prompts import (
    MEMO_CLARIFICATION_PROMPT,
    MEMO_HINDI_PROMPT,
    MEMO_VERIFICATION_STATEMENT_PROMPT,
)
from app.checks import params
from app.checks.capacity import fy_start_month
from app.ingest import units
from app.llm import LLMClient
from app.models.agent import (
    ClarificationMemo,
    ImprovementObservation,
    MemoItem,
    VerificationStatement,
)

DocType = Literal["clarification_memo", "verification_statement"]
GuardStatus = Literal["ok", "regenerated", "template_fallback"]

# ---------- eligibility ----------

# A finding only becomes scoring-relevant once it's "confirmed" (docs/
# DATA_SPEC.md §4a's agreement rule); every classify_confirmed_findings
# bucket (deductible/systemic/no_own_evidence/concurs_with_check) plus
# review_flag all count as "this processor has a live finding" for memo
# eligibility — only withdrawn (trail-only, no scoring effect, no UI
# visibility beyond the raw trail) does not.
_NON_LIVE_CLASSIFICATIONS = {"withdrawn"}
# concurs_with_check restates what a deterministic check already caught
# (docs/DATA_SPEC.md §4a) — the check itself already earns an item in the
# memo (via its own fail/warn status), so showing the finding too would
# be a redundant item about the same thing.
_MEMO_EXCLUDED_CLASSIFICATIONS = {"withdrawn", "concurs_with_check"}


def _has_any_live_finding(findings: list[dict] | None) -> bool:
    if not findings:
        return False
    return any(f["classification"] not in _NON_LIVE_CLASSIFICATIONS for f in findings)


def decide_doc_type(
    assessment: dict, check_results: list[dict], findings: list[dict] | None
) -> DocType:
    """findings=None means no agent run exists yet for this processor
    (checks_only data only) — treated as "no live finding", never as a
    reason to assume anything. Every processor resolves to exactly one
    of the two document types; this inverts cleanly with no gap: a
    verification statement requires Low risk AND no failed hard check AND
    no live finding, which is exactly the negation of this condition."""
    has_failed_hard_check = any(
        c.get("severity") == "hard" and c.get("status") == "fail" for c in check_results
    )
    if (
        assessment["risk_band"] in ("Medium", "High")
        or has_failed_hard_check
        or _has_any_live_finding(findings)
    ):
        return "clarification_memo"
    return "verification_statement"


def _memo_worthy_findings(findings: list[dict] | None) -> list[dict]:
    return [
        f for f in (findings or []) if f["classification"] not in _MEMO_EXCLUDED_CLASSIFICATIONS
    ]


# ---------- Part B observation derivation (code only, measured data only) ----------


def _fy_months_up_to(as_of_month: str) -> list[str]:
    fy_start = fy_start_month(as_of_month)
    year, month = (int(x) for x in fy_start.split("-"))
    months = []
    current = f"{year:04d}-{month:02d}"
    while current <= as_of_month:
        months.append(current)
        month += 1
        if month > 12:
            month = 1
            year += 1
        current = f"{year:04d}-{month:02d}"
    return months


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def derive_improvement_observations(
    processor: dict,
    check_results: list[dict],
    as_of_month: str,
    shipments_by_id: dict[str, dict],
    documents_by_id: dict[str, dict],
    findings: list[dict] | None,
    certificates: list[dict],
) -> list[ImprovementObservation]:
    """Deliberately scoped for this build pass (see docs/PROGRESS.md):
    implements near-threshold passes, soft-warn checks, benign weighbridge
    remarks, consent/registration expiry, and months with no certificates.
    NOT implemented — would need extracted_facts confidence data threaded
    through memo_context, a real scope addition, not a small follow-on:
    low-confidence extracted fields and "missing optional fields" (the
    latter also has no defined meaning per doc type in docs/DATA_SPEC.md,
    so building it now would be inventing a requirement). recommendation
    is left "" here — the model fills it in (generate_verification_
    statement's _reconcile_statement), one sentence, no new fact/number."""
    observations: list[ImprovementObservation] = []

    for c in check_results:
        if c.get("severity") != "hard" or c.get("status") != "pass":
            continue
        measured, threshold = c.get("measured"), c.get("threshold")
        if measured is None or threshold is None or threshold <= 0:
            continue
        if (threshold - measured) / threshold <= params.IMPROVEMENT_NEAR_THRESHOLD_MARGIN:
            observations.append(
                ImprovementObservation(
                    kind="near_threshold",
                    measured=measured,
                    threshold=threshold,
                    evidence_ids=list(c.get("evidence_ids") or []),
                    recommendation="",
                )
            )

    for c in check_results:
        if c.get("severity") == "soft" and c.get("status") == "warn":
            observations.append(
                ImprovementObservation(
                    kind="soft_note",
                    measured=c.get("measured"),
                    threshold=c.get("threshold"),
                    evidence_ids=list(c.get("evidence_ids") or []),
                    recommendation="",
                )
            )

    cited_shipment_ids = {
        sid for f in (findings or []) for sid in (f.get("cited_shipment_ids") or [])
    }
    for shipment_id, shipment in shipments_by_id.items():
        if shipment_id in cited_shipment_ids:
            continue
        weighbridge_doc_id = shipment.get("weighbridge_doc_id")
        doc = documents_by_id.get(weighbridge_doc_id) if weighbridge_doc_id else None
        remarks = ((doc or {}).get("fields") or {}).get("remarks", "")
        if (remarks or "").strip():
            observations.append(
                ImprovementObservation(
                    kind="soft_note",
                    measured=None,
                    threshold=None,
                    evidence_ids=[weighbridge_doc_id] if weighbridge_doc_id else [],
                    recommendation="",
                )
            )

    consent_valid_to = processor.get("consent_valid_to")
    if consent_valid_to:
        expiry = units.parse_date_ddmmyyyy(consent_valid_to)
        year, month = (int(x) for x in as_of_month.split("-"))
        months_until_expiry = _months_between(date(year, month, 1), expiry)
        if months_until_expiry <= params.CONSENT_EXPIRY_WARNING_MONTHS:
            cto_doc_id = next(
                (doc_id for doc_id, doc in documents_by_id.items() if doc.get("doc_type") == "cto"),
                None,
            )
            observations.append(
                ImprovementObservation(
                    kind="consent_expiry",
                    measured=float(months_until_expiry),
                    threshold=float(params.CONSENT_EXPIRY_WARNING_MONTHS),
                    evidence_ids=[cto_doc_id] if cto_doc_id else [],
                    recommendation="",
                )
            )

    months_with_certs = {c["period_month"] for c in certificates}
    missing_months = [m for m in _fy_months_up_to(as_of_month) if m not in months_with_certs]
    if missing_months:
        observations.append(
            ImprovementObservation(
                kind="documentation_gap",
                measured=float(len(missing_months)),
                threshold=0.0,
                evidence_ids=[],
                recommendation="",
            )
        )

    return observations


# ---------- context assembly ----------


def _allowed_evidence_ids(check_results: list[dict], findings: list[dict]) -> frozenset[str]:
    ids = {eid for c in check_results for eid in (c.get("evidence_ids") or [])}
    for f in findings:
        ids.update(f.get("evidence_ids") or [])
    return frozenset(ids)


def _fy_label_numbers(as_of_month: str) -> set[float]:
    """Registers both the FY label's own digits ("FY 2025-26" -> 2025,
    26) and the negative form _extract_numbers' regex would actually pull
    from the hyphenated string itself (see its own docstring) — without
    this, a model-written "FY 2025-26" or "as of 2026-03" fails the number
    guard on every single memo regardless of content."""
    fy_start = fy_start_month(as_of_month)
    start_year = int(fy_start.split("-")[0])
    end_year_short = (start_year + 1) % 100
    year, month = (int(x) for x in as_of_month.split("-"))
    return {
        float(start_year),
        float(end_year_short),
        -float(end_year_short),
        float(year),
        float(month),
        -float(month),
    }


# HSN reference facts given to the agents (docs/DATA_SPEC.md §1, cited
# sources, not invented): 3915 = waste, parings and scrap of plastics;
# 3901 = polymers of ethylene in primary forms (virgin resin). Both are
# domain facts the Hypothesis/Critic prompts already cite — allowing a
# memo to repeat one isn't trusting the model's arithmetic, it's letting
# it restate a fact it was given (docs/PROGRESS.md 2026-10-09: PWP-05's
# real finding cited HSN 3901 to explain why "virgin LDPE granules"
# under HSN 3915 is a contradiction).
_HSN_REFERENCE_CODES = (3915.0, 3901.0)


def _relevant_months(
    as_of_month: str, certificates: list[dict], shipments_by_id: dict[str, dict]
) -> set[str]:
    months = {as_of_month}
    months.update(c.get("period_month") for c in certificates if c.get("period_month"))
    months.update(s.get("month") for s in shipments_by_id.values() if s.get("month"))
    return {m for m in months if m}


def _period_identifiers(
    as_of_month: str, certificates: list[dict], shipments_by_id: dict[str, dict]
) -> set[str]:
    """Period/date-label strings ("2025-07", the FY label "2025-26") are
    stripped as identifiers, never registered as allowed numbers — a
    month label isn't a quantity, and stripping it avoids _extract_
    numbers' hyphen-as-minus-sign ambiguity for this whole class of
    string entirely (a check explanation naming a DIFFERENT month than
    as_of_month, e.g. C7's own "(period 2025-07)", hit this in the
    first real-data run — docs/PROGRESS.md 2026-10-09 — the same
    ambiguity a prior fix only covered for as_of_month itself)."""
    months = _relevant_months(as_of_month, certificates, shipments_by_id)
    fy_start = fy_start_month(as_of_month)
    fy_start_year = fy_start.split("-")[0]
    fy_label = f"{fy_start_year}-{(int(fy_start_year) + 1) % 100:02d}"
    return months | {fy_label}


def _monthly_certified_t(certificates: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for c in certificates:
        month = c.get("period_month")
        if month:
            totals[month] = totals.get(month, 0.0) + (c.get("quantity_t") or 0.0)
    return totals


def _monthly_verified_inbound_t(shipments_by_id: dict[str, dict]) -> dict[str, float]:
    """Raw matched-shipment total per month — code-computed from raw
    shipment data, zero agent involvement, so it's trustworthy the same
    way a deterministic check's own measured/threshold is. Does not
    apply any finding's exclusion (see the deductible-finding loop in
    _allowed_numbers, which subtracts a specific month's excluded
    shipments on top of this)."""
    totals: dict[str, float] = {}
    for shipment in shipments_by_id.values():
        if shipment.get("match_status") != "matched":
            continue
        month = shipment.get("month")
        net_t = shipment.get("weighbridge_net_t")
        if month and net_t is not None:
            totals[month] = totals.get(month, 0.0) + net_t
    return totals


def _allowed_numbers(
    assessment: dict,
    check_results: list[dict],
    findings: list[dict],
    shipments_by_id: dict[str, dict],
    documents_by_id: dict[str, dict],
    certificates: list[dict],
    as_of_month: str,
    observations: list[ImprovementObservation],
    known_identifiers: frozenset[str],
) -> frozenset[float]:
    """known_identifiers is needed here because of the check-explanation
    scan below: every number literally present in a check_result's own
    `explanation` string is allowed, since that string is code-generated
    (app/checks/*.py) and already shown to the model verbatim. Agent
    FINDING explanations are deliberately NOT scanned the same way —
    that free text is Gemini's own unguarded prose from an earlier run,
    so blanket-trusting its numbers would be laundering un-vetted model
    arithmetic into the allow-list (docs/PROGRESS.md 2026-10-09: the
    first version of this fix did exactly that; tightened after review).
    What a finding's own numbers need is instead reconstructed here from
    data the finding could legitimately be referring to: monthly
    certified/verified-inbound totals and cited shipments' own tonnage —
    all code-computed, never read out of the finding's prose."""
    numbers: set[float] = set()
    for field in (
        "certified_t",
        "verified_inbound_t",
        "capacity_limit_t",
        "verifiable_t",
        "unverifiable_t",
    ):
        value = assessment.get(field)
        if value is not None:
            numbers.add(round(value, 2))
    for c in check_results:
        for field in ("measured", "threshold", "affected_tonnes"):
            value = c.get(field)
            if value is not None:
                numbers.add(round(value, 2))
        explanation = c.get("explanation")
        if explanation:
            stripped = _strip_known_identifiers(explanation, known_identifiers)
            numbers.update(_extract_numbers_with_sign_variants(stripped))

    cited_shipment_ids = {sid for f in findings for sid in (f.get("cited_shipment_ids") or [])}
    for sid in cited_shipment_ids:
        net_t = (shipments_by_id.get(sid) or {}).get("weighbridge_net_t")
        if net_t is not None:
            numbers.add(round(net_t, 2))

    monthly_certified = _monthly_certified_t(certificates)
    monthly_verified = _monthly_verified_inbound_t(shipments_by_id)
    numbers.update(round(v, 2) for v in monthly_certified.values())
    numbers.update(round(v, 2) for v in monthly_verified.values())
    # Dedup by shipment_id per month BEFORE summing — two separate
    # deductible findings can cite the SAME shipment (PWP-02's real data
    # did exactly this), and summing per-finding would double-subtract
    # it, landing on the wrong "after exclusion" total.
    deductible_shipment_ids_by_month: dict[str, set[str]] = {}
    for f in findings:
        if f.get("classification") != "deductible":
            continue
        for sid in f.get("cited_shipment_ids") or []:
            month = (shipments_by_id.get(sid) or {}).get("month")
            if month:
                deductible_shipment_ids_by_month.setdefault(month, set()).add(sid)
    for month, sids in deductible_shipment_ids_by_month.items():
        excluded = sum(
            (shipments_by_id.get(sid) or {}).get("weighbridge_net_t") or 0.0 for sid in sids
        )
        numbers.add(round(monthly_verified.get(month, 0.0) - excluded, 2))

    # Models naturally write dates as "Month YYYY" in prose (e.g. "August
    # 2025"), not the machine "YYYY-MM" form that's stripped as an
    # identifier above — the bare year itself is harmless to allow (not
    # a tonnage/compliance figure) and resolves that case without
    # weakening anything (docs/PROGRESS.md 2026-10-09).
    numbers.update(
        float(m.split("-")[0]) for m in _relevant_months(as_of_month, certificates, shipments_by_id)
    )

    numbers.update(_HSN_REFERENCE_CODES)
    numbers.add(float(params.MEMO_RESPONSE_DEADLINE_DAYS))
    for doc in documents_by_id.values():
        hsn = (doc.get("fields") or {}).get("hsn")
        if hsn:
            numbers.update(round(n, 2) for n in _extract_numbers(str(hsn)))
    for obs in observations:
        if obs.measured is not None:
            numbers.add(round(obs.measured, 2))
        if obs.threshold is not None:
            numbers.add(round(obs.threshold, 2))
    numbers.add(float(sum(1 for c in check_results if c.get("status") == "pass")))
    numbers.add(float(len(check_results)))
    numbers.add(float(len(documents_by_id)))
    numbers.add(float(len(shipments_by_id)))
    return frozenset(numbers)


def _known_identifiers(
    processor: dict,
    shipments_by_id: dict[str, dict],
    documents_by_id: dict[str, dict],
    allowed_evidence_ids: frozenset[str],
    as_of_month: str,
    certificates: list[dict],
) -> frozenset[str]:
    """Includes processor_id itself, not just document/shipment IDs and
    consent/registration numbers — found via test_memo.py: a processor
    name like "PWP-08 Recyclers Pvt. Ltd." contains digits ("08") that
    the number guard would otherwise mis-flag as an unsupported number
    every time the model (correctly) names the processor in prose.

    Also includes every evidence_id check_results/findings cite — not
    only doc_ids/shipment_ids — because a check's evidence can be a
    certificate_id ("EPR-CERT/617488/202504") or a site-thumbnail
    storage path ("seed-42/site/PWP-09.png"), neither a doc_id; both
    leaked digits into the number guard in the first real-data run
    (docs/PROGRESS.md 2026-10-09). And every period/date-label string
    (see _period_identifiers) — a month label isn't a quantity."""
    identifiers: set[str] = set(documents_by_id.keys()) | set(shipments_by_id.keys())
    identifiers |= set(allowed_evidence_ids)
    identifiers |= _period_identifiers(as_of_month, certificates, shipments_by_id)
    for key in ("processor_id", "consent_no", "registration_no"):
        value = processor.get(key)
        if value:
            identifiers.add(str(value))
    return frozenset(i for i in identifiers if i)


def build_memo_context(
    processor: dict,
    assessment: dict,
    check_results: list[dict],
    findings: list[dict] | None,
    shipments_by_id: dict[str, dict],
    documents_by_id: dict[str, dict],
    certificates: list[dict],
    as_of_month: str,
) -> dict:
    """processor: {processor_id, name, consent_no, registration_no,
    consent_valid_to, ...}. assessment: a StageAssessment-shaped dict
    (prefer "full" when an agent run exists, else "checks_only" —
    decided by the caller). findings: app/store/cache.py's get_findings
    shape ({finding_type, classification, effect, cited_shipment_ids,
    evidence_ids, explanation, ...}), or None if no agent run exists yet
    for this processor (decide_doc_type/derive_improvement_observations
    both treat that as "no live finding", never as a guess)."""
    doc_type = decide_doc_type(assessment, check_results, findings)
    observations = (
        derive_improvement_observations(
            processor,
            check_results,
            as_of_month,
            shipments_by_id,
            documents_by_id,
            findings,
            certificates,
        )
        if doc_type == "verification_statement"
        else []
    )
    relevant_findings = (
        _memo_worthy_findings(findings) if doc_type == "clarification_memo" else (findings or [])
    )
    allowed_evidence_ids = _allowed_evidence_ids(check_results, relevant_findings)
    known_identifiers = _known_identifiers(
        processor,
        shipments_by_id,
        documents_by_id,
        allowed_evidence_ids,
        as_of_month,
        certificates,
    )
    return {
        "processor": processor,
        "assessment": assessment,
        "check_results": check_results,
        "findings": findings,
        "shipments_by_id": shipments_by_id,
        "documents_by_id": documents_by_id,
        "certificates": certificates,
        "as_of_month": as_of_month,
        "doc_type": doc_type,
        "observations": observations,
        "documents_examined": len(documents_by_id),
        "allowed_evidence_ids": allowed_evidence_ids,
        "allowed_numbers": _allowed_numbers(
            assessment,
            check_results,
            relevant_findings,
            shipments_by_id,
            documents_by_id,
            certificates,
            as_of_month,
            observations,
            known_identifiers,
        ),
        "known_identifiers": known_identifiers,
    }


# ---------- guards ----------

_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_NUMBER_TOLERANCE = 0.01

_FORBIDDEN_WORDS_EN = ("fraud", "fraudulent", "fake", "illegal", "criminal", "violation", "scam")
# Drafted per the developer's request (2026-10-08) — standard Hindi
# equivalents, not frozen; swap any entry before the prompt freeze.
_FORBIDDEN_WORDS_HI = (
    "धोखाधड़ी",  # fraud / cheating
    "जालसाजी",  # forgery / fraud
    "नकली",  # fake
    "फर्जी",  # bogus / fake
    "अवैध",  # illegal
    "गैरकानूनी",  # unlawful
    "आपराधिक",  # criminal
    "अपराध",  # crime
    "उल्लंघन",  # violation
)

_TAXONOMY_CODE_RE = re.compile(r"\b[FH][1-9]\b")
_INTERNAL_LABELS = (
    "deductible",
    "systemic",
    "no_own_evidence",
    "no own evidence",
    "concurs_with_check",
    "concurs with check",
    "review_flag",
    "review flag",
    "AGENT_SYSTEMIC_FINDING",
    "AGENT_NO_OWN_EVIDENCE_FINDING",
    "AGENT_DISPUTED_FINDING",
)


def _strip_known_identifiers(text: str, known_identifiers: frozenset[str]) -> str:
    """Replaces each identifier with a space (not empty) so two numbers
    that happen to bracket an identifier in the sentence never merge into
    one. Longest-first so one identifier that's a substring of another
    (shouldn't happen with this dataset's ID shapes, but cheap to guard)
    can't partially shadow it."""
    for identifier in sorted(known_identifiers, key=len, reverse=True):
        if identifier:
            text = text.replace(identifier, " ")
    return text


def _extract_numbers(text: str) -> list[float]:
    numbers = []
    for match in _NUMBER_RE.findall(text):
        cleaned = match.replace(",", "")
        if cleaned in ("", "-", "."):
            continue
        numbers.append(float(cleaned))
    return numbers


def _extract_numbers_with_sign_variants(text: str) -> set[float]:
    """_extract_numbers' regex treats a hyphen directly between two
    numbers as a minus sign, so a genuine range like "150-1200 kWh/t"
    extracts as [150.0, -1200.0], not [150.0, 1200.0] (docs/PROGRESS.md
    2026-10-09: C7's own explanation hit exactly this). Only used when
    pulling numbers out of TRUSTED source text (a check's own
    explanation) for the allow-list — registering both signs here never
    loosens what the model's own output must match against, it only
    widens what's allowed to compensate for our own extraction's
    ambiguity on text we wrote ourselves."""
    numbers = {round(n, 2) for n in _extract_numbers(text)}
    return numbers | {-n for n in numbers}


def _unsupported_numbers(
    text: str, known_identifiers: frozenset[str], allowed_numbers: frozenset[float]
) -> list[float]:
    """The actual offending numbers, not just a bool — _numbers_ok below
    is this with an empty-check; diagnose_text_guards (for
    scripts/probe_memo_guards.py) needs the real values to report."""
    stripped = _strip_known_identifiers(text, known_identifiers)
    return [
        n
        for n in _extract_numbers(stripped)
        if not any(abs(n - a) <= _NUMBER_TOLERANCE for a in allowed_numbers)
    ]


def _numbers_ok(
    text: str, known_identifiers: frozenset[str], allowed_numbers: frozenset[float]
) -> bool:
    return not _unsupported_numbers(text, known_identifiers, allowed_numbers)


def _forbidden_word_hit(text: str) -> str | None:
    lowered = text.lower()
    for word in _FORBIDDEN_WORDS_EN:
        if word in lowered:
            return word
    for word in _FORBIDDEN_WORDS_HI:
        if word in text:
            return word
    return None


def _internal_label_hit(text: str) -> str | None:
    match = _TAXONOMY_CODE_RE.search(text)
    if match:
        return match.group(0)
    lowered = text.lower()
    for label in _INTERNAL_LABELS:
        if label.lower() in lowered:
            return label
    return None


def corrective_note(issues: list[dict]) -> str:
    """issues: diagnose_text_guards/diagnose_memo/diagnose_statement's
    structured output — the single source of truth for what went wrong,
    shared with the diagnostic path (scripts/probe_memo_guards.py)."""
    notes: dict[str, None] = {}
    guards_present = {issue["guard"] for issue in issues}
    if "empty" in guards_present:
        notes[
            "Every item must cite at least one of the evidence IDs given to you for that "
            "observation."
        ] = None
    if "number" in guards_present:
        notes[
            "Every number you write must already appear in the information provided above — "
            "do not invent, compute or restate any other number."
        ] = None
    for issue in issues:
        if issue["guard"] == "forbidden_word":
            notes[f"Do not use the word '{issue['offending']}' or its equivalents."] = None
        elif issue["guard"] == "internal_label":
            notes[
                f"Do not use the internal label or code '{issue['offending']}' — describe it "
                "in plain language instead."
            ] = None
    return " ".join(notes)


def diagnose_text_guards(
    field: str, text: str, known_identifiers: frozenset[str], allowed_numbers: frozenset[float]
) -> list[dict]:
    """One entry per guard that actually tripped on this field, with the
    real offending token(s), not just a category label — the single
    source of truth both corrective_note (what to tell the model on
    retry) and scripts/probe_memo_guards.py (what to show the developer
    when a real response falls back to template) read from."""
    issues: list[dict] = []
    unsupported = _unsupported_numbers(text, known_identifiers, allowed_numbers)
    if unsupported:
        issues.append({"field": field, "guard": "number", "offending": unsupported, "text": text})
    word_hit = _forbidden_word_hit(text)
    if word_hit:
        issues.append(
            {"field": field, "guard": "forbidden_word", "offending": word_hit, "text": text}
        )
    label_hit = _internal_label_hit(text)
    if label_hit:
        issues.append(
            {"field": field, "guard": "internal_label", "offending": label_hit, "text": text}
        )
    return issues


def diagnose_memo(
    memo: ClarificationMemo, known_identifiers: frozenset[str], allowed_numbers: frozenset[float]
) -> list[dict]:
    """Same field set _memo_guard_text_fields checks, labelled per
    field/item index so a diagnosis table can point at exactly which
    sentence tripped which guard."""
    issues = diagnose_text_guards(
        "opening_paragraph", memo.opening_paragraph, known_identifiers, allowed_numbers
    )
    issues += diagnose_text_guards(
        "closing_paragraph", memo.closing_paragraph, known_identifiers, allowed_numbers
    )
    for i, item in enumerate(memo.items):
        issues += diagnose_text_guards(
            f"items[{i}].what_we_observed",
            item.what_we_observed,
            known_identifiers,
            allowed_numbers,
        )
        issues += diagnose_text_guards(
            f"items[{i}].what_we_request", item.what_we_request, known_identifiers, allowed_numbers
        )
    if not memo.items:
        issues.append({"field": "items", "guard": "empty", "offending": None, "text": None})
    return issues


def diagnose_statement(
    statement: VerificationStatement,
    known_identifiers: frozenset[str],
    allowed_numbers: frozenset[float],
) -> list[dict]:
    issues = diagnose_text_guards(
        "part_a_paragraph", statement.part_a_paragraph, known_identifiers, allowed_numbers
    )
    issues += diagnose_text_guards(
        "closing_paragraph", statement.closing_paragraph, known_identifiers, allowed_numbers
    )
    for i, obs in enumerate(statement.observations):
        issues += diagnose_text_guards(
            f"observations[{i}].recommendation",
            obs.recommendation,
            known_identifiers,
            allowed_numbers,
        )
    return issues


# ---------- clarification memo ----------


def _filter_memo_items(
    items: list[MemoItem], allowed_evidence_ids: frozenset[str]
) -> list[MemoItem]:
    filtered = []
    for item in items:
        evidence_ids = [e for e in item.evidence_ids if e in allowed_evidence_ids]
        if not evidence_ids:
            continue
        filtered.append(item.model_copy(update={"evidence_ids": evidence_ids}))
    return filtered


def _cited_shipment_tonnes(finding: dict, shipments_by_id: dict[str, dict]) -> dict[str, float]:
    tonnes = {}
    for sid in finding.get("cited_shipment_ids") or []:
        net_t = (shipments_by_id.get(sid) or {}).get("weighbridge_net_t")
        if net_t is not None:
            tonnes[sid] = round(net_t, 2)
    return tonnes


def _memo_context_payload(memo_context: dict) -> dict:
    processor = memo_context["processor"]
    findings = _memo_worthy_findings(memo_context.get("findings"))
    shipments_by_id = memo_context["shipments_by_id"]
    return {
        "processor_name": processor.get("name"),
        "response_deadline_days": params.MEMO_RESPONSE_DEADLINE_DAYS,
        "failed_or_warned_checks": [
            {
                "check_id": c["check_id"],
                "explanation": c["explanation"],
                "measured": c.get("measured"),
                "threshold": c.get("threshold"),
                "evidence_ids": c.get("evidence_ids") or [],
            }
            for c in memo_context["check_results"]
            if c.get("status") in ("fail", "warn")
        ],
        "findings": [
            {
                "finding_type": f["finding_type"],
                "explanation": f["explanation"],
                "cited_shipment_tonnes_t": _cited_shipment_tonnes(f, shipments_by_id),
                "evidence_ids": f.get("evidence_ids") or [],
            }
            for f in findings
        ],
    }


def _template_clarification_memo(memo_context: dict) -> ClarificationMemo:
    processor_name = (
        memo_context["processor"].get("name") or memo_context["processor"]["processor_id"]
    )
    items = []
    for c in memo_context["check_results"]:
        if c.get("status") not in ("fail", "warn"):
            continue
        items.append(
            MemoItem(
                heading=f"Check {c['check_id']}",
                what_we_observed=(
                    f"Check {c['check_id']} did not pass for the period under review: "
                    f"measured {c.get('measured')} against a threshold of {c.get('threshold')}."
                ),
                evidence_ids=list(c.get("evidence_ids") or []),
                what_we_request="Please provide supporting documentation for this check.",
            )
        )
    for f in _memo_worthy_findings(memo_context.get("findings")):
        cited = f.get("cited_shipment_ids") or []
        items.append(
            MemoItem(
                heading=f["finding_type"],
                what_we_observed=f["explanation"],
                evidence_ids=list(f.get("evidence_ids") or []),
                what_we_request=(
                    f"Please provide supporting documents for shipment(s) {', '.join(cited)}."
                    if cited
                    else "Please provide supporting documents for this observation."
                ),
            )
        )
    if not items:
        items.append(
            MemoItem(
                heading="Assessment risk band",
                what_we_observed=(
                    f"This processor's assessment for the period under review shows a risk "
                    f"band of {memo_context['assessment']['risk_band']}."
                ),
                evidence_ids=[],
                what_we_request=(
                    "Please provide any supporting documentation you believe clarifies the "
                    "verified tonnage for this period."
                ),
            )
        )
    return ClarificationMemo(
        subject=f"Request for clarification — EPR certificates, {processor_name}",
        salutation="Dear Sir/Madam,",
        opening_paragraph=(
            "In the course of reviewing EPR certificates issued by this processor for the "
            "period under review, we identified items in the submitted documentation that we "
            "would like to request clarification on, along with supporting documents."
        ),
        items=items,
        response_deadline_days=params.MEMO_RESPONSE_DEADLINE_DAYS,
        closing_paragraph=(
            f"We request a response within {params.MEMO_RESPONSE_DEADLINE_DAYS} days of this "
            "letter."
        ),
    )


def attempt_clarification_memo(
    memo_context: dict, llm_client: LLMClient, corrective: str | None = None
) -> tuple[ClarificationMemo, list[dict]]:
    """One generation attempt — no regenerate/template-fallback logic.
    Returns the finalised candidate (evidence-filtered, deadline fixed
    to the real constant) and diagnose_memo's issues (empty = guard-
    clean). Exposed publicly so scripts/probe_memo_guards.py can inspect
    a real response's exact failure reasons using the same prompt-
    building generate_clarification_memo itself uses, not a second copy
    of it."""
    known_identifiers = memo_context["known_identifiers"]
    allowed_numbers = memo_context["allowed_numbers"]
    allowed_evidence_ids = memo_context["allowed_evidence_ids"]
    payload_json = json.dumps(_memo_context_payload(memo_context), default=str)
    prompt = MEMO_CLARIFICATION_PROMPT + payload_json
    if corrective:
        prompt += "\n\n" + corrective

    raw = llm_client.generate_structured([prompt], ClarificationMemo, purpose="agent_memo")
    candidate = raw.model_copy(
        update={
            "items": _filter_memo_items(raw.items, allowed_evidence_ids),
            "response_deadline_days": params.MEMO_RESPONSE_DEADLINE_DAYS,
        }
    )
    return candidate, diagnose_memo(candidate, known_identifiers, allowed_numbers)


def generate_clarification_memo(
    memo_context: dict, llm_client: LLMClient
) -> tuple[ClarificationMemo, GuardStatus]:
    candidate, issues = attempt_clarification_memo(memo_context, llm_client)
    if not issues:
        return candidate, "ok"

    candidate2, issues2 = attempt_clarification_memo(
        memo_context, llm_client, corrective=corrective_note(issues)
    )
    if not issues2:
        return candidate2, "regenerated"

    return _template_clarification_memo(memo_context), "template_fallback"


# ---------- verification statement ----------


def _template_recommendation(obs: ImprovementObservation) -> str:
    if obs.measured is not None and obs.threshold is not None:
        return (
            f"Measured value {obs.measured:.2f} is close to the threshold of "
            f"{obs.threshold:.2f} — consider reviewing supporting documentation for this item."
        )
    return "Consider reviewing supporting documentation for this item."


def _reconcile_statement(
    raw: VerificationStatement, code_observations: list[ImprovementObservation]
) -> VerificationStatement:
    """Never trusts the model's own kind/measured/threshold/evidence_ids
    for an observation — only its recommendation sentence, matched to
    code_observations by position. A model that returns the wrong count
    (or none) falls back to a per-observation template sentence for
    whichever index it didn't cover, not a guard failure for the whole
    document — recommendations are independent of each other."""
    model_recommendations = [o.recommendation for o in raw.observations]
    reconciled = [
        obs.model_copy(
            update={
                "recommendation": (
                    model_recommendations[i]
                    if i < len(model_recommendations)
                    else _template_recommendation(obs)
                )
            }
        )
        for i, obs in enumerate(code_observations)
    ]
    no_items_note = (
        None if reconciled else "No improvement items identified from the documents examined."
    )
    return raw.model_copy(update={"observations": reconciled, "no_items_note": no_items_note})


def _statement_context_payload(memo_context: dict) -> dict:
    processor = memo_context["processor"]
    assessment = memo_context["assessment"]
    check_results = memo_context["check_results"]
    checks_total = len(check_results)
    checks_passed = sum(1 for c in check_results if c.get("status") == "pass")
    findings = memo_context.get("findings")
    agent_review_note = (
        "two independent agents found no unresolved issues"
        if findings is not None
        else "no agent review has been completed yet for this processor"
    )
    observations = memo_context.get("observations") or []
    return {
        "processor_name": processor.get("name"),
        "certified_t": assessment["certified_t"],
        "verifiable_t": assessment["verifiable_t"],
        "documents_examined": memo_context.get("documents_examined"),
        "shipments_examined": len(memo_context.get("shipments_by_id") or {}),
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "agent_review_note": agent_review_note,
        "observations": [
            {
                "kind": o.kind,
                "measured": o.measured,
                "threshold": o.threshold,
                "evidence_ids": o.evidence_ids,
            }
            for o in observations
        ],
    }


def _template_verification_statement(memo_context: dict) -> VerificationStatement:
    processor_name = (
        memo_context["processor"].get("name") or memo_context["processor"]["processor_id"]
    )
    assessment = memo_context["assessment"]
    check_results = memo_context["check_results"]
    checks_total = len(check_results)
    checks_passed = sum(1 for c in check_results if c.get("status") == "pass")
    observations = memo_context.get("observations") or []
    reconciled = [
        obs.model_copy(update={"recommendation": _template_recommendation(obs)})
        for obs in observations
    ]
    return VerificationStatement(
        subject=f"Verification statement — {processor_name}",
        salutation="Dear Sir/Madam,",
        part_a_paragraph=(
            f"Of the {assessment['certified_t']:.2f} t certified by {processor_name} for the "
            f"period under review, {assessment['verifiable_t']:.2f} t were verified, with "
            f"{checks_passed} of {checks_total} checks passed."
        ),
        observations=reconciled,
        no_items_note=(
            None if reconciled else "No improvement items identified from the documents examined."
        ),
        closing_paragraph="No further action is required at this time.",
    )


def attempt_verification_statement(
    memo_context: dict, llm_client: LLMClient, corrective: str | None = None
) -> tuple[VerificationStatement, list[dict]]:
    """One generation attempt — see attempt_clarification_memo's
    docstring; same shape, exposed for the same reason."""
    known_identifiers = memo_context["known_identifiers"]
    allowed_numbers = memo_context["allowed_numbers"]
    code_observations = memo_context.get("observations") or []
    prompt = MEMO_VERIFICATION_STATEMENT_PROMPT + json.dumps(
        _statement_context_payload(memo_context), default=str
    )
    if corrective:
        prompt += "\n\n" + corrective

    raw = llm_client.generate_structured([prompt], VerificationStatement, purpose="agent_memo")
    candidate = _reconcile_statement(raw, code_observations)
    return candidate, diagnose_statement(candidate, known_identifiers, allowed_numbers)


def generate_verification_statement(
    memo_context: dict, llm_client: LLMClient
) -> tuple[VerificationStatement, GuardStatus]:
    candidate, issues = attempt_verification_statement(memo_context, llm_client)
    if not issues:
        return candidate, "ok"

    candidate2, issues2 = attempt_verification_statement(
        memo_context, llm_client, corrective=corrective_note(issues)
    )
    if not issues2:
        return candidate2, "regenerated"

    return _template_verification_statement(memo_context), "template_fallback"


# ---------- Hindi translation ----------

_CORRECTIVE_WESTERN_DIGITS_HI = (
    "Use Western digits (0123456789) for all numbers, not Devanagari numerals."
)

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_CORRECTIVE_UNTRANSLATED_HI = (
    "Your previous reply was not translated into Hindi — it was English text. "
    "Rewrite every field in Hindi (Devanagari script), not English."
)


def _is_untranslated(text: str) -> bool:
    """True when a "Hindi" field carries no Devanagari at all — the model
    echoed the English prompt content back instead of translating it.
    Found live: _hindi_matches_english only ever checked numbers and
    evidence IDs, so an untouched English field trivially passed (its own
    numbers always "match" themselves) and got stored as the Hindi memo —
    the web toggle then showed English text with only the lang="hi" font
    switched, never actual Hindi. Short fields with no prose (shouldn't
    occur in practice, since every paired field here is a generated
    sentence) would also fail this check, which is the conservative
    direction — reject and retry/fall back to English-only, never accept
    silently untranslated text."""
    return not _DEVANAGARI_RE.search(text)


def _hindi_field_pairs(
    doc_type: DocType,
    hindi_doc: ClarificationMemo | VerificationStatement,
    english_doc: ClarificationMemo | VerificationStatement,
) -> list[tuple[str, str]] | None:
    """None means a structural mismatch (wrong item/observation count, or
    an item/observation whose evidence_ids don't match its English
    counterpart exactly) — an automatic guard failure, never compared
    field by field in that case."""
    if doc_type == "clarification_memo":
        if hindi_doc.response_deadline_days != english_doc.response_deadline_days:
            return None
        if len(hindi_doc.items) != len(english_doc.items):
            return None
        pairs = [
            (hindi_doc.opening_paragraph, english_doc.opening_paragraph),
            (hindi_doc.closing_paragraph, english_doc.closing_paragraph),
        ]
        for hi_item, en_item in zip(hindi_doc.items, english_doc.items, strict=True):
            if set(hi_item.evidence_ids) != set(en_item.evidence_ids):
                return None
            pairs.append((hi_item.what_we_observed, en_item.what_we_observed))
            pairs.append((hi_item.what_we_request, en_item.what_we_request))
        return pairs

    if len(hindi_doc.observations) != len(english_doc.observations):
        return None
    pairs = [
        (hindi_doc.part_a_paragraph, english_doc.part_a_paragraph),
        (hindi_doc.closing_paragraph, english_doc.closing_paragraph),
    ]
    for hi_obs, en_obs in zip(hindi_doc.observations, english_doc.observations, strict=True):
        if set(hi_obs.evidence_ids) != set(en_obs.evidence_ids):
            return None
        pairs.append((hi_obs.recommendation, en_obs.recommendation))
    return pairs


def _hindi_known_identifiers(
    doc_type: DocType,
    hindi_doc: ClarificationMemo | VerificationStatement,
    english_doc: ClarificationMemo | VerificationStatement,
) -> frozenset[str]:
    ids: set[str] = set()
    if doc_type == "clarification_memo":
        for doc in (hindi_doc, english_doc):
            for item in doc.items:
                ids.update(item.evidence_ids)
    else:
        for doc in (hindi_doc, english_doc):
            for obs in doc.observations:
                ids.update(obs.evidence_ids)
    return frozenset(ids)


def _field_numbers_match(
    hindi_text: str, english_text: str, known_identifiers: frozenset[str]
) -> bool:
    """Every number in the Hindi field must match one already in the
    corresponding English field — not the full processor allow-list
    (docs/PROGRESS.md: Hindi must match English exactly). Devanagari
    numerals are normalised to ASCII first (app/ingest/units.py's
    normalize_digits, reused rather than reimplemented) — a code-level
    safety net, not a trust assumption that the model followed the
    Western-digits instruction."""
    hindi_clean = _strip_known_identifiers(units.normalize_digits(hindi_text), known_identifiers)
    english_clean = _strip_known_identifiers(english_text, known_identifiers)
    allowed = frozenset(round(n, 2) for n in _extract_numbers(english_clean))
    return all(
        any(abs(n - a) <= _NUMBER_TOLERANCE for a in allowed) for n in _extract_numbers(hindi_clean)
    )


def _hindi_matches_english(
    doc_type: DocType,
    hindi_doc: ClarificationMemo | VerificationStatement,
    english_doc: ClarificationMemo | VerificationStatement,
) -> bool:
    pairs = _hindi_field_pairs(doc_type, hindi_doc, english_doc)
    if pairs is None:
        return False
    if any(_is_untranslated(hi) for hi, _en in pairs):
        return False
    known_identifiers = _hindi_known_identifiers(doc_type, hindi_doc, english_doc)
    return all(_field_numbers_match(hi, en, known_identifiers) for hi, en in pairs)


def _hindi_corrective_for(
    doc_type: DocType,
    raw: ClarificationMemo | VerificationStatement,
    english_doc: ClarificationMemo | VerificationStatement,
) -> str:
    """Picks the retry's corrective note to match why the first attempt
    actually failed, instead of always sending the digit-format note
    regardless of cause — an untranslated (still-English) reply needs to
    be told to translate, not told about digit formatting."""
    pairs = _hindi_field_pairs(doc_type, raw, english_doc)
    if pairs is not None and any(_is_untranslated(hi) for hi, _en in pairs):
        return _CORRECTIVE_UNTRANSLATED_HI
    return _CORRECTIVE_WESTERN_DIGITS_HI


def generate_hindi_memo(
    doc_type: DocType,
    english_doc: ClarificationMemo | VerificationStatement,
    llm_client: LLMClient,
) -> tuple[ClarificationMemo | VerificationStatement | None, GuardStatus | None]:
    """Returns (None, None) on guard failure after the one retry — the
    caller writes no Hindi row at all in that case (docs/PROGRESS.md:
    "on any guard failure, show English only"), never a Hindi fallback
    template. Only called by the caller when the English document's own
    guard_status != "template_fallback"."""
    schema = ClarificationMemo if doc_type == "clarification_memo" else VerificationStatement
    english_json = english_doc.model_dump_json()

    def _prompt(corrective: str | None) -> str:
        base = MEMO_HINDI_PROMPT + english_json
        return base if corrective is None else base + "\n\n" + corrective

    raw = llm_client.generate_structured([_prompt(None)], schema, purpose="agent_memo_hi")
    if _hindi_matches_english(doc_type, raw, english_doc):
        return raw, "ok"

    corrective = _hindi_corrective_for(doc_type, raw, english_doc)
    raw2 = llm_client.generate_structured([_prompt(corrective)], schema, purpose="agent_memo_hi")
    if _hindi_matches_english(doc_type, raw2, english_doc):
        return raw2, "regenerated"

    return None, None
