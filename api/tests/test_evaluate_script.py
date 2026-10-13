"""Tests for scripts/evaluate.py's pure label/allow-list helpers — which
eval_metrics rows each dataset_label is allowed to carry. No network, no
real BigQuery calls.
"""

import scripts.evaluate as evaluate_script
from scripts.evaluate import (
    DATASET_LABELS,
    HELDOUT_SEED,
    build_rows,
    dev_metric_allowed,
    filter_rows_for_label,
    write_rows,
)

HELDOUT_LABEL = DATASET_LABELS[HELDOUT_SEED]
DEV_LABEL = DATASET_LABELS[42]


def _all_metric_names() -> list[str]:
    """Every metric name compute_metrics produces, built the same way it
    builds them (docs/DATA_SPEC.md §7) — so this test fails loudly if a
    new metric family is added without deciding whether the dev label
    should carry it."""
    names = ["key_field_read_accuracy"]
    for facts_source in ("truth", "extracted"):
        names += [f"issue_recall_F{i}_{facts_source}" for i in range(1, 8)]
        names += [
            f"finding_precision_checks_{facts_source}",
            f"false_flags_clean_processors_{facts_source}",
            f"false_flags_hard_negatives_{facts_source}",
            f"agent_citation_recall_{facts_source}",
            f"agent_citation_precision_{facts_source}",
        ]
        if facts_source == "extracted":
            names += ["issue_surfaced_as_review_flag_F5", "issue_surfaced_as_review_flag_F7"]
        for stage in ("checks_only", "full"):
            names += [
                f"risk_band_accuracy_{stage}_{facts_source}",
                f"unverifiable_t_abs_error_kg_{stage}_{facts_source}",
                f"unverifiable_t_pct_error_{stage}_{facts_source}",
            ]
    names += [
        "finding_set_agreement",
        "risk_band_stability",
        "unverifiable_t_stability",
        "agent_cost_micro_usd_per_processor",
        "agent_latency_ms_per_processor",
    ]
    return names


def test_every_seed_has_exactly_one_label():
    assert DATASET_LABELS == {7: "heldout-seed7", 42: "dev-seed42"}


def test_heldout_label_carries_every_computed_metric():
    rows = {metric: (1, 1) for metric in _all_metric_names()}
    assert filter_rows_for_label(rows, HELDOUT_LABEL) == rows


def test_dev_label_carries_only_the_summary_figure_rows():
    rows = {metric: (1, 1) for metric in _all_metric_names()}
    kept = sorted(filter_rows_for_label(rows, DEV_LABEL))

    assert kept == [
        "agent_citation_recall_extracted",
        "issue_recall_F1_extracted",
        "issue_recall_F2_extracted",
        "issue_recall_F3_extracted",
        "issue_recall_F4_extracted",
        "issue_recall_F5_extracted",
        "issue_recall_F6_extracted",
        "issue_recall_F7_extracted",
        "key_field_read_accuracy",
        "risk_band_accuracy_checks_only_extracted",
        "risk_band_accuracy_checks_only_truth",
        "risk_band_accuracy_full_extracted",
        "risk_band_accuracy_full_truth",
        "unverifiable_t_abs_error_kg_checks_only_extracted",
        "unverifiable_t_abs_error_kg_checks_only_truth",
        "unverifiable_t_abs_error_kg_full_extracted",
        "unverifiable_t_abs_error_kg_full_truth",
        "unverifiable_t_pct_error_checks_only_extracted",
        "unverifiable_t_pct_error_checks_only_truth",
        "unverifiable_t_pct_error_full_extracted",
        "unverifiable_t_pct_error_full_truth",
    ]


def test_dev_label_excludes_stability_cost_and_latency():
    """These need 3 fresh extracted-facts agent runs (Gemini cost); seed
    42 only has 2 saved truth-facts probe runs, so they can never be
    measured on the development set from stored output."""
    for metric in (
        "finding_set_agreement",
        "risk_band_stability",
        "unverifiable_t_stability",
        "agent_cost_micro_usd_per_processor",
        "agent_latency_ms_per_processor",
    ):
        assert not dev_metric_allowed(metric)


def test_dev_label_excludes_truth_mode_issue_recall():
    assert dev_metric_allowed("issue_recall_F1_extracted")
    assert not dev_metric_allowed("issue_recall_F1_truth")


def test_dev_label_excludes_precision_and_false_flag_families():
    for metric in (
        "finding_precision_checks_extracted",
        "agent_citation_precision_extracted",
        "false_flags_clean_processors_extracted",
        "false_flags_hard_negatives_extracted",
        "issue_surfaced_as_review_flag_F5",
    ):
        assert not dev_metric_allowed(metric)


class _FakeQueryJob:
    def result(self):
        return []


class _FakeClient:
    """Records every query() call so the write path's BigQuery table
    update count can be asserted — never talks to BigQuery."""

    def __init__(self):
        self.queries: list[tuple[str, object]] = []

    def query(self, query, job_config=None, location=None):
        self.queries.append((query, job_config))
        return _FakeQueryJob()


def test_write_rows_issues_exactly_one_delete_regardless_of_metric_count(monkeypatch):
    """BigQuery caps table update operations at a handful per ten seconds
    per table. One DELETE per metric (21 for the dev label, 44 for the
    held-out one) trips `429 Exceeded rate limits` and the load job that
    follows is rejected, leaving the label deleted but not rewritten."""
    loaded: list[list[dict]] = []
    monkeypatch.setattr(
        evaluate_script.bq, "load_rows", lambda client, table, rows: loaded.append(rows)
    )
    client = _FakeClient()
    rows = {f"metric_{i}": (i, 10) for i in range(44)}

    written = write_rows(client, rows, "abc123", DEV_LABEL)

    assert len(client.queries) == 1
    query, job_config = client.queries[0]
    assert "DELETE FROM" in query
    assert "dataset_label = @dataset_label" in query
    assert "metric IN UNNEST(@metrics)" in query
    assert len(written) == 44
    assert loaded == [written]


def test_write_rows_delete_is_scoped_to_its_own_dataset_label(monkeypatch):
    """Without the dataset_label predicate the DELETE would also remove
    the identically-named rows under the other label."""
    monkeypatch.setattr(evaluate_script.bq, "load_rows", lambda client, table, rows: None)
    client = _FakeClient()

    write_rows(client, {"key_field_read_accuracy": (5521, 5523)}, None, DEV_LABEL)

    _, job_config = client.queries[0]
    params = {
        p.name: p.values if hasattr(p, "values") else p.value for p in job_config.query_parameters
    }
    assert params["dataset_label"] == DEV_LABEL
    assert params["metrics"] == ["key_field_read_accuracy"]


def test_write_rows_with_no_metrics_touches_nothing(monkeypatch):
    monkeypatch.setattr(evaluate_script.bq, "load_rows", lambda client, table, rows: None)
    client = _FakeClient()

    assert write_rows(client, {}, None, DEV_LABEL) == []
    assert client.queries == []


def test_build_rows_stamps_every_row_with_the_same_label_and_commit():
    rows = build_rows({"a": (1, 2), "b": (3, 4)}, "deadbeef", HELDOUT_LABEL)

    assert {r["dataset_label"] for r in rows} == {HELDOUT_LABEL}
    assert {r["git_commit"] for r in rows} == {"deadbeef"}
    assert {r["source_script"] for r in rows} == {"scripts/evaluate.py"}
    assert len({r["computed_at"] for r in rows}) == 1
