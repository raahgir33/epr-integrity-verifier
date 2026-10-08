"""Developer-run, read-only report: lists every key-field extraction
mismatch (doc_id, field_name, extracted value, ground-truth value) for a
seed, plus the accuracy figure by document type and overall, formatted to
2 decimal places (never rounded up to 100.00% unless every field
matched — app/eval/evaluate.py's format_accuracy_pct).

A post-hoc read of extracted_facts (no Gemini call) — run any time after
--stage extract has completed, to recover the per-field detail
--stage extract's own one-shot console report doesn't persist anywhere.

Run by the developer — never by the agent (reads real BigQuery).

Usage: uv run python scripts/report_extraction_mismatches.py --seed 42
       uv run python scripts/report_extraction_mismatches.py --seed 42 --processor PWP-02
"""

import argparse

from app.eval.evaluate import (
    extraction_field_accuracy,
    extraction_field_mismatches,
    format_accuracy_pct,
)
from app.store import bq
from scripts.run_pipeline import _fetch_bq_rows, load_ground_truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--processor", help="Only report this processor_id (e.g. PWP-02)")
    args = parser.parse_args()
    seed = args.seed

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


if __name__ == "__main__":
    main()
