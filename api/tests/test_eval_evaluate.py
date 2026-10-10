"""Tests for T14's new pure scoring functions in app/eval/evaluate.py —
no network, no BigQuery."""

from app.eval.evaluate import (
    agent_citation_metrics,
    describe_misses,
    false_flags_on_clean,
    false_flags_on_hard_negatives,
    finding_precision_checks,
    issue_type_recall,
    pooled_run_to_run_agreement,
    risk_band_accuracy,
    verifiable_t_error,
)


def _ground_truth(processors: list[dict]) -> dict:
    return {"processors": processors}


def _processor(
    pid,
    issue_types=None,
    label="issues",
    hard_negatives=None,
    certified_t=1000.0,
    true_verifiable_t=1000.0,
    shipments=None,
    energy_monthly=None,
):
    return {
        "processor_id": pid,
        "label": label,
        "issue_types": issue_types or [],
        "hard_negatives": hard_negatives or [],
        "certified_t": certified_t,
        "true_verifiable_t": true_verifiable_t,
        "shipments": shipments or [],
        "energy_monthly": energy_monthly or [],
    }


def _check(check_id, status):
    return {"check_id": check_id, "status": status}


def _finding(cited_shipment_ids, classification="deductible"):
    return {"classification": classification, "cited_shipment_ids": cited_shipment_ids}


def test_issue_type_recall_detects_when_mapped_check_fails():
    ground_truth = _ground_truth([_processor("PWP-01", issue_types=["F1"])])
    check_results_by_processor = {"PWP-01": [_check("C1", "fail")]}

    result = issue_type_recall(check_results_by_processor, ground_truth, "F1")

    assert result == {"numerator": 1, "denominator": 1}


def test_issue_type_recall_misses_when_mapped_check_passes():
    ground_truth = _ground_truth([_processor("PWP-01", issue_types=["F1"])])
    check_results_by_processor = {"PWP-01": [_check("C1", "pass")]}

    result = issue_type_recall(check_results_by_processor, ground_truth, "F1")

    assert result == {"numerator": 0, "denominator": 1}


def test_issue_type_recall_denominator_is_only_processors_with_that_issue():
    ground_truth = _ground_truth(
        [_processor("PWP-01", issue_types=["F1"]), _processor("PWP-02", issue_types=["F6"])]
    )
    check_results_by_processor = {
        "PWP-01": [_check("C1", "fail")],
        "PWP-02": [_check("C6", "fail")],
    }

    result = issue_type_recall(check_results_by_processor, ground_truth, "F1")

    assert result == {"numerator": 1, "denominator": 1}


def test_finding_precision_checks_true_positive_matches_planted_issue():
    ground_truth = _ground_truth([_processor("PWP-01", issue_types=["F1"])])
    check_results_by_processor = {"PWP-01": [_check("C1", "fail")]}

    result = finding_precision_checks(check_results_by_processor, ground_truth)

    assert result == {"numerator": 1, "denominator": 1}


def test_finding_precision_checks_false_positive_when_no_matching_issue_planted():
    ground_truth = _ground_truth([_processor("PWP-01", issue_types=[])])
    check_results_by_processor = {"PWP-01": [_check("C1", "fail")]}

    result = finding_precision_checks(check_results_by_processor, ground_truth)

    assert result == {"numerator": 0, "denominator": 1}


def test_finding_precision_checks_ignores_untracked_check_ids():
    ground_truth = _ground_truth([_processor("PWP-01", issue_types=[])])
    check_results_by_processor = {"PWP-01": [_check("AGENT_SYSTEMIC_FINDING", "warn")]}

    result = finding_precision_checks(check_results_by_processor, ground_truth)

    assert result == {"numerator": 0, "denominator": 0}


