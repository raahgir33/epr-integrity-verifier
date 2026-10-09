"""Uploads T13's demo-extra documents (api/scripts/generate_demo_extra_docs.py's
output, data/synthetic/seed-<seed>/demo_extra/) to Cloud Storage and
registers them in the `documents` BigQuery table — deliberately with NO
`extracted_facts` rows, so DocumentListItem.extraction_status reads
"not_extracted" until the live event path (app/events/run_processor.py)
runs Gemini extraction on them for real, at demo time.

Also loads data/synthetic/seed-<seed>/demo_batches.json itself into a new
`demo_batches` BigQuery table — api/Dockerfile only copies app/ into the
deployed image (neither scripts/ nor data/ ship), so the live event path,
running inside that deployed container, can't read the JSON file off
local disk the way this loader (running on the developer's machine) can.

Idempotent and scoped to exactly these doc_ids (bq.delete_by_ids, never
bq.delete_by_seed — this must never touch the ~714 real document rows for
this seed). Run once, before the first live demo click; re-run safely any
time generate_demo_extra_docs.py's output changes.

Run by the developer — never by the agent (hits real Google Cloud).

Usage: uv run python scripts/load_demo_extra_docs.py --seed 42
"""

import argparse
import json
from pathlib import Path

from app.config import settings
from app.store import bq, gcs

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload T13's demo-extra documents and register them in BigQuery."
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    seed = args.seed

    demo_extra_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "demo_extra"
    manifest_paths = sorted(demo_extra_dir.glob("*/manifest.json"))
    if not manifest_paths:
        print(f"No manifests found under {demo_extra_dir} — run generate_demo_extra_docs.py first.")
        return

    all_docs: list[dict] = []
    for manifest_path in manifest_paths:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        all_docs.extend(manifest["documents"])

    gcs_client = gcs.get_client()
    print(f"Uploading {len(all_docs)} demo-extra document(s) to gs://{settings.dossier_bucket}/...")
    for doc in all_docs:
        local_path = demo_extra_dir / doc["processor_id"] / Path(doc["gcs_path"]).name
        gcs.upload_file(gcs_client, settings.dossier_bucket, doc["gcs_path"], local_path)
        print(f"  {doc['doc_id']} -> gs://{settings.dossier_bucket}/{doc['gcs_path']}")

    bq_client = bq.get_client()
    doc_ids = [d["doc_id"] for d in all_docs]
    bq.delete_by_ids(bq_client, "documents", "doc_id", doc_ids)
    rows = [
        {
            "seed": seed,
            "doc_id": d["doc_id"],
            "processor_id": d["processor_id"],
            "doc_type": d["doc_type"],
            "lang": d["lang"],
            "gcs_path": d["gcs_path"],
            "mime_type": d["mime_type"],
        }
        for d in all_docs
    ]
    count = bq.load_rows(bq_client, "documents", rows)
    print(f"\nRegistered {count} demo-extra document row(s) (no extracted_facts yet).")

    demo_batches_path = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "demo_batches.json"
    demo_batches = json.loads(demo_batches_path.read_text(encoding="utf-8"))
    demo_batch_rows = [{"seed": seed, **b} for b in demo_batches]
    bq.delete_by_seed(bq_client, "demo_batches", seed)
    batch_count = bq.load_rows(bq_client, "demo_batches", demo_batch_rows)
    print(f"Loaded {batch_count} demo_batches row(s).")


if __name__ == "__main__":
    main()
