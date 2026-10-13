"""T14 held-out evaluation: computes docs/DATA_SPEC.md §7's metrics for a
seed against ground_truth.json, and writes them to the LIVE
epr.eval_metrics table so the deployed single-dataset API can serve GET
/evaluation without ever pointing at two datasets at once.

Two modes, chosen by --seed (see DATASET_LABELS):

  --seed 7   dataset_label "heldout-seed7": the headline. Reads every
             seed-7 pipeline table from a SEPARATE dataset
             (--eval-dataset, default "epr_eval"), never the live one,
             and writes the full metric set.
  --seed 42  dataset_label "dev-seed42": the development set. The
             developer passes --eval-dataset epr, so this mode reads the
             LIVE dataset — READ-ONLY; the only writes this script ever
             makes are to eval_metrics, scoped to (dataset_label, metric).
             Only the rows behind /evaluation's four summary figures are
             written (DEV_METRIC_PREFIXES) — everything else is labelled
             "not run on the development set" by the page. Run it after
             POST /admin/reset-demo, since a live demo run mutates
             seed-42's extracted-facts rows for PWP-01/03/05.

The read dataset is selected by temporarily pointing
app.config.settings.bq_dataset at --eval-dataset for the whole read
phase, then restoring it to whatever BQ_DATASET already was (normally
"epr") for the one write phase at the end. Every read/write helper reused
here (app.store.cache, app.store.bq, scripts.run_pipeline) already resolves
the dataset dynamically from `settings.bq_dataset` at call time, so this
toggle is the only mechanism needed — no other code changes, and no
hardcoded dataset name anywhere in this file.

Every metric is an integer numerator/denominator pair (dollars and
kilograms scaled to integers where needed) — the existing eval_metrics
schema (dataset_label, metric, numerator, denominator, computed_at,
source_script, git_commit) already fits every metric below; no ALTER TABLE
is needed.

Prerequisites (see docs/GCP_SETUP.md's T14 section for the exact commands):
  1. scripts/generate_dossiers.py --seed 7 (local)
  2. scripts/deploy/create_tables.py and scripts/load_dossiers.py --seed 7,
     both with BQ_DATASET=<eval dataset>
  3. scripts/run_pipeline.py --seed 7 --stage {extract,normalize,checks,
     site,agents} for every facts_source this script reads (both truth and
     extracted), with BQ_DATASET=<eval dataset>
  4. scripts/probe_agent_thinking.py --seed 7 --facts-source extracted
     --configs no_thinking --runs-per-config 3 (3 independent runs, for the
     finding_set_agreement/risk_band_stability/unverifiable_t_stability/
     cost/latency metrics — read from this script's own saved JSON, not
     BigQuery, since BigQuery's agent_runs/assessments tables only ever
     hold the latest run per processor)

Run by the developer — never by the agent (reads/writes real BigQuery).

Usage: uv run python scripts/evaluate.py --seed 7
       uv run python scripts/evaluate.py --seed 42 --eval-dataset epr
"""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import bigquery

from app.config import settings
from app.eval import evaluate as ev
from app.ingest.normalize import EXTRACTED, TRUTH
from app.store import bq, cache
from scripts.cost_report import estimate_cost_usd
from scripts.run_pipeline import _fetch_bq_rows, load_ground_truth

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPT = "scripts/evaluate.py"

# One eval_metrics dataset_label per seed. A seed with no entry here is
# refused rather than guessed at, so a typo can never write a third label
# the API and the page know nothing about.
DATASET_LABELS = {7: "heldout-seed7", 42: "dev-seed42"}

HELDOUT_SEED = 7

