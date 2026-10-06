"""Smoke test: Cloud Storage — upload, read back, delete a test object.

Run: uv run python scripts/smoke/smoke_gcs.py
"""

import sys
import uuid

from google.cloud import storage

from app.config import settings


def main() -> int:
    print("--- smoke_gcs: upload, read back, delete ---")
    if not settings.dossier_bucket:
        print("smoke_gcs: FAIL — DOSSIER_BUCKET is not set in the environment")
        return 1

    blob_name = f"smoke-test/{uuid.uuid4()}.txt"
    content = b"SYNTHETIC - DEMO DATA - epr-integrity smoke test"

    try:
        client = storage.Client(project=settings.gcp_project)
        bucket = client.bucket(settings.dossier_bucket)
        blob = bucket.blob(blob_name)

        blob.upload_from_string(content, content_type="text/plain")
        print(f"uploaded: gs://{settings.dossier_bucket}/{blob_name}")

        read_back = blob.download_as_bytes()
        if read_back != content:
            print(f"smoke_gcs: FAIL — content mismatch, got {read_back!r}")
            return 1
        print("read back matches")

        blob.delete()
        print("deleted")

        print("smoke_gcs: PASS")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"smoke_gcs: FAIL — {exc!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
