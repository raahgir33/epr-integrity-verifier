"""Tests for app/ingest/extract.py using a fake LLMClient — no network
calls to Gemini or GCS (gcs.download_bytes is monkeypatched).
"""

from unittest.mock import patch

from pydantic import ValidationError

from app.ingest.extract import extract_all, extract_one, facts_to_field_rows
from app.ingest.schemas import FieldConfidence, InboundInvoiceFacts

_DOC = {
    "doc_id": "PWP-01-INV-001",
    "processor_id": "PWP-01",
    "doc_type": "inbound_invoice",
    "gcs_path": "seed-42/documents/PWP-01/PWP-01-INV-001.pdf",
}

_FACTS_KWARGS = dict(
    invoice_no="INV-001",
    date="05/04/2025",
    supplier_gstin="27AAA",
    buyer_gstin="27BBB",
    item_description="Post-consumer plastic waste",
    hsn="3915",
    quantity_t="10.50",
    rate="12.00",
    value="1,26,000.00",
)


class _FakeLLMClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def extract(self, data, mime_type, prompt, schema, purpose, thinking_level=None):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _facts(**overrides):
    kwargs = {**_FACTS_KWARGS, **overrides}
    return InboundInvoiceFacts(
        **kwargs,
        field_confidence=[FieldConfidence(field="invoice_no", confidence=0.95, page=1)],
    )


def _validation_error() -> ValidationError:
    try:
        InboundInvoiceFacts()  # missing all required fields
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError")


@patch("app.ingest.extract.gcs.download_bytes", return_value=b"fake-bytes")
def test_extract_one_success(_mock_download):
    client = _FakeLLMClient([_facts()])
    result = extract_one(client, object(), "bucket", _DOC)

    assert result["status"] == "ok"
    assert result["facts"].invoice_no == "INV-001"
    assert client.calls == 1


@patch("app.ingest.extract.gcs.download_bytes", return_value=b"fake-bytes")
def test_extract_one_retries_once_on_validation_error_then_succeeds(_mock_download):
    client = _FakeLLMClient([_validation_error(), _facts()])
    result = extract_one(client, object(), "bucket", _DOC)

    assert result["status"] == "ok"
    assert client.calls == 2


@patch("app.ingest.extract.gcs.download_bytes", return_value=b"fake-bytes")
def test_extract_one_fails_after_two_validation_errors(_mock_download):
    client = _FakeLLMClient([_validation_error(), _validation_error()])
    result = extract_one(client, object(), "bucket", _DOC)

    assert result["status"] == "failed"
    assert result["facts"] is None
    assert client.calls == 2


@patch("app.ingest.extract.gcs.download_bytes", return_value=b"fake-bytes")
def test_extract_one_does_not_retry_on_non_validation_error(_mock_download):
    client = _FakeLLMClient([RuntimeError("boom")])
    result = extract_one(client, object(), "bucket", _DOC)

    assert result["status"] == "failed"
    assert client.calls == 1


@patch("app.ingest.extract.gcs.download_bytes", return_value=b"fake-bytes")
def test_extract_all_processes_every_document(_mock_download):
    docs = [dict(_DOC, doc_id=f"D{i}") for i in range(6)]
    client = _FakeLLMClient([_facts() for _ in docs])
    results = extract_all(client, object(), "bucket", docs)

    assert len(results) == len(docs)
    assert all(r["status"] == "ok" for r in results)


def test_facts_to_field_rows_joins_confidence():
    facts = _facts()
    rows = facts_to_field_rows(facts)
    by_field = {r["field_name"]: r for r in rows}

    assert by_field["invoice_no"]["printed_value"] == "INV-001"
    assert by_field["invoice_no"]["confidence"] == 0.95
    assert by_field["invoice_no"]["page"] == 1
    # Fields with no self-reported confidence still appear, with None.
    assert by_field["hsn"]["confidence"] is None
