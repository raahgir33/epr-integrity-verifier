"""Tests for scripts/report_truth_vs_extracted.py's pure diff functions.
No network, no real BigQuery/Gemini calls."""

from scripts.report_truth_vs_extracted import (
    diff_check_results,
    diff_findings,
    diff_verifiable_t,
)


def _stage(verifiable_t, risk_band="Low"):
    return {"verifiable_t": verifiable_t, "risk_band": risk_band}


def test_diff_verifiable_t_none_when_equal():
    assert diff_verifiable_t(_stage(100.0), _stage(100.0)) is None


def test_diff_verifiable_t_none_within_float_tolerance():
    assert diff_verifiable_t(_stage(100.00), _stage(100.005)) is None


def test_diff_verifiable_t_reports_delta_beyond_tolerance():
    result = diff_verifiable_t(_stage(100.0), _stage(90.0))
    assert result["truth_verifiable_t"] == 100.0
    assert result["extracted_verifiable_t"] == 90.0
    assert "delta -10.00t" in result["cause"]


def test_diff_verifiable_t_reports_risk_band_change_even_if_tonnes_equal():
    result = diff_verifiable_t(_stage(100.0, "Low"), _stage(100.0, "High"))
    assert result is not None
    assert result["truth_risk_band"] == "Low"
    assert result["extracted_risk_band"] == "High"


def test_diff_verifiable_t_both_missing_is_none():
    assert diff_verifiable_t(None, None) is None


def test_diff_verifiable_t_one_missing_is_reported():
    result = diff_verifiable_t(_stage(100.0), None)
    assert result["extracted_verifiable_t"] is None
    assert "extracted" in result["cause"]


def _check(check_id, status, measured=1.0, threshold=2.0):
    return {"check_id": check_id, "status": status, "measured": measured, "threshold": threshold}


def test_diff_check_results_no_diff_when_statuses_match():
    truth = [_check("C1", "pass")]
    extracted = [_check("C1", "pass")]
    assert diff_check_results(truth, extracted) == []


def test_diff_check_results_flags_status_change():
    truth = [_check("C1", "pass", measured=1.0)]
    extracted = [_check("C1", "fail", measured=5.0)]
    diffs = diff_check_results(truth, extracted)
    assert len(diffs) == 1
    assert diffs[0]["check_id"] == "C1"
    assert diffs[0]["truth_status"] == "pass"
    assert diffs[0]["extracted_status"] == "fail"
    assert "measured truth=1.0 extracted=5.0" in diffs[0]["cause"]


def test_diff_check_results_flags_check_present_on_only_one_side():
    truth = [_check("C1", "pass")]
    extracted = []
    diffs = diff_check_results(truth, extracted)
    assert diffs[0]["extracted_status"] == "missing"


def _finding(finding_type, cited, classification="deductible"):
    return {
        "finding_type": finding_type,
        "cited_shipment_ids": cited,
        "classification": classification,
    }


def test_diff_findings_same_type_and_shipments_is_no_diff():
    truth = [_finding("F8", ["SHP-1"])]
    extracted = [_finding("F8", ["SHP-1"])]
    only_truth, only_extracted = diff_findings(truth, extracted)
    assert only_truth == []
    assert only_extracted == []


def test_diff_findings_order_of_cited_shipments_does_not_matter():
    truth = [_finding("F8", ["SHP-2", "SHP-1"])]
    extracted = [_finding("F8", ["SHP-1", "SHP-2"])]
    only_truth, only_extracted = diff_findings(truth, extracted)
    assert only_truth == []
    assert only_extracted == []


def test_diff_findings_flags_finding_only_on_one_side():
    truth = [_finding("F8", ["SHP-1"])]
    extracted = []
    only_truth, only_extracted = diff_findings(truth, extracted)
    assert len(only_truth) == 1
    assert only_extracted == []


def test_diff_findings_different_wording_same_shipments_and_classification_is_no_diff():
    # Matching is by (shipment set, classification), never free-text
    # finding_type — the model can describe the same underlying finding
    # differently between a truth-mode and an extracted-mode run.
    truth = [_finding("Virgin material described on invoice", ["SHP-1"])]
    extracted = [_finding("Inbound material description mismatch", ["SHP-1"])]
    only_truth, only_extracted = diff_findings(truth, extracted)
    assert only_truth == []
    assert only_extracted == []


def test_diff_findings_same_shipments_different_classification_is_a_diff():
    truth = [_finding("F8", ["SHP-1"], classification="deductible")]
    extracted = [_finding("F8", ["SHP-1"], classification="review_flag")]
    only_truth, only_extracted = diff_findings(truth, extracted)
    assert len(only_truth) == 1
    assert len(only_extracted) == 1


def test_diff_findings_normalizes_extracted_mode_shipment_ids():
    # Extracted-mode shipment_ids carry an "EXT-" segment truth mode's
    # own IDs don't — the exact bug the first real comparison hit.
    truth = [_finding("F8", ["PWP-06-SHP-003"])]
    extracted = [_finding("F8", ["PWP-06-EXT-SHP-003"])]
    only_truth, only_extracted = diff_findings(truth, extracted)
    assert only_truth == []
    assert only_extracted == []


def test_diff_findings_normalizes_multiple_shipment_ids_regardless_of_order():
    truth = [_finding("F2", ["PWP-07-SHP-002", "PWP-07-SHP-005"])]
    extracted = [_finding("F2", ["PWP-07-EXT-SHP-005", "PWP-07-EXT-SHP-002"])]
    only_truth, only_extracted = diff_findings(truth, extracted)
    assert only_truth == []
    assert only_extracted == []
