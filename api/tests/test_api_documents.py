"""Tests for GET /processors/{id}/documents, /documents/{doc_id}/file and
/documents/{doc_id}/facts."""

from app.store import cache, gcs


def test_get_processor_documents_happy_path(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(
        cache,
        "get_documents_for_processor",
        lambda seed, pid: [
            {
                "doc_id": "PWP-01-INV-0001",
                "doc_type": "inbound_invoice",
                "lang": "en",
                "extraction_status": "ok",
            },
            {
                "doc_id": "PWP-01-WB-0001",
                "doc_type": "weighbridge_slip",
                "lang": "en",
                "extraction_status": "not_extracted",
            },
        ],
    )

    response = api_client.get("/processors/PWP-01/documents")

    assert response.status_code == 200
    body = response.json()
    assert len(body["documents"]) == 2
    assert body["documents"][1]["extraction_status"] == "not_extracted"


def test_get_processor_documents_404_unknown_processor(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: None)

    response = api_client.get("/processors/PWP-99/documents")

    assert response.status_code == 404


def test_get_document_file_streams_bytes_with_cache_headers(api_client, monkeypatch):
    monkeypatch.setattr(
        cache,
        "get_document",
        lambda seed, doc_id: {
            "doc_id": doc_id,
            "gcs_path": "seed-42/PWP-01/PWP-01-INV-0001.pdf",
            "mime_type": "application/pdf",
        },
    )
    monkeypatch.setattr(gcs, "get_client", lambda: object())
    monkeypatch.setattr(gcs, "download_bytes", lambda client, bucket, path: b"%PDF-fake-bytes")

    response = api_client.get("/documents/PWP-01-INV-0001/file")

    assert response.status_code == 200
    assert response.content == b"%PDF-fake-bytes"
    assert response.headers["content-type"] == "application/pdf"
    assert "immutable" in response.headers["cache-control"]


def test_get_document_file_404_unknown_doc_never_reads_gcs(api_client, monkeypatch):
    """doc_id is validated against the documents table BEFORE any GCS
    read (docs/BUILD_PLAN.md T11) — an unknown doc_id must 404 without
    ever calling gcs.download_bytes, not just happen not to crash."""
    monkeypatch.setattr(cache, "get_document", lambda seed, doc_id: None)
    monkeypatch.setattr(gcs, "get_client", lambda: object())

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("gcs.download_bytes must not be called for an unknown doc_id")

    monkeypatch.setattr(gcs, "download_bytes", _fail_if_called)

    response = api_client.get("/documents/PWP-01-INV-9999/file")

    assert response.status_code == 404


def test_get_document_facts_not_extracted(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_document", lambda seed, doc_id: {"doc_id": doc_id})
    monkeypatch.setattr(
        cache,
        "get_document_facts",
        lambda seed, doc_id: {
            "extraction_status": "not_extracted",
            "error_message": None,
            "fields": [],
        },
    )

    response = api_client.get("/documents/PWP-01-WB-0001/facts")

    assert response.status_code == 200
    body = response.json()
    assert body["extraction_status"] == "not_extracted"
    assert body["fields"] == []


def test_get_document_facts_ok(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_document", lambda seed, doc_id: {"doc_id": doc_id})
    monkeypatch.setattr(
        cache,
        "get_document_facts",
        lambda seed, doc_id: {
            "extraction_status": "ok",
            "error_message": None,
            "fields": [
                {
                    "field_name": "invoice_no",
                    "printed_value": "ALPHA/25-26/0001",
                    "confidence": 0.98,
                    "page": 1,
                }
            ],
        },
    )

    response = api_client.get("/documents/PWP-01-INV-0001/facts")

    assert response.status_code == 200
    assert response.json()["fields"][0]["field_name"] == "invoice_no"


def test_get_document_facts_404_unknown_doc(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_document", lambda seed, doc_id: None)

    response = api_client.get("/documents/PWP-01-INV-9999/facts")

    assert response.status_code == 404
