"""Tests for scripts/report_extraction_mismatches.py's --write-bq row-
building logic (write_accuracy_metric). No network, no real BigQuery —
bq.delete_eval_metrics/load_rows are monkeypatched to a fake client."""

from scripts.report_extraction_mismatches import EVAL_METRIC, write_accuracy_metric


def test_write_accuracy_metric_deletes_then_loads_one_row(monkeypatch):
    deletes = []
    loads = []
    monkeypatch.setattr(
        "scripts.report_extraction_mismatches.bq.delete_eval_metrics",
        lambda client, dataset_label, metric: deletes.append((dataset_label, metric)),
    )
    monkeypatch.setattr(
        "scripts.report_extraction_mismatches.bq.load_rows",
        lambda client, table_name, rows: loads.append((table_name, rows)),
    )

    row = write_accuracy_metric(
        bq_client=object(),
        seed=42,
        overall={"correct": 5521, "total": 5523},
        git_commit="abc123",
    )

    assert deletes == [("dev-seed42", EVAL_METRIC)]
    assert len(loads) == 1
    table_name, rows = loads[0]
    assert table_name == "eval_metrics"
    assert rows == [row]
    assert row["dataset_label"] == "dev-seed42"
    assert row["metric"] == EVAL_METRIC
    assert row["numerator"] == 5521
    assert row["denominator"] == 5523
    assert row["source_script"] == "scripts/report_extraction_mismatches.py"
    assert row["git_commit"] == "abc123"
    assert row["computed_at"]  # a real ISO timestamp, not asserting the exact value


def test_write_accuracy_metric_delete_runs_before_load(monkeypatch):
    order = []
    monkeypatch.setattr(
        "scripts.report_extraction_mismatches.bq.delete_eval_metrics",
        lambda client, dataset_label, metric: order.append("delete"),
    )
    monkeypatch.setattr(
        "scripts.report_extraction_mismatches.bq.load_rows",
        lambda client, table_name, rows: order.append("load"),
    )

    write_accuracy_metric(bq_client=object(), seed=7, overall={"correct": 1, "total": 1})

    assert order == ["delete", "load"]


def test_write_accuracy_metric_git_commit_optional(monkeypatch):
    monkeypatch.setattr(
        "scripts.report_extraction_mismatches.bq.delete_eval_metrics", lambda *a, **k: None
    )
    loads = []
    monkeypatch.setattr(
        "scripts.report_extraction_mismatches.bq.load_rows",
        lambda client, table_name, rows: loads.append(rows),
    )

    row = write_accuracy_metric(bq_client=object(), seed=42, overall={"correct": 1, "total": 2})

    assert row["git_commit"] is None
