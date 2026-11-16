
import asyncio
from uuid import UUID

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.main import app


def test_health_generates_request_id():
    """The server should generate a UUID when no ID is supplied."""

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200

    request_id = response.json()["request_id"]

    # Verify that the generated ID is a valid UUID.
    UUID(request_id)

    assert response.headers["X-Request-ID"] == request_id


def test_custom_request_id_is_preserved():
    """A valid client-provided ID should be preserved."""

    custom_id = "test-request-123"

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"X-Request-ID": custom_id},
        )

    assert response.status_code == 200
    assert response.json()["request_id"] == custom_id
    assert response.headers["X-Request-ID"] == custom_id


def test_invalid_request_id_is_replaced():
    """Malformed request IDs should be replaced with a generated UUID."""

    invalid_id = "invalid request/id with spaces"

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"X-Request-ID": invalid_id},
        )

    assert response.status_code == 200

    generated_id = response.json()["request_id"]

    assert generated_id != invalid_id
    UUID(generated_id)

    assert response.headers["X-Request-ID"] == generated_id


def test_concurrent_request_id_isolation():
    """Concurrent requests must retain their own request IDs."""

    async def run_requests():
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:

            tasks = [
                client.get(
                    "/api/v1/health",
                    headers={"X-Request-ID": f"async-test-{i}"},
                )
                for i in range(1, 21)
            ]

            return await asyncio.gather(*tasks)

    responses = asyncio.run(run_requests())

    assert len(responses) == 20

    for i, response in enumerate(responses, start=1):
        expected_id = f"async-test-{i}"

        assert response.status_code == 200
        assert response.json()["request_id"] == expected_id
        assert response.headers["X-Request-ID"] == expected_id
