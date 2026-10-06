"""Creates the BigQuery tables this project needs so far. Run by the
developer — never by the agent. Safe to re-run: uses CREATE TABLE IF NOT
EXISTS, so later tasks can add tables to app/store/bq.py's SCHEMAS registry
and re-run this rather than needing a one-shot migration each time.

Usage: uv run python scripts/deploy/create_tables.py
"""

from app.config import settings
from app.store import bq


def main() -> None:
    client = bq.get_client()
    bq.create_tables(client)
    print(f"Dataset: {client.project}.{settings.bq_dataset}")
    print(f"Created/verified tables: {', '.join(bq.SCHEMAS.keys())}")


if __name__ == "__main__":
    main()
