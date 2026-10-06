"""Tests for app/eval/evaluate.py — pure function, uses the committed
seed-42 ground_truth.json as a fixture. No network calls.
"""

import json
from pathlib import Path

import pytest

from app.eval.evaluate import KEY_FIELDS_BY_DOC_TYPE, extraction_field_accuracy

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
