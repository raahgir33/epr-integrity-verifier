"""Cloud Storage client: upload, download, stream file bytes.

No signed URLs — they need extra IAM permissions on Cloud Run. The API
streams file bytes through its own route instead.
"""

from pathlib import Path

from google.cloud import storage

from app.config import settings


def get_client() -> storage.Client:
    return storage.Client(project=settings.gcp_project)


def upload_file(client: storage.Client, bucket_name: str, blob_path: str, local_path: Path) -> None:
    bucket = client.bucket(bucket_name)
    bucket.blob(blob_path).upload_from_filename(str(local_path))


def download_bytes(client: storage.Client, bucket_name: str, blob_path: str) -> bytes:
    bucket = client.bucket(bucket_name)
    return bucket.blob(blob_path).download_as_bytes()
