"""Deterministic scoring. docs/DATA_SPEC.md §4a. score_processor serves
both assessment stages: called with no excluded_shipment_ids it reproduces
ground_truth.json's true_verifiable_t_checks_only exactly ("checks_only"
stage); called with a confirmed agent finding's cited shipment IDs
(T10's "full" stage) it subtracts them from verified inbound tonnes too.
"""

import datetime
import re

from app.checks.capacity import certified_t_fy_to_date, fy_start_month
from app.checks.mass_balance import verified_inbound_tonnes
from app.ingest import units
from app.llm import LLMClient
from app.models.agent import NarrativeSummary
from app.models.checks import CheckResult

_RISK_BANDS = ["Low", "Medium", "High"]
_SOFT_SIGNAL_CHECK_IDS = {"C2b", "C7", "C8"}


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


def _month_bounds(month: str) -> tuple[datetime.date, datetime.date]:
    year, mon = (int(x) for x in month.split("-"))
    start = datetime.date(year, mon, 1)
    next_month = mon + 1 if mon < 12 else 1
    next_year = year if mon < 12 else year + 1
    end = datetime.date(next_year, next_month, 1) - datetime.timedelta(days=1)
    return start, end


def capacity_limit_t_with_consent(
    capacity_t_per_year: float,
    as_of_month: str,
    consent_valid_from: str,
    consent_valid_to: str,
) -> float:
    """docs/DATA_SPEC.md §4a.2: CTO capacity x months elapsed / 12, with a
    month's share of capacity set to 0 if that month falls entirely outside
    CTO validity (any overlap at all counts the month as valid — this
    dataset's consent windows always span the full FY, so the zeroing
    never actually triggers here; see docs/PROGRESS.md)."""
    valid_from = units.parse_date_ddmmyyyy(consent_valid_from)
    valid_to = units.parse_date_ddmmyyyy(consent_valid_to)
    monthly_capacity = capacity_t_per_year / 12.0

    total = 0.0
    for month in _fy_months_up_to(as_of_month):
        start, end = _month_bounds(month)
        if end < valid_from or start > valid_to:
            continue
        total += monthly_capacity
    return total


def risk_band(unverifiable_share: float) -> str:
    """docs/DATA_SPEC.md §4a.5: Low < 5%, Medium 5-25%, High > 25%."""
    if unverifiable_share < 0.05:
        return "Low"
    if unverifiable_share <= 0.25:
        return "Medium"
    return "High"


def apply_soft_signal_bump(band: str, check_results: list[CheckResult]) -> str:
    """At most one step, regardless of how many soft signals (C2b, C7, C8)
    failed."""
    any_failed_soft = any(
        r.check_id in _SOFT_SIGNAL_CHECK_IDS and r.status == "warn" for r in check_results
    )
    if not any_failed_soft:
        return band
    index = _RISK_BANDS.index(band)
    return _RISK_BANDS[min(index + 1, len(_RISK_BANDS) - 1)]


def _eligible_certified_t_fy_to_date(
    certificates: list[dict], permitted_categories: list[str], as_of_month: str
) -> float:
    """Certified tonnes, FY-to-date, excluding certificates in a category
    the CTO doesn't permit (F6/C6): that activity is out of consent no
    matter how well-backed physically, so it's excluded from the eligible
    basis feeding verifiable_t — not just flagged in the risk band."""
    fy_start = fy_start_month(as_of_month)
    return sum(
        c["quantity_t"]
        for c in certificates
        if fy_start <= c["period_month"] <= as_of_month and c["category"] in permitted_categories
    )


