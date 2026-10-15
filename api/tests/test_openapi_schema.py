"""Tests for the published OpenAPI schema.

Two internal endpoints — the admin reset and the Pub/Sub push handler —
are deliberately absent from the schema (`include_in_schema=False`) while
remaining fully functional, so neither the API's own /docs nor the web
app's /api-docs page advertises an operations-only surface. These tests
pin both halves of that: hidden from the schema, and still reachable.

They also guard the two committed copies of the schema against drift.
Nothing regenerates them automatically, and the /api-docs page is
rendered from web/lib/openapi.json, so a route change that skips the
export would silently publish a stale reference.
"""

import json
from pathlib import Path

from app.admin import reset_demo as admin_reset_demo
from app.checks import params as check_params
from app.events import pubsub
from app.main import app
from app.store import cache

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SCHEMA_PATH = REPO_ROOT / "api" / "openapi.json"
WEB_SCHEMA_PATH = REPO_ROOT / "web" / "lib" / "openapi.json"

INTERNAL_PATHS = ("/admin/reset-demo", "/events/certificate-batch")

# Prose that belongs in the code, not in a published description: task
# identifiers, module paths and source filenames. Every public endpoint's
# description was once its handler docstring, which carried all three.
INTERNAL_PROSE = ("docs/", "app/", "scripts/", ".py")


def test_internal_endpoints_are_absent_from_the_schema():
    paths = app.openapi()["paths"]

    for path in INTERNAL_PATHS:
        assert path not in paths, f"{path} must not be published"


def test_hidden_admin_reset_still_rejects_a_bad_token(api_client):
    response = api_client.post("/admin/reset-demo", params={"token": "wrong"})

    assert response.status_code == 401
    assert response.json()["error"] == "invalid push token"


def test_hidden_admin_reset_still_works_with_a_valid_token(api_client, monkeypatch):
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)
    monkeypatch.setattr(admin_reset_demo, "run_reset_live", lambda seed: ["PWP-01"])
    monkeypatch.setattr(cache, "invalidate", lambda key=None: None)
    monkeypatch.setattr(cache, "preload", lambda seed, facts_source: None)

    response = api_client.post("/admin/reset-demo", params={"token": "x"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_hidden_push_endpoint_still_rejects_a_bad_token(api_client):
    response = api_client.post(
        "/events/certificate-batch",
        params={"token": "wrong"},
        json={"message": {"data": "", "messageId": "1"}},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid push token"


def test_hidden_push_endpoint_is_still_routed_past_its_gate(api_client, monkeypatch):
    """A malformed envelope reaching the handler's own 400 proves the route
    is registered and the token gate passed — being unpublished changes
    neither."""
    monkeypatch.setattr(pubsub, "verify_push_token", lambda token: True)

    response = api_client.post(
        "/events/certificate-batch",
        params={"token": "x"},
        json={"message": {"not_data": "oops"}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "malformed push envelope"


def test_every_published_endpoint_has_a_public_summary_and_description():
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            where = f"{method.upper()} {path}"
            assert operation.get("summary"), f"{where} has no summary"
            description = operation.get("description")
            assert description, f"{where} has no description"
            for fragment in INTERNAL_PROSE:
                assert fragment not in description, f"{where} description leaks {fragment!r}"


def test_demo_run_limits_in_the_description_match_params():
    """The published limits are prose, so nothing but a test stops them
    drifting from the constants actually enforced."""
    description = app.openapi()["paths"]["/demo/certificate-batch"]["post"]["description"]

    assert f"{check_params.DEMO_COOLDOWN_SECONDS}-second cooldown" in description
    assert f"no more than {check_params.DEMO_DAILY_RUN_CAP} runs" in description


def test_committed_schema_copies_match_the_app():
    """scripts/export_openapi.py writes both copies. The web one exists
    because web/Dockerfile builds from web/ alone, so the page cannot
    import across the package boundary."""
    expected = app.openapi()

    for path in (API_SCHEMA_PATH, WEB_SCHEMA_PATH):
        assert path.exists(), f"{path} is missing — run scripts/export_openapi.py"
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert committed == expected, (
            f"{path.name} is stale — re-run scripts/export_openapi.py "
            "(and npm run gen:types in web/)"
        )
