"""Runs every check for a processor, applying docs/DATA_SPEC.md §4's
applicability table (C2b and C7 are recycler-only; end-of-life processors
get not_evaluable, never pass). C8 (site) is T9 — not run here yet.

Every input here (shipments, outputs, energy_monthly, certificates) must
already be scoped to exactly one (seed, facts_source) before it reaches
this module — truth-mode and extracted-mode rows for the same shipment
must never be mixed, and run_checks_for_run's cross-processor C5 grouping
is only correct within one such scope. Scoping that is the caller's job
(scripts/run_pipeline.py's BigQuery reads, or a test fixture), not
runner.py's — these functions take already-scoped data in and return
CheckResult lists, no I/O.
"""

from app.checks.capacity import certified_t_fy_to_date, check_c1
from app.checks.consent import check_c6
from app.checks.consistency import check_c4
from app.checks.duplicates import check_c5, find_duplicate_keys
from app.checks.energy import check_c7
from app.checks.mass_balance import check_c2a, check_c2b, verified_inbound_tonnes
from app.checks.transport import check_c3a, check_c3b
from app.models.checks import CheckResult

RECYCLER = "recycler"


def _certified_t_by_month(certificates: list[dict]) -> dict[str, float]:
    by_month: dict[str, float] = {}
    for c in certificates:
        by_month[c["period_month"]] = by_month.get(c["period_month"], 0.0) + c["quantity_t"]
    return by_month


def run_checks_for_processor(
    processor: dict,
    shipments: list[dict],
    outputs: list[dict],
    energy_monthly: list[dict],
    certificates: list[dict],
    duplicate_keys: dict[str, dict],
    as_of_month: str,
) -> list[CheckResult]:
    """processor: {processor_id, type, capacity_t_per_year,
    permitted_categories, consent_valid_from, consent_valid_to} — from
    processors.json / the BigQuery processors table, not ground_truth.json
    (which carries the shipments/outputs/energy/certificates for this
    processor, but not its registry fields).
    """
    processor_id = processor["processor_id"]
    is_recycler = processor["type"] == RECYCLER

    certified_t = certified_t_fy_to_date(certificates, as_of_month)
    verified_inbound_t = verified_inbound_tonnes(shipments, duplicate_keys)

    results = [
        check_c1(processor_id, certificates, processor["capacity_t_per_year"], as_of_month),
        check_c2a(processor_id, certified_t, verified_inbound_t),
        check_c3a(processor_id, shipments),
        check_c3b(processor_id, shipments),
        check_c4(processor_id, shipments),
        check_c5(processor_id, shipments, duplicate_keys),
        check_c6(
            processor_id,
            certificates,
            processor["permitted_categories"],
            processor["consent_valid_from"],
            processor["consent_valid_to"],
        ),
    ]

    if is_recycler:
        output_t = sum(o["quantity_t"] for o in outputs)
        results.append(check_c2b(processor_id, output_t, verified_inbound_t))
        results.append(check_c7(processor_id, energy_monthly, _certified_t_by_month(certificates)))
    else:
        results.append(
            CheckResult(
                check_id="C2b",
                status="not_evaluable",
                severity="soft",
                explanation=f"{processor_id} is end-of-life: no recycled product to evaluate.",
            )
        )
        results.append(
            CheckResult(
                check_id="C7",
                status="not_evaluable",
                severity="soft",
                explanation=f"{processor_id} is end-of-life: kiln energy is not plastic-driven.",
            )
        )

    return results


def run_checks_for_run(
    processors: list[dict],
    shipments_by_processor: dict[str, list[dict]],
    outputs_by_processor: dict[str, list[dict]],
    energy_by_processor: dict[str, list[dict]],
    certificates_by_processor: dict[str, list[dict]],
    as_of_month: str,
) -> dict[str, list[CheckResult]]:
    """Computes C5's duplicate-key groups once, across every processor's
    shipments in shipments_by_processor, then runs every other check per
    processor. All five *_by_processor dicts must already be scoped to one
    (seed, facts_source)."""
    all_shipments = [s for rows in shipments_by_processor.values() for s in rows]
    duplicate_keys = find_duplicate_keys(all_shipments)

    return {
        processor["processor_id"]: run_checks_for_processor(
            processor,
            shipments_by_processor.get(processor["processor_id"], []),
            outputs_by_processor.get(processor["processor_id"], []),
            energy_by_processor.get(processor["processor_id"], []),
            certificates_by_processor.get(processor["processor_id"], []),
            duplicate_keys,
            as_of_month,
        )
        for processor in processors
    }
