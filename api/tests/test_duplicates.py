"""Tests for app/checks/duplicates.py (C5) — hand-crafted fixtures for the
attribution rule, plus a real-data check that the generator's weighbridge
ticket numbering scheme never collides across processors (seed-42,
scripts/dossier_gen is never imported — only ground_truth.json is read).
"""

import json
from pathlib import Path

from app.checks.duplicates import check_c5, find_duplicate_keys, shipment_passes_c5

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH_PATH = REPO_ROOT / "data" / "synthetic" / "seed-42" / "ground_truth.json"


def _shipment(**overrides) -> dict:
    base = {
        "shipment_id": "SHP-1",
        "invoice_doc_id": "INV-1",
        "eway_doc_id": "EWAY-1",
        "weighbridge_doc_id": "WB-1",
        "match_status": "matched",
        "ewb_no": "EWB-1",
        "invoice_no": "INV-NO-1",
        "supplier_gstin": "GSTIN-1",
        "weighbridge_ticket_no": "TICKET-1",
        "weighbridge_net_t": 10.0,
    }
    base.update(overrides)
    return base


def test_no_shared_keys_passes():
    shipments = [
        _shipment(shipment_id="SHP-1", ewb_no="EWB-1"),
        _shipment(
            shipment_id="SHP-2",
            ewb_no="EWB-2",
            invoice_no="INV-NO-2",
            weighbridge_ticket_no="TICKET-2",
        ),
    ]
    duplicate_keys = find_duplicate_keys(shipments)
    assert duplicate_keys == {}
    assert shipment_passes_c5("SHP-1", duplicate_keys)
    result = check_c5("PWP-01", shipments, duplicate_keys)
    assert result.status == "pass"
    assert result.affected_tonnes == 0.0


def test_mixed_matched_and_unmatched_flags_only_unmatched():
    """The F4 scenario: PWP-01's original shipment (matched) and PWP-10's
    copy (unmatched, no weighbridge slip) share an ewb_no and an
    (invoice_no, supplier_gstin) pair. Only PWP-10's side should fail."""
    original = _shipment(
        shipment_id="PWP-01-SHP-001",
        invoice_doc_id="PWP-01-INV",
        eway_doc_id="PWP-01-EWAY",
        weighbridge_doc_id="PWP-01-WB",
        match_status="matched",
        ewb_no="EWB-SHARED",
        invoice_no="INV-SHARED",
        supplier_gstin="GSTIN-SHARED",
        weighbridge_ticket_no="PWP-01-WB-0001",
    )
    duplicate = _shipment(
        shipment_id="PWP-10-SHP-DUP",
        invoice_doc_id="PWP-10-INV",
        eway_doc_id="PWP-10-EWAY",
        weighbridge_doc_id=None,
        match_status="unmatched",
        ewb_no="EWB-SHARED",
        invoice_no="INV-SHARED",
        supplier_gstin="GSTIN-SHARED",
        weighbridge_ticket_no=None,
        weighbridge_net_t=None,
    )
    duplicate_keys = find_duplicate_keys([original, duplicate])

    assert shipment_passes_c5("PWP-01-SHP-001", duplicate_keys)
    assert not shipment_passes_c5("PWP-10-SHP-DUP", duplicate_keys)
    assert set(duplicate_keys["PWP-10-SHP-DUP"]["keys"]) == {"ewb_no", "invoice_no+supplier_gstin"}

    result_clean = check_c5("PWP-01", [original], duplicate_keys)
    assert result_clean.status == "pass"

    result_flagged = check_c5("PWP-10", [duplicate], duplicate_keys)
    assert result_flagged.status == "fail"
    assert result_flagged.affected_tonnes == 0.0  # unmatched already contributes 0
    assert "PWP-01-INV" in result_flagged.evidence_ids


def test_all_matched_group_flags_everyone():
    """No evidence to single anyone out when every member of the group has
    its own weighbridge slip — a weighbridge ticket matched to two e-way
    bills is itself a C5 finding per docs/DATA_SPEC.md §4."""
    a = _shipment(shipment_id="SHP-A", weighbridge_ticket_no="TICKET-SHARED", ewb_no="EWB-A")
    b = _shipment(shipment_id="SHP-B", weighbridge_ticket_no="TICKET-SHARED", ewb_no="EWB-B")
    duplicate_keys = find_duplicate_keys([a, b])
    assert not shipment_passes_c5("SHP-A", duplicate_keys)
    assert not shipment_passes_c5("SHP-B", duplicate_keys)


def test_all_unmatched_group_flags_everyone():
    a = _shipment(
        shipment_id="SHP-A",
        ewb_no="EWB-SHARED",
        match_status="unmatched",
        weighbridge_doc_id=None,
        weighbridge_net_t=None,
    )
    b = _shipment(
        shipment_id="SHP-B",
        ewb_no="EWB-SHARED",
        match_status="unmatched",
        weighbridge_doc_id=None,
        weighbridge_net_t=None,
    )
    duplicate_keys = find_duplicate_keys([a, b])
    assert not shipment_passes_c5("SHP-A", duplicate_keys)
    assert not shipment_passes_c5("SHP-B", duplicate_keys)


def test_missing_key_fields_never_group():
    """Shipments with no ewb_no/ticket_no/invoice+gstin at all must never
    be grouped together just because they share None."""
    a = _shipment(
        shipment_id="SHP-A",
        ewb_no=None,
        invoice_no=None,
        supplier_gstin=None,
        weighbridge_ticket_no=None,
    )
    b = _shipment(
        shipment_id="SHP-B",
        ewb_no=None,
        invoice_no=None,
        supplier_gstin=None,
        weighbridge_ticket_no=None,
    )
    duplicate_keys = find_duplicate_keys([a, b])
    assert duplicate_keys == {}


def test_key_matching_is_case_and_whitespace_insensitive():
    a = _shipment(
        shipment_id="SHP-A",
        ewb_no=" ewb-shared ",
        match_status="unmatched",
        weighbridge_doc_id=None,
        weighbridge_net_t=None,
    )
    b = _shipment(
        shipment_id="SHP-B",
        ewb_no="EWB-SHARED",
        match_status="unmatched",
        weighbridge_doc_id=None,
        weighbridge_net_t=None,
    )
    duplicate_keys = find_duplicate_keys([a, b])
    assert not shipment_passes_c5("SHP-A", duplicate_keys)
    assert not shipment_passes_c5("SHP-B", duplicate_keys)


def test_seed_42_weighbridge_ticket_numbers_never_collide():
    """The generator prefixes every ticket number with its own processor_id
    (scripts/dossier_gen/shipments.py), so ticket_no alone is globally
    unique in this dataset — confirmed here against the committed
    ground_truth.json rather than assumed. Real-world weighbridge data
    would need a weighbridge-qualified key (see docs/PROGRESS.md) since two
    different physical weighbridges could reuse the same ticket numbering;
    this dataset's documents carry no such field to key on."""
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    ticket_nos = [
        doc["fields"]["ticket_no"]["canonical"]
        for doc in ground_truth["documents"]
        if doc["doc_type"] == "weighbridge_slip"
    ]
    assert len(ticket_nos) == len(set(ticket_nos)), "weighbridge ticket numbers collide"
