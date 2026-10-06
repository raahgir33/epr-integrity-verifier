"""Assembles ground_truth.json: per-processor true verifiable tonnes (per
docs/DATA_SPEC.md §4a), plus every document's printed+canonical fields and
the true shipments/outputs/energy_monthly tables — rich enough to drive
`run_pipeline.py --facts-source truth` (T7) without running extraction.
"""

from scripts.dossier_gen.shipments import Dossier
from scripts.dossier_gen.world import Processor

# C8 and C7 are the only soft checks this generator seeds (F5 -> C8, F7 -> C7).
# C2b (output plausibility) isn't seeded here. "At most one step in total"
# per DATA_SPEC §4a — multiple failed soft signals still only bump once.
_SOFT_ISSUE_TYPES = {"F5", "F7"}


def _risk_band(certified_t: float, true_verifiable_t: float, issue_types: list[str]) -> str:
    unverifiable_share = (
        0.0 if certified_t <= 0 else (certified_t - true_verifiable_t) / certified_t
    )
    if unverifiable_share > 0.25:
        band = "High"
    elif unverifiable_share > 0.05:
        band = "Medium"
    else:
        band = "Low"
    if _SOFT_ISSUE_TYPES & set(issue_types):
        band = {"Low": "Medium", "Medium": "High", "High": "High"}[band]
    return band


def _affected_certificate_ids(certificates: list[dict], shortfall: float) -> list[str]:
    if shortfall <= 0:
        return []
    affected = []
    accumulated = 0.0
    for cert in sorted(certificates, key=lambda c: c["period_month"], reverse=True):
        affected.append(cert["certificate_id"])
        accumulated += cert["quantity_t"]
        if accumulated >= shortfall:
            break
    return affected


def compute_processor_truth(processor: Processor, dossier: Dossier) -> dict:
    certified_t = round(sum(c["quantity_t"] for c in dossier.certificates), 2)

    # A certificate in a category the CTO doesn't permit (F6) isn't verifiable
    # no matter how well-backed it is physically — the activity itself is out
    # of consent. Excluded from the eligible basis, not just the risk band.
    non_permitted_t = round(
        sum(
            c["quantity_t"]
            for c in dossier.certificates
            if c["category"] not in processor.permitted_categories
        ),
        2,
    )
    eligible_certified_t = round(certified_t - non_permitted_t, 2)

    verified_checks_only = round(
        sum(s["weighbridge_net_t"] or 0 for s in dossier.shipments if s.get("verified")), 2
    )
    f8_tonnes = round(
        sum(
            s["weighbridge_net_t"] or 0
            for s in dossier.shipments
            if s.get("verified") and s.get("is_f8")
        ),
        2,
    )
    verified_full_system = round(verified_checks_only - f8_tonnes, 2)

    capacity_limit_t = processor.capacity_t_per_year

    true_verifiable_t_checks_only = round(
        min(eligible_certified_t, verified_checks_only, capacity_limit_t), 2
    )
    true_verifiable_t = round(min(eligible_certified_t, verified_full_system, capacity_limit_t), 2)

    shortfall = round(certified_t - true_verifiable_t, 2)
    affected_certificate_ids = _affected_certificate_ids(dossier.certificates, shortfall)

    label = "issues" if processor.issue_types else "clean"
    risk_band = _risk_band(certified_t, true_verifiable_t, processor.issue_types)

    return {
        "processor_id": processor.processor_id,
        "label": label,
        "issue_types": list(processor.issue_types),
        "hard_negatives": list(processor.hard_negatives),
        "certified_t": certified_t,
        "verified_inbound_t": verified_checks_only,
        "verified_inbound_t_full_system": verified_full_system,
        "capacity_limit_t": capacity_limit_t,
        "true_verifiable_t": true_verifiable_t,
        "true_verifiable_t_checks_only": true_verifiable_t_checks_only,
        "risk_band": risk_band,
        "affected_certificate_ids": affected_certificate_ids,
        "site": {
            "lat": processor.lat,
            "lon": processor.lon,
            "site_validated": processor.site_validated,
            "placement_note": processor.site_note,
        },
        "shipments": dossier.shipments,
        "outputs": dossier.outputs,
        "energy_monthly": dossier.energy_monthly,
        "certificates": dossier.certificates,
    }


def build_ground_truth(
    seed: int, processors: list[Processor], dossiers: dict[str, Dossier]
) -> dict:
    all_documents = []
    processor_entries = []
    for processor in processors:
        dossier = dossiers[processor.processor_id]
        processor_entries.append(compute_processor_truth(processor, dossier))
        all_documents.extend(dossier.documents)

    return {
        "seed": seed,
        "processors": processor_entries,
        "documents": all_documents,
    }
