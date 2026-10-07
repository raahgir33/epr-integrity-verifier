"""Tests for scripts/probe_agent_thinking.py's pure scoring functions —
no network, no real Gemini/BigQuery calls."""

from scripts.probe_agent_thinking import (
    _precision_recall_f1,
    compute_run_metrics,
    compute_run_to_run_agreement,
)


def test_precision_recall_f1_perfect_match():
    result = _precision_recall_f1({"SHP-1", "SHP-2"}, {"SHP-1", "SHP-2"})
    assert result == {"tp": 2, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_precision_recall_f1_false_positive_and_false_negative():
    result = _precision_recall_f1({"SHP-1", "SHP-3"}, {"SHP-1", "SHP-2"})
    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5


def test_precision_recall_f1_nothing_cited_and_nothing_true_is_perfect():
    result = _precision_recall_f1(set(), set())
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0


def _finding(cited_shipment_ids):
    return {"cited_shipment_ids": cited_shipment_ids}


def _run_record(pwp01_cited, pwp01_verifiable_t):
    return {
        "processors": {
            "PWP-01": {
                "agent_status": "ok",
                "confirmed_findings": [_finding(pwp01_cited)] if pwp01_cited else [],
                "score": {"verifiable_t": pwp01_verifiable_t},
            }
        }
    }


def _ground_truth(pwp01_is_f8_shipment_ids, true_verifiable_t):
    return {
        "processors": [
            {
                "processor_id": "PWP-01",
                "true_verifiable_t": true_verifiable_t,
                "shipments": [
                    {"shipment_id": sid, "is_f8": True} for sid in pwp01_is_f8_shipment_ids
                ],
            }
        ]
    }


def test_compute_run_metrics_correct_citation_and_accurate_verifiable_t():
    run_record = _run_record(["SHP-1"], 900.0)
    ground_truth = _ground_truth(["SHP-1"], 900.0)

    metrics = compute_run_metrics(run_record, ground_truth)

    assert metrics["overall_f1"] == 1.0
    assert metrics["mean_verifiable_t_abs_error"] == 0.0
    assert metrics["false_citations"] == []
    assert metrics["agent_status_counts"] == {"ok": 1}


def test_compute_run_metrics_flags_false_citation():
    run_record = _run_record(["SHP-999"], 900.0)
    ground_truth = _ground_truth(["SHP-1"], 900.0)

    metrics = compute_run_metrics(run_record, ground_truth)

    assert metrics["false_citations"] == [{"processor_id": "PWP-01", "shipment_id": "SHP-999"}]
    assert metrics["overall_precision"] == 0.0
    assert metrics["overall_recall"] == 0.0


def test_compute_run_metrics_measures_verifiable_t_error():
    run_record = _run_record([], 850.0)
    ground_truth = _ground_truth([], 900.0)

    metrics = compute_run_metrics(run_record, ground_truth)

    assert metrics["mean_verifiable_t_abs_error"] == 50.0


def test_compute_run_to_run_agreement_identical_runs_have_jaccard_1():
    run_a = _run_record(["SHP-1"], 900.0)
    run_b = _run_record(["SHP-1"], 900.0)

    agreement = compute_run_to_run_agreement(run_a, run_b)

    assert agreement["mean_jaccard"] == 1.0


def test_compute_run_to_run_agreement_disjoint_citations_have_jaccard_0():
    run_a = _run_record(["SHP-1"], 900.0)
    run_b = _run_record(["SHP-2"], 900.0)

    agreement = compute_run_to_run_agreement(run_a, run_b)

    assert agreement["mean_jaccard"] == 0.0
