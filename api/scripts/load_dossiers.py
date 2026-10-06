"""Uploads a generated seed's documents to Cloud Storage and registers
processors, suppliers, brands, documents and certificates in BigQuery.
Idempotent: re-running deletes this seed's rows first, then reloads, and
GCS blob uploads simply overwrite the same path — row/object counts never
grow on repeat runs.

Run by the developer — never by the agent (hits real Google Cloud).

Usage: uv run python scripts/load_dossiers.py --seed 42
"""

import argparse
import csv
import json
from pathlib import Path

from app.config import settings
from app.store import bq, gcs

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_ddmmyyyy(printed: str) -> str:
    """DD/MM/YYYY -> ISO YYYY-MM-DD, for BigQuery DATE columns."""
    day, month, year = printed.split("/")
    return f"{year}-{month}-{day}"


def document_local_filename(doc: dict) -> str:
    ext = "png" if doc["doc_type"] == "weighbridge_slip" else "pdf"
    return f"{doc['doc_id']}.{ext}"


def document_mime_type(doc: dict) -> str:
    return "image/png" if doc["doc_type"] == "weighbridge_slip" else "application/pdf"


def document_gcs_path(seed: int, doc: dict) -> str:
    return f"seed-{seed}/documents/{doc['processor_id']}/{document_local_filename(doc)}"


def processor_to_row(seed: int, p: dict) -> dict:
    return {
        "seed": seed,
        "processor_id": p["processor_id"],
        "name": p["name"],
        "type": p["type"],
        "permitted_categories": p["permitted_categories"],
        "capacity_t_per_year": p["capacity_t_per_year"],
        "consent_no": p["consent_no"],
        "consent_valid_from": parse_ddmmyyyy(p["consent_valid_from"]),
        "consent_valid_to": parse_ddmmyyyy(p["consent_valid_to"]),
        "registration_no": p["registration_no"],
        "gstin": p["gstin"],
        "address": p["address"],
        "lat": p["lat"],
        "lon": p["lon"],
        "site_validated": p["site_validated"],
        "issue_types": p["issue_types"],
        "hard_negatives": p["hard_negatives"],
    }


def supplier_to_row(seed: int, s: dict) -> dict:
    return {
        "seed": seed,
        "supplier_id": s["supplier_id"],
        "name": s["name"],
        "gstin": s["gstin"],
        "pin_code": s["pin_code"],
        "lat": s["lat"],
        "lon": s["lon"],
    }


def brand_to_row(seed: int, b: dict) -> dict:
    return {"seed": seed, "brand_id": b["brand_id"], "name": b["name"]}


def document_to_row(seed: int, doc: dict) -> dict:
    return {
        "seed": seed,
        "doc_id": doc["doc_id"],
        "processor_id": doc["processor_id"],
        "doc_type": doc["doc_type"],
        "lang": doc["lang"],
        "gcs_path": document_gcs_path(seed, doc),
        "mime_type": document_mime_type(doc),
    }


def certificate_row_from_csv_row(seed: int, row: dict) -> dict:
    return {
        "seed": seed,
        "certificate_id": row["certificate_id"],
        "processor_id": row["processor_id"],
        "brand_id": row["brand_id"],
        "category": row["category"],
        "quantity_t": float(row["quantity_t"]),
        "generation_date": parse_ddmmyyyy(row["generation_date"]),
        "period_month": row["period_month"],
    }


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_certificates_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload documents to GCS and register manifests in BigQuery."
    )
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    seed = args.seed

    seed_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}"
    processors = load_json(seed_dir / "processors.json")
    suppliers = load_json(seed_dir / "suppliers.json")
    brands = load_json(seed_dir / "brands.json")
    ground_truth = load_json(seed_dir / "ground_truth.json")
    certificates = load_certificates_csv(seed_dir / "certificates.csv")
    documents = ground_truth["documents"]

    gcs_client = gcs.get_client()
    print(
        f"Uploading {len(documents)} documents to "
        f"gs://{settings.dossier_bucket}/seed-{seed}/documents/ ..."
    )
    for doc in documents:
        local_path = seed_dir / "documents" / doc["processor_id"] / document_local_filename(doc)
        gcs.upload_file(
            gcs_client, settings.dossier_bucket, document_gcs_path(seed, doc), local_path
        )
    print("Upload complete.")

    bq_client = bq.get_client()
    counts: dict[str, int] = {}

    bq.delete_by_seed(bq_client, "processors", seed)
    counts["processors"] = bq.load_rows(
        bq_client, "processors", [processor_to_row(seed, p) for p in processors]
    )

    bq.delete_by_seed(bq_client, "suppliers", seed)
    counts["suppliers"] = bq.load_rows(
        bq_client, "suppliers", [supplier_to_row(seed, s) for s in suppliers]
    )

    bq.delete_by_seed(bq_client, "brands", seed)
    counts["brands"] = bq.load_rows(bq_client, "brands", [brand_to_row(seed, b) for b in brands])

    bq.delete_by_seed(bq_client, "documents", seed)
    counts["documents"] = bq.load_rows(
        bq_client, "documents", [document_to_row(seed, doc) for doc in documents]
    )

    bq.delete_by_seed(bq_client, "certificates", seed)
    counts["certificates"] = bq.load_rows(
        bq_client,
        "certificates",
        [certificate_row_from_csv_row(seed, row) for row in certificates],
    )

    print("Row counts loaded:")
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
