"""Cloud Storage client: upload, download, stream file bytes.

No signed URLs — they need extra IAM permissions on Cloud Run. The API
streams file bytes through its own route instead.
"""

import threading
from pathlib import Path

from google.cloud import storage

from app.config import settings

_client: storage.Client | None = None
_client_lock = threading.Lock()


def get_client() -> storage.Client:
    """Memoized, same reasoning as app/store/bq.py's get_client()."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = storage.Client(project=settings.gcp_project)
    return _client


def upload_file(client: storage.Client, bucket_name: str, blob_path: str, local_path: Path) -> None:
    bucket = client.bucket(bucket_name)
    bucket.blob(blob_path).upload_from_filename(str(local_path))


def download_bytes(client: storage.Client, bucket_name: str, blob_path: str) -> bytes:
    bucket = client.bucket(bucket_name)
    return bucket.blob(blob_path).download_as_bytes()


def upload_bytes(
    client: storage.Client, bucket_name: str, blob_path: str, data: bytes, content_type: str
) -> None:
    bucket = client.bucket(bucket_name)
    bucket.blob(blob_path).upload_from_string(data, content_type=content_type)
