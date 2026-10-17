"""Tests for app/agents/tools.py — no LLM involved, real tool functions
called directly against hand-built processor context."""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.tools import _cap, _parse_gcs_uri, _resolve_gcs_path, build_tools

_CONTEXT = {
    "check_results": [
        {"check_id": "C1", "status": "pass", "severity": "hard", "explanation": "within capacity"},
    ],
    "shipments": [
        {"shipment_id": "SHP-1", "match_status": "matched", "invoice_qty_t": 10.0},
        {"shipment_id": "SHP-2", "match_status": "unmatched", "invoice_qty_t": 5.0},
    ],
    "site_assessment": {"status": "pass", "building_count": 73, "total_footprint_m2": 10435.3},
    "documents": [
        {
            "doc_id": "DOC-1",
            "doc_type": "inbound_invoice",
            "lang": "en",
            "gcs_path": "gs://my-bucket/seed-42/documents/PWP-01/DOC-1.pdf",
            "fields": {"invoice_no": "INV-001", "quantity_t": "10.50"},
        },
        {
            "doc_id": "DOC-2",
            "doc_type": "weighbridge_slip",
            "lang": "hi",
            "gcs_path": "gs://my-bucket/seed-42/documents/PWP-01/DOC-2.png",
            "fields": {"ticket_no": "PWP-01-WB-0001"},
        },
    ],
}


def _tools_by_name(gcs_client=None):
    return {fn.__name__: fn for fn in build_tools(_CONTEXT, gcs_client=gcs_client)}


def test_parse_gcs_uri():
    assert _parse_gcs_uri("gs://my-bucket/a/b/c.pdf") == ("my-bucket", "a/b/c.pdf")


def test_parse_gcs_uri_rejects_non_gs_uri():
    with pytest.raises(ValueError, match="not a gs"):
        _parse_gcs_uri("https://example.com/file.pdf")


def test_cap_truncates_long_output():
    big = {"items": ["x" * 100 for _ in range(100)]}
    capped = _cap(big)
    assert len(capped.encode("utf-8")) <= 2048 + len("...(truncated)")
    assert capped.endswith("...(truncated)")


def test_run_check_found():
    tools = _tools_by_name()
    summary, attachment = tools["run_check"]("C1")
    assert '"status": "pass"' in summary
    assert attachment is None


def test_run_check_not_found():
    tools = _tools_by_name()
    summary, attachment = tools["run_check"]("C99")
    assert "error" in summary
    assert attachment is None


def test_get_shipments_filters_to_known_ids_and_ignores_unknown():
    tools = _tools_by_name()
    summary, attachment = tools["get_shipments"](["SHP-1", "SHP-999"])
    assert "SHP-1" in summary
    assert "SHP-999" not in summary
    assert attachment is None


def test_get_document_facts_found():
    tools = _tools_by_name()
    summary, attachment = tools["get_document_facts"]("DOC-1")
    assert "INV-001" in summary
    assert "inbound_invoice" in summary
    assert attachment is None


def test_get_document_facts_not_found():
    tools = _tools_by_name()
    summary, attachment = tools["get_document_facts"]("DOC-999")
    assert "error" in summary
    assert attachment is None


def test_get_site_assessment_present():
    tools = _tools_by_name()
    summary, attachment = tools["get_site_assessment"]()
    assert "building_count" in summary
    assert attachment is None


def test_get_site_assessment_absent():
    tools = {fn.__name__: fn for fn in build_tools({**_CONTEXT, "site_assessment": None})}
    summary, attachment = tools["get_site_assessment"]()
    assert "error" in summary
    assert attachment is None


@patch("app.agents.tools.gcs.download_bytes")
def test_read_document_fetches_bytes_and_infers_pdf_mime_type(mock_download):
    mock_download.return_value = b"%PDF-1.4 fake"
    gcs_client = MagicMock()
    tools = _tools_by_name(gcs_client=gcs_client)

    summary, attachment = tools["read_document"]("DOC-1")

    assert attachment == (b"%PDF-1.4 fake", "application/pdf")
    mock_download.assert_called_once_with(
        gcs_client, "my-bucket", "seed-42/documents/PWP-01/DOC-1.pdf"
    )
    assert "document attached" in summary


@patch("app.agents.tools.gcs.download_bytes")
def test_read_document_infers_png_mime_type_for_weighbridge_slip(mock_download):
    mock_download.return_value = b"\x89PNG fake"
    tools = _tools_by_name(gcs_client=MagicMock())

    _summary, attachment = tools["read_document"]("DOC-2")

    assert attachment[1] == "image/png"


def test_read_document_not_found():
    tools = _tools_by_name()
    summary, attachment = tools["read_document"]("DOC-999")
    assert "error" in summary
    assert attachment is None


@patch("app.agents.tools.settings.dossier_bucket", "test-bucket")
@patch("app.agents.tools.gcs.download_bytes")
def test_read_document_resolves_a_bucket_relative_path(mock_download):
    """Every real documents row stores gcs_path bucket-relative
    (scripts/load_dossiers.py's document_gcs_path), which read_document
    used to reject outright — the live 2026-10-17 failure. The fixture
    above happens to use gs:// URIs, which is why no unit test caught it.
    dossier_bucket is patched because it is unset wherever there is no
    .env (CI), and read_document then takes its no-bucket branch."""
    mock_download.return_value = b"%PDF-1.4 fake"
    gcs_client = MagicMock()
    context = {
        **_CONTEXT,
        "documents": [
            {
                "doc_id": "DOC-REL",
                "doc_type": "electricity_bill",
                "lang": "en",
                "gcs_path": "seed-42/documents/PWP-03/PWP-03-ELECTRICITY_BILL-060.pdf",
                "fields": {},
            }
        ],
    }
    tools = {fn.__name__: fn for fn in build_tools(context, gcs_client=gcs_client)}

    summary, attachment = tools["read_document"]("DOC-REL")

    assert attachment == (b"%PDF-1.4 fake", "application/pdf")
    mock_download.assert_called_once_with(
        gcs_client,
        "test-bucket",
        "seed-42/documents/PWP-03/PWP-03-ELECTRICITY_BILL-060.pdf",
    )
    assert "document attached" in summary


@patch("app.agents.tools.settings.dossier_bucket", "test-bucket")
def test_resolve_gcs_path_prefers_an_explicit_gs_uri():
    assert _resolve_gcs_path("gs://other-bucket/a/b.pdf") == ("other-bucket", "a/b.pdf")
    assert _resolve_gcs_path("a/b.pdf") == ("test-bucket", "a/b.pdf")