# The development set gets only the rows behind /evaluation's four
# summary figures: risk-band accuracy, tonnage error (percentage plus its
# companion absolute kilograms), key fields read, and patterns detected
# (aggregated by the page from the per-issue recall rows and the
# agent-only citation-recall row). Everything else the held-out label
# carries is deliberately absent here and labelled "not run on the
# development set" — it would measure prompts and thresholds against the
# very data they were tuned on, or (stability/cost/latency) need fresh
# Gemini runs. Both facts sources are written for band and tonnage so the
# page can prefer ground-truth facts and fall back to extracted.
DEV_METRIC_PREFIXES = (
    "key_field_read_accuracy",
    "risk_band_accuracy_",
    "unverifiable_t_abs_error_kg_",
    "unverifiable_t_pct_error_",
    "agent_citation_recall_extracted",
)


def dev_metric_allowed(metric: str) -> bool:
    """True for a metric the dev label is allowed to carry. issue_recall_
    is extracted-facts-only here: the page's patterns-detected figure
    reads the extracted rows, and the truth-mode ones would only restate
    the generator's own planting."""
    if metric.startswith("issue_recall_"):
        return metric.endswith("_extracted")
    return metric.startswith(DEV_METRIC_PREFIXES)


def filter_rows_for_label(
    rows: dict[str, tuple[int, int]], dataset_label: str
) -> dict[str, tuple[int, int]]:
    if dataset_label == DATASET_LABELS[HELDOUT_SEED]:
        return rows
    return {m: v for m, v in rows.items() if dev_metric_allowed(m)}


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _assessments_for_stage(
    seed: int, facts_source: str, stage: str, processor_ids: list[str]
) -> dict[str, dict]:
    result = {}
    for pid in processor_ids:
        assessments = cache.get_processor_assessments(seed, facts_source, pid)
        if assessments and assessments.get(stage):
            result[pid] = assessments[stage]
    return result


def _stability_run_paths(seed: int) -> list[Path]:
    runs_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "agent_probe_runs"
    return sorted(runs_dir.glob("no_thinking_extracted_run*.json"))


