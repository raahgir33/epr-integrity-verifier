"""Full reset of one seed's downstream BigQuery state and GCS documents,
before a regenerate + reload — so stale pre-fix content (old extractions,
old shipments/checks computed from the previous documents) can never
silently coexist with newly-generated documents.

`load_dossiers.py` already self-cleans `processors`/`suppliers`/`brands`/
`documents`/`certificates` (delete-by-seed then load, T5's idempotency).
What it does NOT touch is every downstream pipeline table, which this
script clears first.

Run by the developer — never by the agent (hits real GCS + BigQuery).

Usage: uv run python scripts/reset_seed_data.py --seed 42
"""

import argparse

from app.config import settings
from app.store import bq, gcs

# llm_calls is deliberately excluded: it's an append-only call-history
# log, not a replaceable snapshot (established T6 decision — see
# docs/PROGRESS.md). processors/suppliers/brands/documents/certificates
# are excluded too: load_dossiers.py already deletes-by-seed and reloads
# them itself.
RESET_TABLES = [
    "shipments",
    "outputs",
    "energy_monthly",
    "check_results",
    "extracted_facts",
    "extraction_results",
    "site_assessments",
    "agent_runs",
    "assessments",
]


def reset_bigquery(seed: int) -> None:
    client = bq.get_client()
    for table in RESET_TABLES:
        bq.delete_by_seed(client, table, seed)
        print(f"  cleared {table} for seed {seed}")


def reset_gcs_documents(seed: int) -> int:
    client = gcs.get_client()
    prefix = f"seed-{seed}/documents/"
    blobs = list(client.list_blobs(settings.dossier_bucket, prefix=prefix))
    for blob in blobs:
        blob.delete()
    return len(blobs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    print(f"Resetting BigQuery tables for seed {args.seed}...")
    reset_bigquery(args.seed)

    print(f"Deleting GCS documents for seed {args.seed}...")
    deleted = reset_gcs_documents(args.seed)
    print(f"  deleted {deleted} object(s) under seed-{args.seed}/documents/")

    print(
        f"\nDone. Next: uv run python scripts/load_dossiers.py --seed {args.seed}, "
        "then re-run --stage normalize/checks/site/extract."
    )


if __name__ == "__main__":
    main()
