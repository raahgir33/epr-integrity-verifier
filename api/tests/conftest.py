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
    touches real BigQuery/GCS."""
    monkeypatch.setattr(cache, "preload", lambda seed, facts_source: None)
    monkeypatch.setattr(
        cache, "check_consistency", lambda seed, facts_source: {"ok": True, "mismatches": []}
    )
    with TestClient(app) as client:
        yield client