def test_false_flags_on_clean_counts_wrongly_flagged_clean_processor():
    ground_truth = _ground_truth(
        [_processor("PWP-01", label="clean"), _processor("PWP-02", label="clean")]
    )
    check_results_by_processor = {
        "PWP-01": [_check("C1", "fail")],
        "PWP-02": [_check("C1", "pass")],
    }
    findings_by_processor = {"PWP-01": [], "PWP-02": []}

    result = false_flags_on_clean(check_results_by_processor, findings_by_processor, ground_truth)

    assert result == {"numerator": 1, "denominator": 2}


def test_false_flags_on_clean_concurs_with_check_finding_does_not_double_count_as_new_flag():
    ground_truth = _ground_truth([_processor("PWP-01", label="clean")])
    check_results_by_processor = {"PWP-01": [_check("C1", "pass")]}
    findings_by_processor = {"PWP-01": [_finding(["SHP-1"], classification="concurs_with_check")]}

    result = false_flags_on_clean(check_results_by_processor, findings_by_processor, ground_truth)

    assert result == {"numerator": 0, "denominator": 1}


def test_false_flags_on_hard_negatives_excludes_h5():
    ground_truth = _ground_truth(
        [
            _processor("PWP-02", label="clean", hard_negatives=["H5"]),
            _processor("PWP-03", label="clean", hard_negatives=["H1", "H2"]),
        ]
    )
    check_results_by_processor = {"PWP-02": [], "PWP-03": [_check("C1", "fail")]}
    findings_by_processor = {"PWP-02": [], "PWP-03": []}

    result = false_flags_on_hard_negatives(
        check_results_by_processor, findings_by_processor, ground_truth
    )

    # PWP-02 (H5-only) is excluded from the denominator entirely.
    assert result == {"numerator": 1, "denominator": 1}


def test_risk_band_accuracy_matches_ground_truth_band():
    ground_truth = _ground_truth(
        [_processor("PWP-01", certified_t=1000.0, true_verifiable_t=1000.0)]
    )
    assessments = {"PWP-01": {"risk_band": "Low", "certified_t": 1000.0, "verifiable_t": 1000.0}}

    result = risk_band_accuracy(assessments, ground_truth)

    assert result == {"numerator": 1, "denominator": 1}


def test_risk_band_accuracy_mismatch():
    ground_truth = _ground_truth(
        [
            _processor("PWP-01", certified_t=1000.0, true_verifiable_t=500.0)
        ]  # 50% unverifiable -> High
    )
    assessments = {"PWP-01": {"risk_band": "Low", "certified_t": 1000.0, "verifiable_t": 1000.0}}

    result = risk_band_accuracy(assessments, ground_truth)

    assert result == {"numerator": 0, "denominator": 1}


def test_risk_band_accuracy_skips_processors_with_no_assessment():
    ground_truth = _ground_truth([_processor("PWP-01"), _processor("PWP-02")])
    assessments = {"PWP-01": {"risk_band": "Low", "certified_t": 1000.0, "verifiable_t": 1000.0}}

    result = risk_band_accuracy(assessments, ground_truth)

    assert result == {"numerator": 1, "denominator": 1}


def test_verifiable_t_error_zero_when_exact_match():
    ground_truth = _ground_truth([_processor("PWP-01", true_verifiable_t=900.0)])
    assessments = {"PWP-01": {"verifiable_t": 900.0}}

    result = verifiable_t_error(assessments, ground_truth)

    assert result == {"abs_error_kg": 0, "pct_error_micro": 0}


def test_verifiable_t_error_scales_tonnes_to_kg_and_percent():
    ground_truth = _ground_truth([_processor("PWP-01", true_verifiable_t=1000.0)])
    assessments = {"PWP-01": {"verifiable_t": 900.0}}  # 100t = 100_000 kg error, 10% error

    result = verifiable_t_error(assessments, ground_truth)

    assert result == {"abs_error_kg": 100_000, "pct_error_micro": 100_000}


