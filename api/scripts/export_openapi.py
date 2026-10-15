"""Writes the API's OpenAPI schema to api/openapi.json, so T12 (web) can
generate TypeScript types from it, and to web/lib/openapi.json, which the
/api-docs page renders.

Two copies, deliberately. web/Dockerfile builds with `COPY . .` from
web/, so api/ is not in the web image's build context: a page importing
"../api/openapi.json" compiles locally and fails the Cloud Run build.
The mirrored copy inside web/ is the same bytes, and
tests/test_openapi_schema.py fails if either copy drifts from the app.

Local only — importing app.main.app constructs the FastAPI app and
registers its routes, but makes no GCP call (BigQuery/GCS/Vertex clients
are only created inside request handlers, not at import time). Safe to run
without real credentials.

Usage: uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.main import app

API_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATHS = (
    API_ROOT / "openapi.json",
    API_ROOT.parent / "web" / "lib" / "openapi.json",
)


def main() -> None:
    schema = app.openapi()
    serialized = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    for output_path in OUTPUT_PATHS:
        output_path.write_text(serialized, encoding="utf-8")
        print(f"wrote {output_path} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
