"""Smoke test: BigQuery — a trivial query in asia-south1.

Does not depend on the `epr` dataset or any tables (those arrive in T5).
Run: uv run python scripts/smoke/smoke_bq.py
"""

import sys

from google.cloud import bigquery

from app.config import settings


def main() -> int:
    print("--- smoke_bq: SELECT 1 in asia-south1 ---")
    try:
        client = bigquery.Client(project=settings.gcp_project)
        job = client.query("SELECT 1 AS ok", location=settings.vertex_location)
        rows = list(job.result())
        print(f"rows: {rows}")
        if len(rows) == 1 and rows[0]["ok"] == 1:
            print("smoke_bq: PASS")
            return 0
        print(f"smoke_bq: FAIL — unexpected result {rows!r}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"smoke_bq: FAIL — {exc!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
