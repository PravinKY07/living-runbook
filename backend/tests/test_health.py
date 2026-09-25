from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_status_code():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_response_body():
    response = client.get("/api/health")
    assert response.json() == {"status": "ok"}


def test_health_content_type():
    response = client.get("/api/health")
    assert "application/json" in response.headers["content-type"]
