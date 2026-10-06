"""C3a (transit speed) and C3b (e-way bill validity). docs/DATA_SPEC.md §4.

Both are per-shipment checks that need the e-way bill's generated_at and
the weighbridge slip's in_time (C3a also needs distance_km; C3b also needs
valid_until) — fields normalize.py only populates for matched shipments
with both documents present. A shipment missing what a check needs is
skipped by that check (not false-flagged), per the applicability principle
in docs/DATA_SPEC.md §4: "not_evaluable, never pass" extends here to the
shipment level, not just the processor/check-type level.

No straight-line-distance fallback for C3a when distance_km is missing
(docs/DATA_SPEC.md §4 names ROAD_FACTOR for this): never missing in this
dataset (the e-way bill always carries it), so not built — see
docs/PROGRESS.md.
"""

import datetime

from app.checks import params
from app.models.checks import CheckResult


def _parse(iso: str | None) -> datetime.datetime | None:
    if iso is None:
        return None
    return datetime.datetime.fromisoformat(iso)


def shipment_passes_c3a(shipment: dict) -> bool | None:
    """None when distance_km, eway_generated_at or weighbridge_in_time is
    missing — not evaluable for this shipment, not a pass or fail."""
    distance_km = shipment.get("distance_km")
    generated_at = _parse(shipment.get("eway_generated_at"))
    in_time = _parse(shipment.get("weighbridge_in_time"))
    if distance_km is None or generated_at is None or in_time is None:
        return None
    transit_hours = (in_time - generated_at).total_seconds() / 3600.0
    if transit_hours <= 0:
        return False
    avg_speed_kmph = distance_km / transit_hours
    return avg_speed_kmph <= params.MAX_AVG_SPEED_KMPH


def shipment_passes_c3b(shipment: dict) -> bool | None:
    """None when eway_valid_until or weighbridge_in_time is missing."""
    valid_until = _parse(shipment.get("eway_valid_until"))
    in_time = _parse(shipment.get("weighbridge_in_time"))
    if valid_until is None or in_time is None:
        return None
    return in_time <= valid_until


def _evidence_doc_ids(shipments: list[dict]) -> list[str]:
    doc_ids: list[str] = []
    for s in shipments:
        for doc_id in (s.get("invoice_doc_id"), s.get("eway_doc_id"), s.get("weighbridge_doc_id")):
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)
    return doc_ids


def _run_shipment_check(
    check_id: str,
    processor_id: str,
    shipments: list[dict],
    predicate,
    not_evaluable_reason: str,
    fail_reason: str,
    pass_reason: str,
) -> CheckResult:
    evaluated = [(s, predicate(s)) for s in shipments]
    evaluated = [(s, passed) for s, passed in evaluated if passed is not None]
    if not evaluated:
        return CheckResult(
            check_id=check_id,
            status="not_evaluable",
            severity="hard",
            explanation=not_evaluable_reason,
        )
    failed = [s for s, passed in evaluated if not passed]
    if not failed:
        return CheckResult(
            check_id=check_id,
            status="pass",
            severity="hard",
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation=(
                f"{pass_reason} ({len(evaluated)} shipment(s) evaluated for {processor_id})."
            ),
        )
    affected_tonnes = sum(s.get("weighbridge_net_t") or 0.0 for s in failed)
    return CheckResult(
        check_id=check_id,
        status="fail",
        severity="hard",
        affected_tonnes=affected_tonnes,
        evidence_ids=_evidence_doc_ids(failed),
        explanation=f"{len(failed)} shipment(s) for {processor_id} {fail_reason}.",
    )


def check_c3a(processor_id: str, shipments: list[dict]) -> CheckResult:
    return _run_shipment_check(
        "C3a",
        processor_id,
        shipments,
        shipment_passes_c3a,
        not_evaluable_reason=(
            "No shipment had both an e-way bill generation time and a weighbridge "
            "in-time, with a known distance, to evaluate transit speed."
        ),
        fail_reason=f"imply an average transit speed above {params.MAX_AVG_SPEED_KMPH} km/h",
        pass_reason=(
            f"All evaluable shipments transited at or below {params.MAX_AVG_SPEED_KMPH} km/h"
        ),
    )


def check_c3b(processor_id: str, shipments: list[dict]) -> CheckResult:
    return _run_shipment_check(
        "C3b",
        processor_id,
        shipments,
        shipment_passes_c3b,
        not_evaluable_reason=(
            "No shipment had both an e-way bill valid-until and a weighbridge "
            "in-time to evaluate e-way bill validity."
        ),
        fail_reason="arrived at the weighbridge after the e-way bill's valid-until",
        pass_reason="All evaluable shipments arrived within the e-way bill's valid-until",
    )
