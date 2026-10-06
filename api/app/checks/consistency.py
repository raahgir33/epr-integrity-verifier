"""C4 — consistency. docs/DATA_SPEC.md §4: invoice qty vs e-way bill qty
within tolerance; weighbridge net vs invoice qty within tolerance; vehicle
no. and GSTINs match.

Only the weighbridge-net-vs-invoice-quantity sub-rule is implemented here.
It is the only sub-rule this dataset actually seeds a failure for (F3,
"weighbridge net materially below invoice quantity") and so the only one
with a real failing fixture to test against. The other two sub-rules are
structurally guaranteed by construction in this dataset, not separately
testable here:
- Invoice qty vs e-way bill qty: the generator always prints the same
  quantity_t on both documents (see scripts/dossier_gen/shipments.py) —
  there is no seeded scenario where they diverge.
- Vehicle number / GSTIN match: match_shipments_from_extracted (see
  app/ingest/normalize.py) requires vehicle-number agreement as part of
  matching an e-way bill to a weighbridge slip, and GSTIN agreement as
  part of matching an invoice to an e-way bill — a mismatch on either
  simply fails to produce a match, rather than producing a matched
  shipment with disagreeing fields for this check to catch.
This is a real gap for a future dataset that seeds either case, not a
silent omission — see docs/PROGRESS.md.
"""

from app.checks import params
from app.models.checks import CheckResult


def shipment_passes_c4(shipment: dict) -> bool | None:
    """None when unmatched (no weighbridge_net_t to compare against)."""
    invoice_qty_t = shipment.get("invoice_qty_t")
    weighbridge_net_t = shipment.get("weighbridge_net_t")
    if invoice_qty_t is None or weighbridge_net_t is None or invoice_qty_t == 0:
        return None
    relative_diff = abs(invoice_qty_t - weighbridge_net_t) / invoice_qty_t
    return relative_diff <= params.QTY_TOL_WEIGHBRIDGE


def _evidence_doc_ids(shipments: list[dict]) -> list[str]:
    doc_ids: list[str] = []
    for s in shipments:
        for doc_id in (s.get("invoice_doc_id"), s.get("eway_doc_id"), s.get("weighbridge_doc_id")):
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)
    return doc_ids


def check_c4(processor_id: str, shipments: list[dict]) -> CheckResult:
    evaluated = [(s, shipment_passes_c4(s)) for s in shipments]
    evaluated = [(s, passed) for s, passed in evaluated if passed is not None]
    if not evaluated:
        return CheckResult(
            check_id="C4",
            status="not_evaluable",
            severity="hard",
            explanation=(
                "No matched shipment had both an invoice quantity and a "
                "weighbridge net quantity to compare."
            ),
        )
    failed = [s for s, passed in evaluated if not passed]
    if not failed:
        return CheckResult(
            check_id="C4",
            status="pass",
            severity="hard",
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation=(
                f"All {len(evaluated)} evaluable shipment(s) for {processor_id} have "
                f"weighbridge net within {params.QTY_TOL_WEIGHBRIDGE:.0%} of invoice quantity."
            ),
        )
    affected_tonnes = sum(s.get("weighbridge_net_t") or 0.0 for s in failed)
    return CheckResult(
        check_id="C4",
        status="fail",
        severity="hard",
        affected_tonnes=affected_tonnes,
        evidence_ids=_evidence_doc_ids(failed),
        explanation=(
            f"{len(failed)} shipment(s) for {processor_id} have weighbridge net "
            f"more than {params.QTY_TOL_WEIGHBRIDGE:.0%} below invoice quantity."
        ),
    )
