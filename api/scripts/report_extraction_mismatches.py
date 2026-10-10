"""Developer-run, read-only report: lists every key-field extraction
mismatch (doc_id, field_name, extracted value, ground-truth value) for a
seed, plus the accuracy figure by document type and overall, formatted to
2 decimal places (never rounded up to 100.00% unless every field
matched — app/eval/evaluate.py's format_accuracy_pct).

A post-hoc read of extracted_facts (no Gemini call) — run any time after
--stage extract has completed, to recover the per-field detail
--stage extract's own one-shot console report doesn't persist anywhere.

--write-bq (T13.6) additionally writes the overall accuracy to the
eval_metrics table — GET /stats's field_read_accuracy_pct reads it back
(T14's real /evaluation endpoint doesn't exist yet, and ground_truth.json,
what this number is measured against, never ships to the deployed
container, so this script is the only place that can compute it).

Run by the developer — never by the agent (reads/writes real BigQuery).

Usage: uv run python scripts/report_extraction_mismatches.py --seed 42
       uv run python scripts/report_extraction_mismatches.py --seed 42 --processor PWP-02
       uv run python scripts/report_extraction_mismatches.py --seed 42 --write-bq
"""

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.eval.evaluate import (
    extraction_field_accuracy,
    extraction_field_mismatches,
    format_accuracy_pct,
)
from app.store import bq
from scripts.run_pipeline import _fetch_bq_rows, load_ground_truth

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_METRIC = "key_field_read_accuracy"


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_accuracy_metric(
    bq_client, seed: int, overall: dict, git_commit: str | None = None
) -> dict:
    """Builds and writes the one eval_metrics row --write-bq produces.
    Separated from main() so it's unit-testable with a fake bq client,
    without going through argv parsing or a real ground_truth.json read.
    Returns the row written, for the test/caller to assert against."""
    row = {
        "dataset_label": f"dev-seed{seed}",
        "metric": EVAL_METRIC,
        "numerator": overall["correct"],
        "denominator": overall["total"],
        "computed_at": datetime.now(UTC).isoformat(),
        "source_script": "scripts/report_extraction_mismatches.py",
        "git_commit": git_commit,
    }
    bq.delete_eval_metrics(bq_client, row["dataset_label"], row["metric"])
    bq.load_rows(bq_client, "eval_metrics", [row])
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--processor", help="Only report this processor_id (e.g. PWP-02)")
    parser.add_argument(
        "--write-bq",
        action="store_true",
        help="Write the overall accuracy to the eval_metrics table (dataset_label dev-seed<seed>)",
    )
    args = parser.parse_args()
    seed = args.seed
    if args.write_bq and args.processor:
        parser.error("--write-bq reports the whole dataset's accuracy — drop --processor")

    ground_truth = load_ground_truth(seed)
    documents = ground_truth["documents"]
    if args.processor:
        documents = [d for d in documents if d["processor_id"] == args.processor]

    bq_client = bq.get_client()
    extracted_rows = _fetch_bq_rows(
        bq_client,
        "extracted_facts",
        "doc_id, processor_id, field_name, printed_value",
        seed,
        args.processor,
    )

    mismatches = extraction_field_mismatches(extracted_rows, documents)
    scope = f", processor {args.processor}" if args.processor else ""
    print(f"Mismatches for seed {seed}{scope}:")
    if not mismatches:
        print("  none")
    for m in mismatches:
        print(
            f"  {m['doc_id']} ({m['processor_id']}, {m['doc_type']}).{m['field_name']}: "
            f"extracted={m['extracted_value']!r} truth={m['truth_value']!r}"
        )

    report = extraction_field_accuracy(extracted_rows, documents)
    print("\nField accuracy by document type (key numeric/ID fields only):")
    for doc_type, stats in sorted(report.items()):
        if doc_type == "overall":
            continue
        acc = format_accuracy_pct(stats["correct"], stats["total"])
        print(f"  {doc_type:20s} {stats['correct']:4d}/{stats['total']:<4d}  {acc}")

    overall = report["overall"]
    overall_acc = format_accuracy_pct(overall["correct"], overall["total"])
    print(f"\nOverall: {overall['correct']}/{overall['total']} ({overall_acc})")

    if args.write_bq:
        row = write_accuracy_metric(bq_client, seed, overall, git_commit=_git_commit())
        print(
            f"\nwrote eval_metrics: {row['dataset_label']}/{row['metric']} = "
            f"{row['numerator']}/{row['denominator']}"
        )


if __name__ == "__main__":
    main()