def test_agent_citation_metrics_perfect_recall_and_precision():
    ground_truth = _ground_truth(
        [
            {
                "processor_id": "PWP-01",
                "issue_types": [],
                "shipments": [{"shipment_id": "SHP-1", "is_f8": True}],
            }
        ]
    )
    findings_by_processor = {"PWP-01": [_finding(["SHP-1"])]}

    result = agent_citation_metrics(findings_by_processor, ground_truth)

    assert result["recall"] == {"numerator": 1, "denominator": 1}
    assert result["precision"] == {"numerator": 1, "denominator": 1}


def test_agent_citation_metrics_excludes_f5_processor_entirely():
    ground_truth = _ground_truth(
        [
            {
                "processor_id": "PWP-09",
                "issue_types": ["F5"],
                "shipments": [{"shipment_id": "SHP-1"}],
            }
        ]
    )
    # A real, unrelated finding citing SHP-1 on the F5 processor must not
    # count as a false F8 citation.
    findings_by_processor = {"PWP-09": [_finding(["SHP-1"])]}

    result = agent_citation_metrics(findings_by_processor, ground_truth)

    assert result["recall"] == {"numerator": 0, "denominator": 0}
    assert result["precision"] == {"numerator": 0, "denominator": 0}


def test_pooled_run_to_run_agreement_identical_runs_is_full_agreement():
    run = {
        "PWP-01": {"confirmed_findings": [_finding(["SHP-1"])], "concurs_with_check_findings": []}
    }

    result = pooled_run_to_run_agreement([run, run, run])

    assert result["numerator"] == result["denominator"]
    assert result["denominator"] > 0


def test_pooled_run_to_run_agreement_both_empty_counts_as_agreement():
    run = {"PWP-01": {"confirmed_findings": [], "concurs_with_check_findings": []}}

    result = pooled_run_to_run_agreement([run, run])

    assert result == {"numerator": 1, "denominator": 1}


def test_pooled_run_to_run_agreement_disjoint_citations_pool_as_zero():
    run_a = {
        "PWP-01": {"confirmed_findings": [_finding(["SHP-1"])], "concurs_with_check_findings": []}
    }
    run_b = {
        "PWP-01": {"confirmed_findings": [_finding(["SHP-2"])], "concurs_with_check_findings": []}
    }

    result = pooled_run_to_run_agreement([run_a, run_b])

    assert result == {"numerator": 0, "denominator": 2}


def test_describe_misses_reports_recall_shortfall_with_issue_label():
    rows = [{"metric": "issue_recall_F3_truth", "numerator": 0, "denominator": 1}]

    misses = describe_misses(rows)

    assert len(misses) == 1
    assert "F3 quantity inflation" in misses[0]
    assert "0/1" in misses[0]
    assert "truth" in misses[0]


def test_describe_misses_silent_on_perfect_recall():
    rows = [{"metric": "issue_recall_F1_truth", "numerator": 1, "denominator": 1}]

    assert describe_misses(rows) == []


def test_describe_misses_reports_false_flags_only_when_nonzero():
    clean_row = {
        "metric": "false_flags_clean_processors_extracted",
        "numerator": 0,
        "denominator": 3,
    }
    hard_row = {"metric": "false_flags_hard_negatives_truth", "numerator": 1, "denominator": 2}

    misses = describe_misses([clean_row, hard_row])

    assert len(misses) == 1
    assert "1/2" in misses[0]
    assert "hard-negative" in misses[0]


def test_describe_misses_reports_risk_band_shortfall_with_stage_label():
    rows = [
        {"metric": "risk_band_accuracy_checks_only_extracted", "numerator": 8, "denominator": 10}
    ]

    misses = describe_misses(rows)

    assert len(misses) == 1
    assert "checks only" in misses[0]
    assert "extracted" in misses[0]
    assert "8/10" in misses[0]


def test_describe_misses_ignores_cost_and_latency_metrics():
    rows = [
        {"metric": "agent_cost_micro_usd_per_processor", "numerator": 500_000, "denominator": 1},
        {"metric": "agent_latency_ms_per_processor", "numerator": 1200, "denominator": 1},
    ]

    assert describe_misses(rows) == []