def compute_metrics(seed: int, bq_client) -> dict[str, tuple[int, int]]:
    """Returns {metric_name: (numerator, denominator)}. Assumes
    settings.bq_dataset already points at the eval dataset — this function
    only reads, never writes or toggles settings itself."""
    ground_truth = load_ground_truth(seed)
    processor_ids = [p["processor_id"] for p in ground_truth["processors"]]
    rows: dict[str, tuple[int, int]] = {}

    # Key-field extraction accuracy (T6's existing metric, on seed 7).
    extracted_rows = _fetch_bq_rows(
        bq_client,
        "extracted_facts",
        "doc_id, processor_id, field_name, printed_value",
        seed,
        None,
    )
    overall = ev.extraction_field_accuracy(extracted_rows, ground_truth["documents"])["overall"]
    rows["key_field_read_accuracy"] = (overall["correct"], overall["total"])

    for facts_source in (TRUTH, EXTRACTED):
        check_results_by_processor = {
            pid: cache.get_check_results(seed, facts_source, pid) for pid in processor_ids
        }
        findings_by_processor = {
            pid: cache.get_findings(seed, facts_source, pid) for pid in processor_ids
        }

        for issue_code in sorted(ev.CHECK_IDS_BY_ISSUE_TYPE):
            r = ev.issue_type_recall(check_results_by_processor, ground_truth, issue_code)
            rows[f"issue_recall_{issue_code}_{facts_source}"] = (
                r["numerator"],
                r["denominator"],
            )

        fp = ev.finding_precision_checks(check_results_by_processor, ground_truth)
        rows[f"finding_precision_checks_{facts_source}"] = (fp["numerator"], fp["denominator"])

        ff_clean = ev.false_flags_on_clean(
            check_results_by_processor, findings_by_processor, ground_truth
        )
        rows[f"false_flags_clean_processors_{facts_source}"] = (
            ff_clean["numerator"],
            ff_clean["denominator"],
        )
        ff_hard = ev.false_flags_on_hard_negatives(
            check_results_by_processor, findings_by_processor, ground_truth
        )
        rows[f"false_flags_hard_negatives_{facts_source}"] = (
            ff_hard["numerator"],
            ff_hard["denominator"],
        )

        agent_metrics = ev.agent_citation_metrics(findings_by_processor, ground_truth)
        rows[f"agent_citation_recall_{facts_source}"] = (
            agent_metrics["recall"]["numerator"],
            agent_metrics["recall"]["denominator"],
        )
        rows[f"agent_citation_precision_{facts_source}"] = (
            agent_metrics["precision"]["numerator"],
            agent_metrics["precision"]["denominator"],
        )

        # Whether a planted F5/F7 missed by its deterministic check at
        # least surfaced as a review flag — the real (extracted-facts)
        # measurement only; truth-mode's ground-truth shortcut doesn't
        # exercise the agent the same way.
        if facts_source == EXTRACTED:
            for issue_code in ("F5", "F7"):
                missed = ev.missed_planted_processors(
                    check_results_by_processor, ground_truth, issue_code
                )
                surfaced = ev.issue_surfaced_as_review_flag(missed, findings_by_processor)
                rows[f"issue_surfaced_as_review_flag_{issue_code}"] = (
                    surfaced["numerator"],
                    surfaced["denominator"],
                )

        for stage in ("checks_only", "full"):
            assessments = _assessments_for_stage(seed, facts_source, stage, processor_ids)
            rb = ev.risk_band_accuracy(assessments, ground_truth)
            rows[f"risk_band_accuracy_{stage}_{facts_source}"] = (
                rb["numerator"],
                rb["denominator"],
            )
            tv = ev.verifiable_t_error(assessments, ground_truth)
            rows[f"unverifiable_t_abs_error_kg_{stage}_{facts_source}"] = (
                tv["abs_error_kg"],
                1,
            )
            rows[f"unverifiable_t_pct_error_{stage}_{facts_source}"] = (
                tv["pct_error_micro"],
                1_000_000,
            )

    # Run-to-run stability, cost and latency — from the 3 independent
    # extracted-mode probe runs' own saved JSON (see module docstring).
    run_paths = _stability_run_paths(seed)
    if len(run_paths) >= 2:
        records = [json.loads(p.read_text(encoding="utf-8")) for p in run_paths]
        processors_by_run = [r["processors"] for r in records]
        agreement = ev.pooled_run_to_run_agreement(processors_by_run)
        rows["finding_set_agreement"] = (agreement["numerator"], agreement["denominator"])

        rb_stability = ev.risk_band_stability(processors_by_run)
        rows["risk_band_stability"] = (rb_stability["numerator"], rb_stability["denominator"])
        vt_stability = ev.unverifiable_t_stability(processors_by_run)
        rows["unverifiable_t_stability"] = (
            vt_stability["numerator"],
            vt_stability["denominator"],
        )

        total_cost_usd = sum(
            estimate_cost_usd(c["input_tokens"], c["output_tokens"], c["thinking_tokens"])
            for r in records
            for c in r["call_log"]
        )
        total_latency_ms = sum(c.get("latency_ms") or 0.0 for r in records for c in r["call_log"])
        total_processor_runs = sum(len(r["processors"]) for r in records)
        if total_processor_runs:
            rows["agent_cost_micro_usd_per_processor"] = (
                round(total_cost_usd / total_processor_runs * 1_000_000),
                1,
            )
            rows["agent_latency_ms_per_processor"] = (
                round(total_latency_ms / total_processor_runs),
                1,
            )
    else:
        print(
            f"Skipping stability/cost/latency metrics: found {len(run_paths)} saved "
            "no_thinking_extracted_run*.json file(s), need >= 2 — run "
            f"scripts/probe_agent_thinking.py --seed {seed} --facts-source extracted "
            "--configs no_thinking --runs-per-config 3 first."
        )

    return rows


def _print_summary(rows: dict[str, tuple[int, int]]) -> None:
    print(f"\n{'metric':42s} {'numerator':>12s} {'denominator':>12s} {'value':>10s}")
    for metric in sorted(rows):
        numerator, denominator = rows[metric]
        value = f"{numerator / denominator:.4f}" if denominator else "n/a"
        print(f"{metric:42s} {numerator:12d} {denominator:12d} {value:>10s}")


