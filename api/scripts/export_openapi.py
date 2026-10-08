"""Writes the API's OpenAPI schema to api/openapi.json, so T12 (web) can
generate TypeScript types from it.

Local only — importing app.main.app constructs the FastAPI app and
registers its routes, but makes no GCP call (BigQuery/GCS/Vertex clients
are only created inside request handlers, not at import time). Safe to run
without real credentials.

Usage: uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
