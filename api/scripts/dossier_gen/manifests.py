"""Writers for certificates.csv, processors.json, suppliers.json,
brands.json and demo_batches.json. See docs/DATA_SPEC.md §2-§3.
"""

import csv
import io

from scripts.dossier_gen.shipments import FY_MONTHS, Dossier
from scripts.dossier_gen.world import Brand, Processor, Supplier


def processors_to_json(processors: list[Processor]) -> list[dict]:
    return [
        {
            "processor_id": p.processor_id,
            "name": p.name,
            "type": p.type,
            "permitted_categories": p.permitted_categories,
            "capacity_t_per_year": p.capacity_t_per_year,
            "consent_no": p.consent_no,
            "consent_valid_from": p.consent_valid_from,
            "consent_valid_to": p.consent_valid_to,
            "registration_no": p.registration_no,
            "gstin": p.gstin,
            "address": p.address,
            "lat": p.lat,
            "lon": p.lon,
            "site_validated": p.site_validated,
            "issue_types": p.issue_types,
            "hard_negatives": p.hard_negatives,
        }
        for p in processors
    ]


def suppliers_to_json(suppliers: list[Supplier]) -> list[dict]:
    return [
        {
            "supplier_id": s.supplier_id,
            "name": s.name,
            "gstin": s.gstin,
            "pin_code": s.pin_code,
            "lat": s.lat,
            "lon": s.lon,
        }
        for s in suppliers
    ]


def brands_to_json(brands: list[Brand]) -> list[dict]:
    return [{"brand_id": b.brand_id, "name": b.name} for b in brands]


def build_certificates_csv(
    processors: list[Processor], dossiers: dict[str, Dossier], brands: list[Brand]
) -> str:
    """One row per certificate, across all processors, round-robin assigned
    to brands so each brand holds certificates from several processors."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "certificate_id",
            "processor_id",
            "brand_id",
            "category",
            "quantity_t",
            "generation_date",
            "period_month",
        ]
    )
    i = 0
    for processor in processors:
        for cert in dossiers[processor.processor_id].certificates:
            brand = brands[i % len(brands)]
            writer.writerow(
                [
                    cert["certificate_id"],
                    processor.processor_id,
                    brand.brand_id,
                    cert["category"],
                    cert["quantity_t"],
                    cert["generation_date"],
                    cert["period_month"],
                ]
            )
            i += 1
    return buf.getvalue()


def build_demo_batches(
    processors: list[Processor], ground_truth_by_id: dict[str, dict]
) -> list[dict]:
    """One scripted 'new certificate batch' per processor for the live demo
    (docs/DATA_SPEC.md §2). PWP-05 (F1 — already over its verifiable tonnes)
    gets a batch that visibly pushes it further past true_verifiable_t, so
    the live-demo alert has something to fire on.

    period_month is always FY_MONTHS[-1] ("2026-03") — the financial
    year's own last month, never a literal "next calendar month" ("2026-
    04" would be the FIRST month of a NEW financial year, since the FY
    runs April-March; app/checks/capacity.py's certified_t_fy_to_date
    windows strictly by fiscal year, so a batch dated into a new FY could
    never sum together with this processor's existing FY-to-date
    certified/verifiable figures — the live dashboard's headline numbers
    would never move). T13's live event path adds this batch's
    certificate directly into the SAME, already-reported fiscal year
    (found and fixed at the source during T13's implementation — see
    docs/PROGRESS.md).

    extra_document_ids is always empty here — every entry starts as a
    pure certificate-ledger bump (matching docs/ARCHITECTURE.md §3.2's
    original "no re-extraction needed" design). Exactly two entries
    (PWP-01, PWP-03) are patched afterward, in place, by
    scripts/generate_demo_extra_docs.py — which also overwrites their
    quantity_t to match the real new shipment's own invoice quantity, so
    the certificate and the shipment agree exactly, the same "honest
    basis" rule docs/DATA_SPEC.md §5 already applies to every normal
    clean-processor certificate."""
    batches = []
    for processor in processors:
        truth = ground_truth_by_id[processor.processor_id]
        pushes_over = processor.processor_id == "PWP-05"
        quantity_t = round(processor.capacity_t_per_year / 12 * (2.0 if pushes_over else 0.1), 2)
        batches.append(
            {
                "batch_id": f"BATCH-{processor.processor_id}-001",
                "processor_id": processor.processor_id,
                "period_month": FY_MONTHS[-1],
                "quantity_t": quantity_t,
                "pushes_over_verifiable": pushes_over,
                "pre_batch_certified_t": truth["certified_t"],
                "pre_batch_true_verifiable_t": truth["true_verifiable_t"],
                "extra_document_ids": [],
            }
        )
    return batches
