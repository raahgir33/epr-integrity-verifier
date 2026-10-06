"""C7 — energy. docs/DATA_SPEC.md §4: kWh per processed tonne within a
plausible band; months with processing but near-zero consumption flagged.
Recycler-only; applicability (not_evaluable for end-of-life processors) is
runner.py's job, not this module's.

Basis is certified tonnes that month, matching how the generator itself
ties a month's electricity use to that month's certified ratio (see
scripts/dossier_gen/shipments.py) — not raw matched-shipment inbound,
which can legitimately be lumpy month to month even for a clean processor.
A month with zero certified tonnage (H4: planned shutdown) is skipped, not
flagged, since there is nothing to divide by and no claim to question.
"""

from app.checks import params
from app.models.checks import CheckResult


def month_passes_c7(kwh: float, certified_t_month: float) -> bool | None:
    """None when certified_t_month is zero — not evaluable, not a pass."""
    if certified_t_month == 0:
        return None
    kwh_per_t = kwh / certified_t_month
    return params.KWH_PER_T_MIN <= kwh_per_t <= params.KWH_PER_T_MAX


def check_c7(
    processor_id: str, energy_monthly: list[dict], certified_t_by_month: dict[str, float]
) -> CheckResult:
    """energy_monthly: this processor's rows ({doc_id, month, kwh}).
    certified_t_by_month: {month: certified_t}, this processor's FY."""
    evaluated = []
    for e in energy_monthly:
        certified_t_month = certified_t_by_month.get(e["month"], 0.0)
        passed = month_passes_c7(e["kwh"], certified_t_month)
        if passed is not None:
            evaluated.append((e, passed))

    if not evaluated:
        return CheckResult(
            check_id="C7",
            status="not_evaluable",
            severity="soft",
            explanation=f"{processor_id} has no month with both energy use and certified tonnage.",
        )

    failed = [e for e, passed in evaluated if not passed]
    if not failed:
        return CheckResult(
            check_id="C7",
            status="pass",
            severity="soft",
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation=(
                f"All {len(evaluated)} evaluable month(s) for {processor_id} fall "
                f"within {params.KWH_PER_T_MIN}-{params.KWH_PER_T_MAX} kWh/t."
            ),
        )

    affected_tonnes = sum(certified_t_by_month.get(e["month"], 0.0) for e in failed)
    return CheckResult(
        check_id="C7",
        status="warn",
        severity="soft",
        affected_tonnes=affected_tonnes,
        evidence_ids=[e["doc_id"] for e in failed],
        explanation=(
            f"{len(failed)} month(s) for {processor_id} fall outside the "
            f"{params.KWH_PER_T_MIN}-{params.KWH_PER_T_MAX} kWh/t plausible band."
        ),
    )
