"""Tests for app/eval/evaluate.py — pure function, uses the committed
seed-42 ground_truth.json as a fixture. No network calls.
"""

import json
from pathlib import Path

import pytest

from app.eval.evaluate import (
    KEY_FIELDS_BY_DOC_TYPE,
    extraction_field_accuracy,
    extraction_field_mismatches,
    format_accuracy_pct,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH_PATH = REPO_ROOT / "data" / "synthetic" / "seed-42" / "ground_truth.json"


@pytest.fixture(scope="module")
def ground_truth_docs():
    data = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    return data["documents"]


def _perfect_rows(docs: list[dict]) -> list[dict]:
    rows = []
    for doc in docs:
        for field_name in KEY_FIELDS_BY_DOC_TYPE.get(doc["doc_type"], set()):
            if field_name in doc["fields"]:
                rows.append(
                    {
                        "doc_id": doc["doc_id"],
                        "field_name": field_name,
                        "printed_value": doc["fields"][field_name]["printed"],
                    }
                )
    return rows


def test_perfect_extraction_scores_100_percent(ground_truth_docs):
    rows = _perfect_rows(ground_truth_docs)
    report = extraction_field_accuracy(rows, ground_truth_docs)

    assert report["overall"]["accuracy"] == 1.0
    assert report["overall"]["total"] > 0


def test_wrong_values_reduce_accuracy(ground_truth_docs):
    rows = _perfect_rows(ground_truth_docs)
    for row in rows[:10]:
        row["printed_value"] = "DEFINITELY_WRONG"
    report = extraction_field_accuracy(rows, ground_truth_docs)

    assert report["overall"]["accuracy"] < 1.0
    assert report["overall"]["total"] == len(rows)
    assert report["overall"]["correct"] == len(rows) - 10


def test_missing_document_contributes_nothing():
    gt_docs = [
        {
            "doc_id": "D1",
            "doc_type": "cto",
            "fields": {"consent_no": {"printed": "CTO-1"}},
        }
    ]
    report = extraction_field_accuracy([], gt_docs)
    assert report["overall"] == {"correct": 0, "total": 0, "accuracy": None}


def test_unknown_doc_id_in_extracted_rows_is_ignored():
    gt_docs = [
        {
            "doc_id": "D1",
            "doc_type": "cto",
            "fields": {"consent_no": {"printed": "CTO-1"}},
        }
    ]
    rows = [{"doc_id": "NOT-IN-GROUND-TRUTH", "field_name": "consent_no", "printed_value": "X"}]
    report = extraction_field_accuracy(rows, gt_docs)
    assert report["overall"] == {"correct": 0, "total": 0, "accuracy": None}


def test_per_doc_type_breakdown_present_for_every_type(ground_truth_docs):
    rows = _perfect_rows(ground_truth_docs)
    report = extraction_field_accuracy(rows, ground_truth_docs)

    doc_types_in_ground_truth = {d["doc_type"] for d in ground_truth_docs}
    for doc_type in doc_types_in_ground_truth:
        assert doc_type in report, f"{doc_type} missing from report"
        assert report[doc_type]["accuracy"] == 1.0


def test_extraction_field_mismatches_empty_on_perfect_extraction(ground_truth_docs):
    rows = _perfect_rows(ground_truth_docs)
    assert extraction_field_mismatches(rows, ground_truth_docs) == []


def test_extraction_field_mismatches_lists_wrong_value_with_both_sides():
    gt_docs = [
        {
            "doc_id": "D1",
            "processor_id": "PWP-01",
            "doc_type": "weighbridge_slip",
            "fields": {"ticket_no": {"printed": "WB-001"}, "net_kg": {"printed": "1,000 kg"}},
        }
    ]
    rows = [
        {"doc_id": "D1", "field_name": "ticket_no", "printed_value": "WB-001"},
        {"doc_id": "D1", "field_name": "net_kg", "printed_value": "1,00O kg"},  # OCR-style typo
    ]
    mismatches = extraction_field_mismatches(rows, gt_docs)
    assert mismatches == [
        {
            "doc_id": "D1",
            "processor_id": "PWP-01",
            "doc_type": "weighbridge_slip",
            "field_name": "net_kg",
            "extracted_value": "1,00O kg",
            "truth_value": "1,000 kg",
        }
    ]


def test_extraction_field_mismatches_field_missing_entirely_has_none_extracted_value():
    gt_docs = [
        {
            "doc_id": "D1",
            "processor_id": "PWP-01",
            "doc_type": "cto",
            "fields": {
                "consent_no": {"printed": "CTO-1"},
                "capacity_t_per_year": {"printed": "500"},
            },
        }
    ]
    rows = [{"doc_id": "D1", "field_name": "consent_no", "printed_value": "CTO-1"}]
    mismatches = extraction_field_mismatches(rows, gt_docs)
    assert len(mismatches) == 1
    assert mismatches[0]["field_name"] == "capacity_t_per_year"
    assert mismatches[0]["extracted_value"] is None
    assert mismatches[0]["truth_value"] == "500"


def test_format_accuracy_pct_exact_match_is_100():
    assert format_accuracy_pct(5523, 5523) == "100.00%"


def test_format_accuracy_pct_truncates_never_rounds_up_to_100():
    # 5521/5523 = 99.9638...% -> must read 99.96%, matching the developer's
    # own hand-computed figure, not round to 100.00% at either decimal place.
    assert format_accuracy_pct(5521, 5523) == "99.96%"


def test_format_accuracy_pct_truncates_even_at_the_rounding_boundary():
    # 19999/20000 = 99.995% -- round-half-up would print "100.00%" despite
    # one field being wrong; truncation must not.
    result = format_accuracy_pct(19999, 20000)
    assert result != "100.00%"
    assert result == "99.99%"


def test_format_accuracy_pct_zero_total_is_na():
    assert format_accuracy_pct(0, 0) == "n/a"
