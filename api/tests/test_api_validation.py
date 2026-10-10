"""T13.8: path/query parameter validation and the uniform error envelope.

A malformed processor_id/doc_id/brand_id/lang must 422 before any cache
lookup runs — no monkeypatching needed, since FastAPI rejects it at the
routing layer. Every error body (422/404/401/...) must be shaped
{"error": "<message>", "request_id": "<uuid>"}, never a raw FastAPI
{"detail": ...} or a stack trace.
"""

import re

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _assert_error_envelope(body: dict) -> None:
    assert set(body.keys()) == {"error", "request_id"}
    assert isinstance(body["error"], str) and body["error"]
    assert _UUID_RE.match(body["request_id"])


def test_bad_processor_id_422(api_client):
    response = api_client.get("/processors/not-a-processor")

    assert response.status_code == 422
    _assert_error_envelope(response.json())


def test_bad_doc_id_422(api_client):
    response = api_client.get("/documents/not-a-doc/facts")

    assert response.status_code == 422
    _assert_error_envelope(response.json())


def test_bad_brand_id_422(api_client):
    response = api_client.get("/portfolio/not-a-brand")

    assert response.status_code == 422
    _assert_error_envelope(response.json())


def test_bad_lang_422(api_client):
    response = api_client.get("/processors/PWP-08/memo?lang=fr")

    assert response.status_code == 422
    _assert_error_envelope(response.json())


def test_valid_ids_are_not_rejected_by_validation(api_client, monkeypatch):
    """A well-formed ID must reach the route body (and 404 there, since
    nothing is mocked) rather than being rejected by the path pattern."""
    from app.store import cache

    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: None)
    response = api_client.get("/processors/PWP-01")

    assert response.status_code == 404
    _assert_error_envelope(response.json())


def test_404_error_envelope_shape(api_client, monkeypatch):
    from app.store import cache

    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: None)
    response = api_client.get("/processors/PWP-01")

    body = response.json()
    _assert_error_envelope(body)
    assert body["error"] == "processor not found"
