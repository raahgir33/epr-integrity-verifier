"""Deterministic scoring. docs/DATA_SPEC.md §4a — the agent-finding
subtraction from verified inbound tonnes (T10, confirmed findings like F8)
is not implemented here; this is the checks-only part, which should
reproduce ground_truth.json's true_verifiable_t_checks_only exactly.
"""

import datetime

from app.checks.capacity import certified_t_fy_to_date, fy_start_month
from app.checks.mass_balance import verified_inbound_tonnes
from app.ingest import units
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
) -> dict:
    """processor: {processor_id, capacity_t_per_year, permitted_categories,
    consent_valid_from, consent_valid_to}. Returns the assessments-table
    row shape (minus seed/facts_source/stage/computed_at, added by the
    caller)."""
    certified_t = certified_t_fy_to_date(certificates, as_of_month)
    eligible_certified_t = _eligible_certified_t_fy_to_date(
        certificates, processor["permitted_categories"], as_of_month
    )
    verified_inbound_t = verified_inbound_tonnes(shipments, duplicate_keys)
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
