"""Precompute pipeline: extract -> normalize -> checks -> site -> agents.
Only --stage extract is implemented so far; T7-T10 add the rest.

Run by the developer — never by the agent (hits real Vertex AI, BigQuery,
Cloud Storage).

Usage: uv run python scripts/run_pipeline.py --seed 42 --stage extract
       uv run python scripts/run_pipeline.py --seed 42 --stage extract --processor PWP-01
"""

import argparse
import json
from pathlib import Path

from app.config import settings
from app.eval.evaluate import extraction_field_accuracy
from app.ingest.extract import extract_all, facts_to_field_rows
from app.llm import GeminiClient
from app.store import bq, gcs
from scripts.load_dossiers import document_gcs_path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCURACY_GATE = 0.90


def load_ground_truth(seed: int) -> dict:
    path = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "ground_truth.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_extract(seed: int, processor_filter: str | None) -> None:
    ground_truth = load_ground_truth(seed)
    documents = ground_truth["documents"]
    if processor_filter:
        documents = [d for d in documents if d["processor_id"] == processor_filter]
    if not documents:
        print(
            f"No documents found for seed {seed}"
            + (f", processor {processor_filter}" if processor_filter else "")
        )
        return

    docs_with_paths = [dict(d, gcs_path=document_gcs_path(seed, d)) for d in documents]

    print(f"Extracting {len(docs_with_paths)} documents (concurrency 4)...")
    llm_client = GeminiClient()
    gcs_client = gcs.get_client()
    results = extract_all(llm_client, gcs_client, settings.dossier_bucket, docs_with_paths)

    extracted_facts_rows = []
    extraction_results_rows = []
    ok_count = 0
    failed_count = 0
    for result in results:
        base = {
            "seed": seed,
            "doc_id": result["doc_id"],
            "processor_id": result["processor_id"],
            "doc_type": result["doc_type"],
        }
        if result["status"] == "ok":
            ok_count += 1
            for field_row in facts_to_field_rows(result["facts"]):
                extracted_facts_rows.append({**base, **field_row})
            extraction_results_rows.append({**base, "status": "ok", "error_message": None})
        else:
            failed_count += 1
            extraction_results_rows.append(
                {**base, "status": "failed", "error_message": result["error"]}
            )

    print(f"Extraction done: {ok_count} ok, {failed_count} failed.")

    bq_client = bq.get_client()
    bq.delete_by_seed(bq_client, "extracted_facts", seed)
    bq.load_rows(bq_client, "extracted_facts", extracted_facts_rows)
    bq.delete_by_seed(bq_client, "extraction_results", seed)
    bq.load_rows(bq_client, "extraction_results", extraction_results_rows)

    call_log = [{"seed": seed, **record} for record in llm_client.flush_call_log()]
    bq.load_rows(bq_client, "llm_calls", call_log)

    report = extraction_field_accuracy(extracted_facts_rows, documents)
    print("\nField accuracy by document type (key numeric/ID fields only):")
    for doc_type, stats in sorted(report.items()):
        if doc_type == "overall":
            continue
        acc = f"{stats['accuracy']:.1%}" if stats["accuracy"] is not None else "n/a"
        print(f"  {doc_type:20s} {stats['correct']:4d}/{stats['total']:<4d}  {acc}")

    overall = report["overall"]
    overall_acc = overall["accuracy"] or 0.0
    print(f"\nOverall: {overall['correct']}/{overall['total']} ({overall_acc:.1%})")
    gate_status = "PASS" if overall_acc >= ACCURACY_GATE else "FAIL"
    print(f"Gate (>= {ACCURACY_GATE:.0%}): {gate_status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run precompute pipeline stages.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--stage", choices=["extract"], required=True)
    parser.add_argument("--processor", help="Only process this processor_id (e.g. PWP-01)")
    args = parser.parse_args()

    if args.stage == "extract":
        run_extract(args.seed, args.processor)


if __name__ == "__main__":
    main()
