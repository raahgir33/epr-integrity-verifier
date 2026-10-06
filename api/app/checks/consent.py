"""C6 — consent. docs/DATA_SPEC.md §4: processing dates within CTO
validity; certificate category within permitted categories.

Every consent window in this dataset spans the full financial year (see
scripts/dossier_gen/world.py), so the date-validity sub-rule is never
seeded to fail here — it is still implemented properly and covered by a
hand-crafted failing fixture, not exercised by the real seed-42 data
(the category sub-rule is what F6 actually seeds).
"""

from app.ingest import units
from app.models.checks import CheckResult


def certificate_passes_c6(
    certificate: dict,
    permitted_categories: list[str],
    consent_valid_from: str,
    consent_valid_to: str,
) -> bool:
    """certificate: {category, generation_date ("DD/MM/YYYY"), ...}.
    consent_valid_from/to: "DD/MM/YYYY", as printed on the CTO."""
    if certificate["category"] not in permitted_categories:
        return False
    generation_date = units.parse_date_ddmmyyyy(certificate["generation_date"])
    valid_from = units.parse_date_ddmmyyyy(consent_valid_from)
    valid_to = units.parse_date_ddmmyyyy(consent_valid_to)
    return valid_from <= generation_date <= valid_to


def check_c6(
    processor_id: str,
    certificates: list[dict],
    permitted_categories: list[str],
    consent_valid_from: str,
    consent_valid_to: str,
) -> CheckResult:
    if not certificates:
        return CheckResult(
            check_id="C6",
            status="not_evaluable",
            severity="hard",
            explanation=f"{processor_id} has no certificates to evaluate against consent.",
        )

    failed = [
        c
        for c in certificates
        if not certificate_passes_c6(c, permitted_categories, consent_valid_from, consent_valid_to)
    ]
    if not failed:
        return CheckResult(
            check_id="C6",
            status="pass",
            severity="hard",
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation=(
                f"All {len(certificates)} certificate(s) for {processor_id} are within "
                "consent validity and permitted categories."
            ),
        )

    affected_tonnes = sum(c["quantity_t"] for c in failed)
    return CheckResult(
        check_id="C6",
        status="fail",
        severity="hard",
        affected_tonnes=affected_tonnes,
        evidence_ids=[c["certificate_id"] for c in failed],
        explanation=(
            f"{len(failed)} certificate(s) for {processor_id} are outside consent "
            "validity or in a category the CTO does not permit."
        ),
    )
