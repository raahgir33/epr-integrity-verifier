"""Shared fixtures for app/main.py's endpoint tests (test_api_*.py)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import cache


@pytest.fixture
def api_client(monkeypatch):
    """A TestClient with the app's lifespan triggered (so startup/shutdown
    actually run), but cache.preload AND cache.check_consistency replaced
    with no-ops — individual tests monkeypatch the specific app.store.cache
    read functions their endpoint needs instead of relying on preload/the
    consistency check populating or scanning real or fake data. Never
    touches real BigQuery/GCS.

    Also clears the module-level file caches (A2: get_document_file's LRU,
    get_site_image_bytes' eager dict) before and after — without this, a
    doc_id/processor_id cached by one test's fake gcs bytes would still be
    "cached" (and so never re-fetched/re-validated) in a later test that
    reuses the same id with different fakes."""
    monkeypatch.setattr(cache, "preload", lambda seed, facts_source: None)
    monkeypatch.setattr(
        cache, "check_consistency", lambda seed, facts_source: {"ok": True, "mismatches": []}
    )
    cache._document_file_cache.clear()
    cache._document_file_cache_bytes = 0
    cache._site_image_cache.clear()
    with TestClient(app) as client:
        yield client
    cache._document_file_cache.clear()
    cache._document_file_cache_bytes = 0
    cache._site_image_cache.clear()
