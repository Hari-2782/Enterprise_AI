from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():

    response = client.get("/api/v1/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "enterprise-ai"
    assert "request_id" in data


def test_request_id_propagation():

    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "test-request-123"}
    )

    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.json()["request_id"] == "test-request-123"