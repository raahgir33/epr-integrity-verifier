from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_status_model_region():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"status", "model", "region"}
    assert body["status"] == "ok"