def delete_label_metrics(client, dataset_label: str, metrics: list[str]) -> None:
    """One DELETE for every metric about to be rewritten, scoped to this
    dataset_label.

    Deliberately NOT a loop over bq.delete_eval_metrics: that issues one
    DML statement per metric, and BigQuery caps table update operations
    at a handful per ten seconds per table — 21 (dev) or 44 (held-out)
    back-to-back DELETEs trip `429 Exceeded rate limits: too many table
    update operations for this table` and the load job that follows is
    rejected, leaving the label's rows deleted but not rewritten. One
    DELETE plus one load job is two operations, well inside the quota.

    bq.delete_by_ids can't be used here: it matches on the id column
    alone, with no dataset_label predicate, so it would also delete the
    identically-named heldout rows. The table reference is built the same
    way app/store/bq.py builds it, from the same settings, rather than
    reaching into its private helper."""
    if not metrics:
        return
    table_ref = f"{settings.gcp_project}.{settings.bq_dataset}.eval_metrics"
    query = (
        f"DELETE FROM `{table_ref}` "
        "WHERE dataset_label = @dataset_label AND metric IN UNNEST(@metrics)"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("dataset_label", "STRING", dataset_label),
            bigquery.ArrayQueryParameter("metrics", "STRING", metrics),
        ]
    )
    client.query(query, job_config=job_config, location=settings.vertex_location).result()


def build_rows(
    rows: dict[str, tuple[int, int]], git_commit: str | None, dataset_label: str
) -> list[dict]:
    computed_at = datetime.now(UTC).isoformat()
    return [
        {
            "dataset_label": dataset_label,
            "metric": metric,
            "numerator": numerator,
            "denominator": denominator,
            "computed_at": computed_at,
            "source_script": SOURCE_SCRIPT,
            "git_commit": git_commit,
        }
        for metric, (numerator, denominator) in rows.items()
    ]


def write_rows(
    write_client, rows: dict[str, tuple[int, int]], git_commit: str | None, dataset_label: str
) -> list[dict]:
    """Delete-then-load, idempotent on (dataset_label, metric)."""
    out_rows = build_rows(rows, git_commit, dataset_label)
    delete_label_metrics(write_client, dataset_label, [r["metric"] for r in out_rows])
    bq.load_rows(write_client, "eval_metrics", out_rows)
    return out_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=HELDOUT_SEED, choices=sorted(DATASET_LABELS))
    parser.add_argument(
        "--eval-dataset",
        default="epr_eval",
        help="BigQuery dataset the seed's pipeline output was loaded into (default: epr_eval). "
        "Read-only. For --seed 42 (the development set) pass the live dataset, epr — this "
        "script's only writes are to eval_metrics, scoped to (dataset_label, metric).",
    )
    args = parser.parse_args()

    dataset_label = DATASET_LABELS[args.seed]
    live_dataset = settings.bq_dataset
    bq_client = bq.get_client()

    settings.bq_dataset = args.eval_dataset
    print(f"Reading seed {args.seed} from dataset {settings.bq_dataset!r} (read-only)...")
    all_rows = compute_metrics(args.seed, bq_client)
    rows = filter_rows_for_label(all_rows, dataset_label)
    skipped = len(all_rows) - len(rows)
    if skipped:
        print(
            f"Computed {len(all_rows)} metric(s); writing {len(rows)} for {dataset_label!r} and "
            f"skipping {skipped} not measured on the development set (see DEV_METRIC_PREFIXES)."
        )

    settings.bq_dataset = live_dataset
    print(
        f"\nWriting {len(rows)} metric(s) to dataset {settings.bq_dataset!r}.eval_metrics "
        f"(dataset_label={dataset_label!r})..."
    )
    written = write_rows(bq_client, rows, _git_commit(), dataset_label)

    _print_summary(rows)
    print(f"\nWrote {len(written)} rows to {settings.gcp_project}.{live_dataset}.eval_metrics")


if __name__ == "__main__":
    main()
