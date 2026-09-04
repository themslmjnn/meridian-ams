import uuid

from httpx import AsyncClient


class TestCorrelationIDMiddleware:
    async def test_request_id_generated_when_absent(
        self, integration_client: AsyncClient
    ):
        """A request without X-Request-ID receives a generated UUID in the response."""

        response = await integration_client.get("/health/live")
        assert "x-request-id" in response.headers

        request_id = response.headers["x-request-id"]
        assert len(request_id) > 0

        parsed = uuid.UUID(request_id)
        assert parsed.version == 4

    async def test_request_id_propagated_when_provided(
        self, integration_client: AsyncClient
    ):
        """A supplied X-Request-ID is echoed back in the response unchanged."""

        response = await integration_client.get(
            "/health/live", headers={"X-Request-ID": "my-trace-id-12345"}
        )

        assert response.headers["x-request-id"] == "my-trace-id-12345"

    async def test_different_requests_get_different_request_ids(
        self, integration_client: AsyncClient
    ):
        """Each request without X-Request-ID must receive a unique generated ID."""

        r1 = await integration_client.get("/health/live")
        r2 = await integration_client.get("/health/live")

        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]

    async def test_request_id_present_on_error_responses(
        self, integration_client: AsyncClient
    ):
        """X-Request-ID must be present even on 404 and 500 responses."""

        response = await integration_client.get("/nonexistent-route")

        assert "x-request-id" in response.headers


class TestSecurityHeadersMiddleware:
    async def test_security_header_x_content_type_options(
        self, integration_client: AsyncClient
    ):
        response = await integration_client.get("/health/live")

        assert response.headers.get("x-content-type-options") == "nosniff"

    async def test_security_header_x_frame_options(
        self, integration_client: AsyncClient
    ):
        response = await integration_client.get("/health/live")

        assert response.headers.get("x-frame-options") == "DENY"

    async def test_security_header_referrer_policy(
        self, integration_client: AsyncClient
    ):
        response = await integration_client.get("/health/live")

        assert (
            response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        )

    async def test_all_security_headers_present_on_success_response(
        self,
        integration_client: AsyncClient,
    ):
        response = await integration_client.get("/health/live")

        assert "x-content-type-options" in response.headers
        assert "x-frame-options" in response.headers
        assert "referrer-policy" in response.headers

    async def test_all_security_headers_present_on_404_response(
        self,
        integration_client: AsyncClient,
    ):
        """Security headers must be appended even when the route does not exist."""

        response = await integration_client.get("/nonexistent-route")

        assert "x-content-type-options" in response.headers
        assert "x-frame-options" in response.headers
        assert "referrer-policy" in response.headers


class TestRequestLoggingMiddleware:
    async def test_request_logging_does_not_alter_status_code(
        self,
        integration_client: AsyncClient,
    ):
        """RequestLoggingMiddleware must not modify the response status code."""

        response = await integration_client.get("/health/live")

        assert response.status_code == 200

    async def test_request_logging_does_not_alter_response_body(
        self,
        integration_client: AsyncClient,
    ):
        """RequestLoggingMiddleware must not modify the response body."""

        response = await integration_client.get("/health/live")

        assert response.json() == {"status": "ok"}
