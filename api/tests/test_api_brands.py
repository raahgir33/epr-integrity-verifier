"""Tests for GET /brands (T12: lets the web app offer a brand picker for
/portfolio, which otherwise only has GET /portfolio/{brand_id})."""

import json
from pathlib import Path

from app.store import cache

REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_DIR = REPO_ROOT / "data" / "synthetic" / "seed-42"


def test_brands_sorted_by_brand_id(api_client, monkeypatch):
    monkeypatch.setattr(
        cache,
        "_brands",
        lambda seed: [
            {"brand_id": "BRAND-02", "name": "Konkan Beverages Pvt. Ltd."},
            {"brand_id": "BRAND-01", "name": "Himalaya FreshFoods Ltd."},
        ],
    )

    response = api_client.get("/brands")

    assert response.status_code == 200
    body = response.json()
    assert [b["brand_id"] for b in body["brands"]] == ["BRAND-01", "BRAND-02"]


def test_brands_matches_committed_seed_42_data(api_client, monkeypatch):
    """Cross-checks against the real, committed seed-42 manifest (no
    BigQuery) — same pattern as test_api_leak_guard.py's _SEED_DIR reads."""
    real_brands = json.loads((_SEED_DIR / "brands.json").read_text())
    monkeypatch.setattr(cache, "_brands", lambda seed: real_brands)

    response = api_client.get("/brands")

    assert response.status_code == 200
    body = response.json()
    assert len(body["brands"]) == 3
    assert {b["brand_id"] for b in body["brands"]} == {b["brand_id"] for b in real_brands}
    assert sorted(b["brand_id"] for b in body["brands"]) == [b["brand_id"] for b in body["brands"]]
