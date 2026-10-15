"""Tests for scripts/evaluate.py's pure label/allow-list helpers — which
eval_metrics rows each dataset_label is allowed to carry. No network, no
real BigQuery calls.
"""

import pytest

import scripts.evaluate as evaluate_script
from app.agents import scorer
from app.eval import evaluate as ev
from scripts.evaluate import (
    DATASET_LABELS,
    HELDOUT_SEED,
    RISK_BAND_ORDER,
    MetricDrift,
    _per_processor_abs_error_rows,
    _per_processor_band_rows,
    build_rows,
    compare_metrics,
    dev_metric_allowed,
    filter_rows_for_label,
    parse_expected_rows,
    write_rows,
)

PROCESSOR_IDS = [f"PWP-{i:02d}" for i in range(1, 11)]

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
                f"per_processor_unverifiable_t_abs_error_kg_{stage}_{facts_source}_{pid}"
                for pid in PROCESSOR_IDS
            ]
    names += [
        "finding_set_agreement",
        "risk_band_stability",
        "unverifiable_t_stability",
        "agent_cost_micro_usd_per_processor",
        "agent_latency_ms_per_processor",
    ]
    names += [
        f"per_processor_risk_band_run{run}_{pid}" for run in (1, 2, 3) for pid in PROCESSOR_IDS
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


# --- per-processor metric families (T18) ------------------------------------


def _ground_truth(true_by_processor: dict[str, float]) -> dict:
    return [
        {"processor_id": pid, "true_verifiable_t": value}
        for pid, value in true_by_processor.items()
    ]


def test_risk_band_order_matches_the_scorer():
    """The band encoding is a local copy of a frozen list. If the scorer
    ever gains a band, every stored ordinal would silently shift."""
    assert list(RISK_BAND_ORDER) == scorer._RISK_BANDS


def test_dev_label_excludes_every_per_processor_metric():
    """The dev label is written from the live dataset and only carries the
    four summary figures; 70 per-processor rows there would be noise the
    page never reads."""
    rows = {metric: (1, 1) for metric in _all_metric_names()}
    kept = filter_rows_for_label(rows, DEV_LABEL)

    assert not [metric for metric in kept if metric.startswith("per_processor_")]
    assert not dev_metric_allowed("per_processor_risk_band_run1_PWP-01")
    assert not dev_metric_allowed("per_processor_unverifiable_t_abs_error_kg_full_truth_PWP-01")


def test_per_processor_abs_error_rows_encode_kilograms_per_processor():
    ground_truth = {"processors": _ground_truth({"PWP-01": 100.0, "PWP-02": 50.0})}
    assessments = {"PWP-01": {"verifiable_t": 98.5}, "PWP-02": {"verifiable_t": 50.0}}

    rows = _per_processor_abs_error_rows(assessments, ground_truth, "full", "truth", 750)

    assert rows == {
        "per_processor_unverifiable_t_abs_error_kg_full_truth_PWP-01": (1500, 1),
        "per_processor_unverifiable_t_abs_error_kg_full_truth_PWP-02": (0, 1),
    }


def test_per_processor_abs_error_rows_skip_processors_with_no_assessment():
    """verifiable_t_error iterates ground truth but skips any processor
    without an assessment row, so these rows must skip exactly the same
    ones or the mean would be taken over a different denominator."""
    ground_truth = {"processors": _ground_truth({"PWP-01": 100.0, "PWP-02": 50.0})}
    assessments = {"PWP-01": {"verifiable_t": 99.0}}

    rows = _per_processor_abs_error_rows(
        assessments, ground_truth, "checks_only", "extracted", 1000
    )

    assert list(rows) == ["per_processor_unverifiable_t_abs_error_kg_checks_only_extracted_PWP-01"]


def test_per_processor_abs_error_rows_reject_a_drifting_aggregate():
    ground_truth = {"processors": _ground_truth({"PWP-01": 100.0})}
    assessments = {"PWP-01": {"verifiable_t": 98.0}}

    with pytest.raises(MetricDrift, match="aggregate metric reads 999 kg"):
        _per_processor_abs_error_rows(assessments, ground_truth, "full", "truth", 999)


def test_per_processor_abs_error_assertion_uses_the_unrounded_mean():
    """Rounding each processor first and averaging those does not
    reproduce the frozen aggregate. These four errors (0.5, 0.5, 0.5 and
    2.5 kg) average to 1 kg unrounded but 0 kg if rounded first, so the
    aggregate is only accepted when the unrounded mean is used."""
    errors_t = [0.0005, 0.0005, 0.0005, 0.0025]
    processor_ids = [f"PWP-{i:02d}" for i in range(1, 5)]
    ground_truth = {"processors": _ground_truth(dict.fromkeys(processor_ids, 0.0))}
    assessments = {pid: {"verifiable_t": error} for pid, error in zip(processor_ids, errors_t)}
    unrounded_mean_kg = round(sum(error * 1000.0 for error in errors_t) / len(errors_t))

    rows = _per_processor_abs_error_rows(
        assessments, ground_truth, "full", "truth", unrounded_mean_kg
    )

    numerators = [numerator for numerator, _ in rows.values()]
    assert round(sum(numerators) / len(numerators)) != unrounded_mean_kg


def test_per_processor_band_rows_encode_the_band_ordinal():
    runs = [
        {"PWP-01": {"score": {"risk_band": "Low"}}, "PWP-02": {"score": {"risk_band": "High"}}},
        {"PWP-01": {"score": {"risk_band": "Low"}}, "PWP-02": {"score": {"risk_band": "Medium"}}},
    ]

    rows = _per_processor_band_rows(runs, {"numerator": 1, "denominator": 2})

    assert rows == {
        "per_processor_risk_band_run1_PWP-01": (0, 3),
        "per_processor_risk_band_run1_PWP-02": (2, 3),
        "per_processor_risk_band_run2_PWP-01": (0, 3),
        "per_processor_risk_band_run2_PWP-02": (1, 3),
    }


def test_per_processor_band_rows_reject_an_unknown_band():
    runs = [{"PWP-01": {"score": {"risk_band": "Critical"}}}]

    with pytest.raises(MetricDrift, match="not one of"):
        _per_processor_band_rows(runs, {"numerator": 1, "denominator": 1})


def test_per_processor_band_rows_reject_a_drifting_stability_aggregate():
    """One processor, two runs, two different bands — zero stable. An
    aggregate claiming otherwise means the strip and the published
    stability figure disagree."""
    runs = [
        {"PWP-01": {"score": {"risk_band": "Low"}}},
        {"PWP-01": {"score": {"risk_band": "High"}}},
    ]

    with pytest.raises(MetricDrift, match="stability 0/1"):
        _per_processor_band_rows(runs, {"numerator": 1, "denominator": 1})


# --- comparison and the guarded write modes (T18) ---------------------------


def test_compare_metrics_splits_changed_new_and_stored_only():
    stored = {"same": (1, 2), "moved": (3, 4), "retired": (9, 9)}
    computed = {"same": (1, 2), "moved": (5, 4), "fresh": (7, 1)}

    comparison = compare_metrics(computed, stored)

    assert comparison["changed"] == [("moved", (3, 4), (5, 4))]
    assert comparison["new"] == ["fresh"]
    assert comparison["stored_only"] == ["retired"]
    assert comparison["unchanged"] == ["same"]


def test_parse_expected_rows_reads_a_bq_json_export():
    text = (
        '[{"dataset_label":"heldout-seed7","metric":"key_field_read_accuracy",'
        '"numerator":"5430","denominator":"5431"}]'
    )

    assert parse_expected_rows(text) == {"key_field_read_accuracy": (5430, 5431)}


def test_parse_expected_rows_reads_a_csv_export():
    text = "metric,numerator,denominator\nrisk_band_stability,9,10\n"

    assert parse_expected_rows(text) == {"risk_band_stability": (9, 10)}


def test_parse_expected_rows_rejects_a_missing_column():
    with pytest.raises(SystemExit, match="missing column"):
        parse_expected_rows('[{"metric":"a","numerator":1}]')


def test_parse_expected_rows_treats_empty_input_as_no_rows():
    assert parse_expected_rows("   \n") == {}


class _MainHarness:
    """Drives main() with every BigQuery touchpoint replaced, so the mode
    logic can be asserted without a client, a dataset or a network."""

    def __init__(self, monkeypatch, computed, stored):
        self.written: list[dict] = []
        monkeypatch.setattr(evaluate_script.bq, "get_client", lambda: object())
        monkeypatch.setattr(evaluate_script, "compute_metrics", lambda seed, client: computed)
        monkeypatch.setattr(evaluate_script, "fetch_stored_rows", lambda client, label: stored)
        monkeypatch.setattr(evaluate_script, "_git_commit", lambda: "abc123")
        monkeypatch.setattr(
            evaluate_script,
            "write_rows",
            lambda client, rows, commit, label: self._record(rows, label),
        )

    def _record(self, rows, label):
        self.written.append({"rows": dict(rows), "label": label})
        return list(rows)

    def run(self, *argv):
        monkeypatch_argv = ["evaluate.py", *argv]
        import sys

        original = sys.argv
        sys.argv = monkeypatch_argv
        try:
            evaluate_script.main()
        finally:
            sys.argv = original


def test_dry_run_writes_nothing_when_every_stored_metric_matches(monkeypatch, capsys):
    stored = {"risk_band_stability": (9, 10)}
    computed = {"risk_band_stability": (9, 10), "per_processor_risk_band_run1_PWP-01": (0, 3)}
    harness = _MainHarness(monkeypatch, computed, stored)

    harness.run("--seed", "7", "--dry-run")

    assert harness.written == []
    assert "nothing written" in capsys.readouterr().out


def test_dry_run_fails_when_a_stored_metric_would_change(monkeypatch):
    stored = {"risk_band_stability": (9, 10)}
    computed = {"risk_band_stability": (8, 10)}
    harness = _MainHarness(monkeypatch, computed, stored)

    with pytest.raises(SystemExit, match="1 existing metric\\(s\\) would change"):
        harness.run("--seed", "7", "--dry-run")

    assert harness.written == []


def test_only_new_writes_just_the_new_metric_names(monkeypatch):
    stored = {"risk_band_stability": (9, 10)}
    computed = {
        "risk_band_stability": (9, 10),
        "per_processor_risk_band_run1_PWP-01": (0, 3),
        "per_processor_unverifiable_t_abs_error_kg_full_truth_PWP-01": (1500, 1),
    }
    harness = _MainHarness(monkeypatch, computed, stored)

    harness.run("--seed", "7", "--only-new")

    assert len(harness.written) == 1
    assert sorted(harness.written[0]["rows"]) == [
        "per_processor_risk_band_run1_PWP-01",
        "per_processor_unverifiable_t_abs_error_kg_full_truth_PWP-01",
    ]
    assert harness.written[0]["label"] == HELDOUT_LABEL


def test_only_new_refuses_to_write_when_an_existing_metric_would_change(monkeypatch):
    stored = {"risk_band_stability": (9, 10)}
    computed = {"risk_band_stability": (8, 10), "per_processor_risk_band_run1_PWP-01": (0, 3)}
    harness = _MainHarness(monkeypatch, computed, stored)

    with pytest.raises(SystemExit, match="would change"):
        harness.run("--seed", "7", "--only-new")

    assert harness.written == []


def test_only_new_is_idempotent_once_the_new_rows_exist(monkeypatch, capsys):
    rows = {"risk_band_stability": (9, 10), "per_processor_risk_band_run1_PWP-01": (0, 3)}
    harness = _MainHarness(monkeypatch, computed=rows, stored=rows)

    harness.run("--seed", "7", "--only-new")

    assert harness.written == []
    assert "already stored" in capsys.readouterr().out


def test_only_new_leaves_a_stored_metric_it_does_not_recompute_alone(monkeypatch):
    """A retired metric name is reported, never deleted — --only-new's
    DELETE is scoped to the names it is about to write."""
    stored = {"risk_band_stability": (9, 10), "agent_run_to_run_agreement": (28, 60)}
    computed = {"risk_band_stability": (9, 10), "per_processor_risk_band_run1_PWP-01": (0, 3)}
    harness = _MainHarness(monkeypatch, computed, stored)

    harness.run("--seed", "7", "--only-new")

    assert list(harness.written[0]["rows"]) == ["per_processor_risk_band_run1_PWP-01"]


def test_dry_run_and_only_new_are_mutually_exclusive(monkeypatch):
    harness = _MainHarness(monkeypatch, {}, {})

    with pytest.raises(SystemExit, match="alternatives"):
        harness.run("--seed", "7", "--dry-run", "--only-new")


def test_expected_requires_a_guarded_mode(monkeypatch):
    harness = _MainHarness(monkeypatch, {}, {})

    with pytest.raises(SystemExit, match="only applies to"):
        harness.run("--seed", "7", "--expected", "export.json")


def test_per_processor_rows_add_nothing_to_the_misses_list():
    """describe_misses drives /evaluation's misses list and is frozen. It
    matches five aggregate prefixes, none of which per_processor_ can
    match — pinned here because 70 new rows reaching that list would put
    per-processor noise on the page."""
    rows = [
        {"metric": metric, "numerator": 0, "denominator": 3}
        for metric in _all_metric_names()
        if metric.startswith("per_processor_")
    ]

    assert ev.describe_misses(rows) == []


def test_the_heldout_label_carries_exactly_seventy_new_rows():
    """The count the runbook's verification SELECT checks against."""
    names = _all_metric_names()
    per_processor = [metric for metric in names if metric.startswith("per_processor_")]

    assert len(per_processor) == 70
    assert len([m for m in per_processor if "abs_error_kg" in m]) == 40
    assert len([m for m in per_processor if "risk_band_run" in m]) == 30
    assert len(names) == 114
