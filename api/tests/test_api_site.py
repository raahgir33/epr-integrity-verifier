"""Tests for GET /processors/{id}/site and GET /site-images/{id}."""

from app.store import cache, gcs

_SITE_ROW = {
    "processor_id": "PWP-09",
    "status": "warn",
    "severity": "soft",
    "measured": None,
    "threshold": 10.0,
    "building_count": 0,
    "total_footprint_m2": 0.0,
    "thumbnail_gcs_path": "seed-42/site/PWP-09.png",
    "thumb_bbox_w": 76.596123,
    "thumb_bbox_s": 27.546123,
    "thumb_bbox_e": 76.598123,
    "thumb_bbox_n": 27.548123,
    "thumb_crs": "EPSG:3857",
    "explanation": "no building footprint detected",
}


def test_site_happy_path_rounds_bbox_to_2dp(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(cache, "get_site_assessment", lambda seed, pid: _SITE_ROW)

    response = api_client.get("/processors/PWP-09/site")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "warn"
    assert body["thumb_bbox"] == [76.6, 27.55, 76.6, 27.55]
    assert "Sentinel" in body["sentinel_attribution"]
    assert "Open Buildings" in body["open_buildings_attribution"]
    assert "synthetic" in body["disclaimer"].lower()


def test_site_404_unknown_processor(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: None)

    response = api_client.get("/processors/PWP-99/site")

    assert response.status_code == 404


def test_site_404_no_assessment_yet(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(cache, "get_site_assessment", lambda seed, pid: None)

    response = api_client.get("/processors/PWP-01/site")

    assert response.status_code == 404


def test_site_image_streams_bytes(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_site_assessment", lambda seed, pid: _SITE_ROW)
    monkeypatch.setattr(gcs, "get_client", lambda: object())
    monkeypatch.setattr(gcs, "download_bytes", lambda client, bucket, path: b"\x89PNG-fake")

    response = api_client.get("/site-images/PWP-09")

    assert response.status_code == 200
    assert response.content == b"\x89PNG-fake"
    assert response.headers["content-type"] == "image/png"


def test_site_image_404_missing_thumbnail(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_site_assessment", lambda seed, pid: None)

    response = api_client.get("/site-images/PWP-99")

    assert response.status_code == 404
