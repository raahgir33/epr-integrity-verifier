"""Tests for scripts/run_pipeline.py's pure helpers. No network, no real
BigQuery/GCS/Gemini calls.
"""

from scripts.run_pipeline import _documents_from_extracted, _to_gcs_uri, _tokens_since


def test_documents_from_extracted_matches_truth_mode_shape():
    documents_rows = [
        {
            "doc_id": "D1",
            "processor_id": "PWP-02",
            "doc_type": "weighbridge_slip",
            "lang": "hi",
            "gcs_path": "seed-42/PWP-02/D1.png",
        }
    ]
    facts = {"D1": {"ticket_no": "WB-001", "remarks": "माल वापस भेजा"}}

    result = _documents_from_extracted(documents_rows, facts)

    assert result == [
        {
            "doc_id": "D1",
            "processor_id": "PWP-02",
            "doc_type": "weighbridge_slip",
            "lang": "hi",
            "gcs_path": _to_gcs_uri("seed-42/PWP-02/D1.png"),
            "fields": {"ticket_no": "WB-001", "remarks": "माल वापस भेजा"},
        }
    ]


def test_documents_from_extracted_doc_with_no_facts_gets_empty_fields():
    documents_rows = [
        {
            "doc_id": "D2",
            "processor_id": "PWP-01",
            "doc_type": "cto",
            "lang": "en",
            "gcs_path": "seed-42/PWP-01/D2.pdf",
        }
    ]
    result = _documents_from_extracted(documents_rows, facts={})
    assert result[0]["fields"] == {}


def test_documents_from_extracted_never_leaks_canonical_or_ground_truth_keys():
    # The only source of "fields" is the facts dict (Gemini's printed
    # output) — there's no code path here that could ever read a
    # "canonical" value or any ground-truth-only key, unlike
    # _documents_from_truth which has to deliberately strip them.
    documents_rows = [
        {
            "doc_id": "D1",
            "processor_id": "PWP-02",
            "doc_type": "weighbridge_slip",
            "lang": "hi",
            "gcs_path": "x",
        }
    ]
    facts = {"D1": {"remarks": "माल वापस भेजा"}}
    result = _documents_from_extracted(documents_rows, facts)
    assert set(result[0].keys()) == {
        "doc_id",
        "processor_id",
        "doc_type",
        "lang",
        "gcs_path",
        "fields",
    }


class _FakeClientWithCallLog:
    """Only exposes what _tokens_since needs — a non-destructive
    call_log snapshot, same shape app/llm.py's GeminiClient.call_log
    returns (list[dict] with purpose/success/input_tokens/output_tokens)."""

    def __init__(self, records):
        self.call_log = records


def test_tokens_since_sums_successful_calls_only():
    client = _FakeClientWithCallLog(
        [
            {"success": True, "input_tokens": 100, "output_tokens": 50},
            {"success": False, "input_tokens": 9999, "output_tokens": 9999},
            {"success": True, "input_tokens": 200, "output_tokens": 80},
        ]
    )
    assert _tokens_since(client, 0) == (300, 130)


def test_tokens_since_slices_from_start_index():
    client = _FakeClientWithCallLog(
        [
            {"success": True, "input_tokens": 1000, "output_tokens": 1000},
            {"success": True, "input_tokens": 100, "output_tokens": 50},
        ]
    )
    assert _tokens_since(client, 1) == (100, 50)


def test_tokens_since_no_calls_returns_none_none():
    client = _FakeClientWithCallLog([])
    assert _tokens_since(client, 0) == (None, None)
