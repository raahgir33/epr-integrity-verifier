"""Unit tests for load_dossiers.py's pure transform functions, using the
committed seed-42 manifests as fixtures. No network calls — BigQuery/GCS
I/O itself is run live by the developer, not exercised here.
"""

import json
from pathlib import Path

import pytest

from scripts.load_dossiers import (
    brand_to_row,
    certificate_row_from_csv_row,
    document_gcs_path,
    document_mime_type,
    document_to_row,
    load_certificates_csv,
    parse_ddmmyyyy,
    processor_to_row,
    supplier_to_row,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = REPO_ROOT / "data" / "synthetic" / "seed-42"
SEED = 42


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def processors():
    return load_json(SEED_DIR / "processors.json")


@pytest.fixture(scope="module")
def suppliers():
    return load_json(SEED_DIR / "suppliers.json")


@pytest.fixture(scope="module")
def brands():
    return load_json(SEED_DIR / "brands.json")


@pytest.fixture(scope="module")
def ground_truth():
    return load_json(SEED_DIR / "ground_truth.json")


@pytest.fixture(scope="module")
def certificates():
    return load_certificates_csv(SEED_DIR / "certificates.csv")


def test_parse_ddmmyyyy():
    assert parse_ddmmyyyy("05/04/2025") == "2025-04-05"
    assert parse_ddmmyyyy("31/03/2026") == "2026-03-31"


def test_processor_to_row_shapes_every_processor(processors):
    for p in processors:
        row = processor_to_row(SEED, p)
        assert row["seed"] == SEED
        assert row["processor_id"] == p["processor_id"]
        assert row["consent_valid_from"] == parse_ddmmyyyy(p["consent_valid_from"])
        assert isinstance(row["issue_types"], list)
        assert isinstance(row["hard_negatives"], list)
    assert len(processors) == 10


def test_supplier_to_row(suppliers):
    row = supplier_to_row(SEED, suppliers[0])
    assert row["seed"] == SEED
    assert row["supplier_id"] == suppliers[0]["supplier_id"]
    assert len(suppliers) == 25


def test_brand_to_row(brands):
    row = brand_to_row(SEED, brands[0])
    assert row["seed"] == SEED
    assert row["brand_id"] == brands[0]["brand_id"]
    assert len(brands) == 3


def test_document_gcs_path_and_mime_type_by_doc_type(ground_truth):
    weighbridge_doc = next(
        d for d in ground_truth["documents"] if d["doc_type"] == "weighbridge_slip"
    )
    invoice_doc = next(d for d in ground_truth["documents"] if d["doc_type"] == "inbound_invoice")

    wb_path = document_gcs_path(SEED, weighbridge_doc)
    assert (
        wb_path
        == f"seed-42/documents/{weighbridge_doc['processor_id']}/{weighbridge_doc['doc_id']}.png"
    )
    assert document_mime_type(weighbridge_doc) == "image/png"

    inv_path = document_gcs_path(SEED, invoice_doc)
    assert (
        inv_path == f"seed-42/documents/{invoice_doc['processor_id']}/{invoice_doc['doc_id']}.pdf"
    )
    assert document_mime_type(invoice_doc) == "application/pdf"


def test_document_to_row_shapes_every_document(ground_truth):
    for doc in ground_truth["documents"]:
        row = document_to_row(SEED, doc)
        assert row["seed"] == SEED
        assert row["doc_id"] == doc["doc_id"]
        assert row["gcs_path"] == document_gcs_path(SEED, doc)
    assert len(ground_truth["documents"]) > 400


def test_certificate_row_from_csv_row_shapes_every_certificate(certificates):
    for row in certificates:
        bq_row = certificate_row_from_csv_row(SEED, row)
        assert bq_row["seed"] == SEED
        assert bq_row["certificate_id"] == row["certificate_id"]
        assert isinstance(bq_row["quantity_t"], float)
        assert bq_row["generation_date"] == parse_ddmmyyyy(row["generation_date"])
    assert len(certificates) == 120