def score_processor(
    processor: dict,
    certificates: list[dict],
    shipments: list[dict],
    duplicate_keys: dict[str, dict],
    check_results: list[CheckResult],
    as_of_month: str,
    excluded_shipment_ids: frozenset[str] = frozenset(),
) -> dict:
    """processor: {processor_id, capacity_t_per_year, permitted_categories,
    consent_valid_from, consent_valid_to}. Returns the assessments-table
    row shape (minus seed/facts_source/stage/computed_at, added by the
    caller). excluded_shipment_ids defaults to empty (stage="checks_only");
    passing a confirmed agent finding's cited shipment IDs produces
    stage="full" figures — see app/agents/orchestrator.py."""
    certified_t = certified_t_fy_to_date(certificates, as_of_month)
    eligible_certified_t = _eligible_certified_t_fy_to_date(
        certificates, processor["permitted_categories"], as_of_month
    )
    verified_inbound_t = verified_inbound_tonnes(shipments, duplicate_keys, excluded_shipment_ids)
    capacity_limit_t = capacity_limit_t_with_consent(
        processor["capacity_t_per_year"],
        as_of_month,
        processor["consent_valid_from"],
        processor["consent_valid_to"],
    )

    verifiable_t = min(eligible_certified_t, verified_inbound_t, capacity_limit_t)
    unverifiable_t = certified_t - verifiable_t
    share = unverifiable_t / certified_t if certified_t > 0 else 0.0

    band = risk_band(share)
    band = apply_soft_signal_bump(band, check_results)

    return {
        "processor_id": processor["processor_id"],
        "certified_t": certified_t,
        "verified_inbound_t": verified_inbound_t,
        "capacity_limit_t": capacity_limit_t,
        "verifiable_t": verifiable_t,
        "unverifiable_t": unverifiable_t,
        "risk_band": band,
    }


_NARRATIVE_FIELDS = ("certified_t", "verified_inbound_t", "verifiable_t", "unverifiable_t")
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_NUMBER_TOLERANCE = 0.01


def _extract_numbers(text: str) -> list[float]:
    numbers = []
    for match in _NUMBER_RE.findall(text):
        cleaned = match.replace(",", "")
        if cleaned in ("", "-", "."):
            continue
        numbers.append(float(cleaned))
    return numbers


def _numbers_are_supported(text: str, score: dict) -> bool:
    """docs/ARCHITECTURE.md §4: "Gemini writes the plain-language summary
    from the computed numbers only." Enforced here, not trusted from the
    prompt — every number the model's narrative contains must match one of
    score's own computed figures."""
    allowed = {round(score[field], 2) for field in _NARRATIVE_FIELDS}
    return all(
        any(abs(n - a) <= _NUMBER_TOLERANCE for a in allowed) for n in _extract_numbers(text)
    )


def _template_narrative(score: dict) -> str:
    return (
        f"{score['verifiable_t']:.2f} t verifiable of {score['certified_t']:.2f} t certified "
        f"({score['unverifiable_t']:.2f} t unverifiable); risk band: {score['risk_band']}."
    )


def generate_narrative(score: dict, llm_client: LLMClient, purpose: str = "narrative") -> str:
    """One or two plain-language sentences summarising score's numbers for
    a non-technical reader. Falls back to a code-generated template
    sentence — never a hallucinated figure — if the model's narrative
    contains any number that isn't one of score's own computed values."""
    prompt = (
        "Write one or two plain-language sentences summarising this EPR "
        "certificate assessment for a non-technical reader. Use only the "
        "numbers given below exactly as given — do not compute, estimate "
        "or round them to a different number.\n"
        f"Processor: {score['processor_id']}\n"
        f"Certified tonnes (FY to date): {score['certified_t']:.2f} t\n"
        f"Verified inbound tonnes: {score['verified_inbound_t']:.2f} t\n"
        f"Verifiable tonnes: {score['verifiable_t']:.2f} t\n"
        f"Unverifiable tonnes: {score['unverifiable_t']:.2f} t\n"
        f"Risk band: {score['risk_band']}"
    )
    result = llm_client.generate_structured([prompt], NarrativeSummary, purpose=purpose)
    if _numbers_are_supported(result.summary, score):
        return result.summary
    return _template_narrative(score)
