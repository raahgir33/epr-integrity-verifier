"""Tests for app/ingest/normalize.py — pure functions, no network. The big
one (`test_extracted_matching_agrees_with_truth_for_every_processor`) feeds
match_shipments_from_extracted the committed seed-42 ground_truth.json's own
document fields, as if extraction were perfect, and checks it independently
derives the same matches the generator already knows are true — for all 10
processors, covering every seeded scenario (F2 unmatched, F3 shortfall, F4
duplicate, H2 long-haul timing).
"""

import json
from pathlib import Path

import pytest

from app.ingest.normalize import (
    energy_from_extracted,
    energy_from_truth,
    facts_by_doc_id,
    match_shipments_from_extracted,
    outputs_from_extracted,
    outputs_from_truth,
    shipments_from_truth,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH_PATH = REPO_ROOT / "data" / "synthetic" / "seed-42" / "ground_truth.json"
SEED = 42


@pytest.fixture(scope="module")
def ground_truth():
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def test_shipments_from_truth_reshapes_fields():
    truth_shipments = [
        {
            "shipment_id": "PWP-01-SHP-001",
            "month": "2025-04",
            "invoice_doc_id": "PWP-01-INV-001",
            "eway_doc_id": "PWP-01-EWAY-001",
            "weighbridge_doc_id": "PWP-01-WB-001",
            "invoice_qty_t": 10.5,
            "weighbridge_net_t": 10.48,
            "match_status": "matched",
            "ewb_no": "123",
            "vehicle_no": "MH12AB1234",
            "distance_km": 50.0,
            "is_f8": False,
            "verified": True,
        }
    ]
    rows = shipments_from_truth(SEED, "PWP-01", truth_shipments)
    assert rows == [
        {
            "seed": SEED,
            "facts_source": "truth",
            "shipment_id": "PWP-01-SHP-001",
            "processor_id": "PWP-01",
            "month": "2025-04",
            "invoice_doc_id": "PWP-01-INV-001",
            "eway_doc_id": "PWP-01-EWAY-001",
            "weighbridge_doc_id": "PWP-01-WB-001",
            "invoice_qty_t": 10.5,
            "weighbridge_net_t": 10.48,
            "match_status": "matched",
            "ewb_no": "123",
            "vehicle_no": "MH12AB1234",
            "distance_km": 50.0,
        }
    ]


def test_outputs_and_energy_from_truth():
    outputs = outputs_from_truth(
        SEED, "PWP-01", [{"doc_id": "D1", "month": "2025-04", "quantity_t": 5.0}]
    )
    assert outputs == [
        {
            "seed": SEED,
            "facts_source": "truth",
            "doc_id": "D1",
            "processor_id": "PWP-01",
            "month": "2025-04",
            "quantity_t": 5.0,
        }
    ]
    energy = energy_from_truth(SEED, "PWP-01", [{"doc_id": "D2", "month": "2025-04", "kwh": 100.0}])
    assert energy == [
        {
            "seed": SEED,
            "facts_source": "truth",
            "doc_id": "D2",
            "processor_id": "PWP-01",
            "month": "2025-04",
            "kwh": 100.0,
        }
    ]


def test_facts_by_doc_id_groups_rows():
    rows = [
        {"doc_id": "D1", "field_name": "invoice_no", "printed_value": "INV-1"},
        {"doc_id": "D1", "field_name": "quantity_t", "printed_value": "10.50"},
        {"doc_id": "D2", "field_name": "invoice_no", "printed_value": "INV-2"},
    ]
    result = facts_by_doc_id(rows)
    assert result == {
        "D1": {"invoice_no": "INV-1", "quantity_t": "10.50"},
        "D2": {"invoice_no": "INV-2"},
    }


def _ground_truth_facts_for_processor(ground_truth: dict, processor_id: str) -> dict[str, dict]:
    """Builds {doc_id: {field_name: printed_value}} as if extraction were
    perfect — printed_value taken directly from ground_truth.json."""
    facts: dict[str, dict] = {}
    for doc in ground_truth["documents"]:
        if doc["processor_id"] != processor_id:
            continue
        facts[doc["doc_id"]] = {name: f["printed"] for name, f in doc["fields"].items()}
    return facts


def _processor_documents(ground_truth: dict, processor_id: str) -> list[dict]:
    return [
        {"doc_id": d["doc_id"], "doc_type": d["doc_type"]}
        for d in ground_truth["documents"]
        if d["processor_id"] == processor_id
    ]


@pytest.mark.parametrize("processor_id", [f"PWP-{i:02d}" for i in range(1, 11)])
def test_extracted_matching_agrees_with_truth_for_every_processor(ground_truth, processor_id):
    processor_entry = next(
        p for p in ground_truth["processors"] if p["processor_id"] == processor_id
    )
    truth_rows = shipments_from_truth(SEED, processor_id, processor_entry["shipments"])
    truth_by_invoice = {r["invoice_doc_id"]: r for r in truth_rows}

    documents = _processor_documents(ground_truth, processor_id)
    facts = _ground_truth_facts_for_processor(ground_truth, processor_id)
    extracted_rows = match_shipments_from_extracted(SEED, processor_id, documents, facts)
    extracted_by_invoice = {r["invoice_doc_id"]: r for r in extracted_rows}

    assert set(extracted_by_invoice) == set(truth_by_invoice), (
        f"{processor_id}: invoice sets differ"
    )

    for invoice_doc_id, truth_row in truth_by_invoice.items():
        extracted_row = extracted_by_invoice[invoice_doc_id]
        assert extracted_row["match_status"] == truth_row["match_status"], (
            f"{processor_id}/{invoice_doc_id}: match_status differs "
            f"(truth={truth_row['match_status']!r}, extracted={extracted_row['match_status']!r})"
        )
        assert extracted_row["weighbridge_doc_id"] == truth_row["weighbridge_doc_id"], (
            f"{processor_id}/{invoice_doc_id}: weighbridge_doc_id differs"
        )
        assert extracted_row["month"] == truth_row["month"], (
            f"{processor_id}/{invoice_doc_id}: month differs"
        )
        if truth_row["invoice_qty_t"] is not None:
            assert extracted_row["invoice_qty_t"] == pytest.approx(truth_row["invoice_qty_t"]), (
                f"{processor_id}/{invoice_doc_id}: invoice_qty_t differs"
            )
        if truth_row["weighbridge_net_t"] is not None:
            assert extracted_row["weighbridge_net_t"] == pytest.approx(
                truth_row["weighbridge_net_t"]
            ), f"{processor_id}/{invoice_doc_id}: weighbridge_net_t differs"


@pytest.mark.parametrize("processor_id", [f"PWP-{i:02d}" for i in range(1, 11)])
def test_extracted_outputs_and_energy_agree_with_truth(ground_truth, processor_id):
    processor_entry = next(
        p for p in ground_truth["processors"] if p["processor_id"] == processor_id
    )
    documents = _processor_documents(ground_truth, processor_id)
    facts = _ground_truth_facts_for_processor(ground_truth, processor_id)

    truth_outputs = {
        o["doc_id"]: o for o in outputs_from_truth(SEED, processor_id, processor_entry["outputs"])
    }
    extracted_outputs = {
        o["doc_id"]: o for o in outputs_from_extracted(SEED, processor_id, documents, facts)
    }
    assert set(truth_outputs) == set(extracted_outputs)
    for doc_id, truth_row in truth_outputs.items():
        assert extracted_outputs[doc_id]["month"] == truth_row["month"]
        assert extracted_outputs[doc_id]["quantity_t"] == pytest.approx(truth_row["quantity_t"])

    truth_energy = {
        e["doc_id"]: e
        for e in energy_from_truth(SEED, processor_id, processor_entry["energy_monthly"])
    }
    extracted_energy = {
        e["doc_id"]: e for e in energy_from_extracted(SEED, processor_id, documents, facts)
    }
    assert set(truth_energy) == set(extracted_energy)
    for doc_id, truth_row in truth_energy.items():
        assert extracted_energy[doc_id]["month"] == truth_row["month"]
        assert extracted_energy[doc_id]["kwh"] == pytest.approx(truth_row["kwh"])
