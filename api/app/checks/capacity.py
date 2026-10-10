"""C1 — capacity. docs/DATA_SPEC.md §4: FY-to-date certified tonnes ≤ CTO
capacity (t/yr) × months elapsed / 12. The EPR financial year runs
April-March (internal engineering notes §6).

months_elapsed comes from a run-level `as_of_month` ("YYYY-MM") passed in
by the caller — never derived from a single processor's own certificates,
so every processor in one run is judged against the same point in time.
scripts/run_pipeline.py defaults as_of_month to the max period_month seen
across all processors in the run; T13's live-demo batch will pass its own
batch month instead.
"""

from app.models.checks import CheckResult


def fy_start_month(as_of_month: str) -> str:
    """as_of_month "YYYY-MM" -> "YYYY-04", the April that starts the
    financial year containing it."""
    year, month = (int(x) for x in as_of_month.split("-"))
    fy_start_year = year if month >= 4 else year - 1
    return f"{fy_start_year}-04"


def months_elapsed_in_fy(as_of_month: str) -> int:
    """1 for April (the FY's first month) through 12 for March."""
    _, month = (int(x) for x in as_of_month.split("-"))
    return month - 3 if month >= 4 else month + 9


def certified_t_fy_to_date(certificates: list[dict], as_of_month: str) -> float:
    """certificates: this processor's rows ({period_month, quantity_t}).
    "YYYY-MM" strings sort correctly lexicographically, including across
    the FY's calendar-year boundary (e.g. "2025-12" < "2026-01")."""
    fy_start = fy_start_month(as_of_month)
    return sum(
        c["quantity_t"] for c in certificates if fy_start <= c["period_month"] <= as_of_month
    )


def capacity_limit_t(capacity_t_per_year: float, months_elapsed: int) -> float:
    return capacity_t_per_year * months_elapsed / 12.0


def check_c1(
    processor_id: str, certificates: list[dict], capacity_t_per_year: float, as_of_month: str
) -> CheckResult:
    months_elapsed = months_elapsed_in_fy(as_of_month)
    certified_t = certified_t_fy_to_date(certificates, as_of_month)
    limit_t = capacity_limit_t(capacity_t_per_year, months_elapsed)

    if certified_t <= limit_t:
        return CheckResult(
            check_id="C1",
            status="pass",
            severity="hard",
            measured=certified_t,
            threshold=limit_t,
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation=(
                f"{processor_id}: FY-to-date certified tonnes ({certified_t:.2f} t) do "
                f"not exceed CTO capacity to date ({limit_t:.2f} t, {months_elapsed} "
                "month(s) elapsed)."
            ),
        )
    excess = certified_t - limit_t
    return CheckResult(
        check_id="C1",
        status="fail",
        severity="hard",
        measured=certified_t,
        threshold=limit_t,
        affected_tonnes=excess,
        evidence_ids=[],
        explanation=(
            f"{processor_id}: FY-to-date certified tonnes ({certified_t:.2f} t) exceed "
            f"CTO capacity to date ({limit_t:.2f} t, {months_elapsed} month(s) elapsed) "
            f"by {excess:.2f} t."
        ),
    )
