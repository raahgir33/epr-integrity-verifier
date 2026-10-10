from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_status_only():
    """T13.8: /health is deliberately minimal — no model, region, project
    ID or internal consistency flag over the wire (docs/BUILD_PLAN.md's
    hardening task). _consistency_status is still computed and logged at
    startup for an operator tailing logs; it's just not exposed here."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
