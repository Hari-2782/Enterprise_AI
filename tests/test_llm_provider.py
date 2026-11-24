import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.llm import (
    ChatMessage,
    LLMAuthError,
    LLMBadRequestError,
    LLMMalformedResponseError,
    LLMRateLimitError,
    LLMRequest,
    LLMTimeoutError,
    MockLLMProvider,
    OpenRouterProvider,
    get_llm_provider,
)


def _sample_request(model: str | None = None) -> LLMRequest:
    return LLMRequest(
        messages=[
            ChatMessage(role="system", content="Answer from context only."),
            ChatMessage(role="user", content="What is the retention policy?"),
        ],
        model=model,
        temperature=0.0,
        max_tokens=128,
    )


def test_mock_provider_generate_and_stream():
    provider = MockLLMProvider(canned_response="Seven years per HR policy.")
    response = provider.generate(_sample_request())

    assert response.provider == "mock"
    assert response.content == "Seven years per HR policy."
    assert response.usage.total_tokens > 0
    assert response.used_fallback is False

    chunks = list(provider.stream(_sample_request()))
    assert "".join(chunk.delta for chunk in chunks) == "Seven years per HR policy."
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None


def test_openrouter_generate_success_and_usage():
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(
            200,
            json={
                "model": "baidu/ernie-5.5-flash-preview:free",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Grounded answer."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="test-key",
        http_client=client,
        sleep_fn=lambda _: None,
    )

    response = provider.generate(_sample_request())
    assert captured_headers["authorization"] == "Bearer test-key"
    assert response.content == "Grounded answer."
    assert response.provider == "openrouter"
    assert response.usage.prompt_tokens == 12
    assert response.usage.completion_tokens == 4
    assert response.usage.total_tokens == 16
    assert response.used_fallback is False


def test_openrouter_retries_rate_limit_then_falls_back():
    seen_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        model = payload["model"]
        seen_models.append(model)
        if model == "baidu/ernie-5.5-flash-preview:free":
            return httpx.Response(429, text="rate limited")
        return httpx.Response(
            200,
            json={
                "model": model,
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Fallback answer."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="test-key",
        max_retries=2,
        http_client=client,
        sleep_fn=lambda _: None,
    )

    response = provider.generate(_sample_request())
    assert seen_models == [
        "baidu/ernie-5.5-flash-preview:free",
        "baidu/ernie-5.5-flash-preview:free",
        "baidu/ernie-5.5-flash-preview:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
    ]
    assert response.content == "Fallback answer."
    assert response.model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert response.used_fallback is True


def test_openrouter_does_not_retry_or_fallback_on_auth_or_bad_request():
    call_count = 0

    def auth_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, text="invalid api key")

    client = httpx.Client(transport=httpx.MockTransport(auth_handler))
    provider = OpenRouterProvider(
        api_key="bad-key",
        max_retries=2,
        http_client=client,
        sleep_fn=lambda _: None,
    )

    with pytest.raises(LLMAuthError):
        provider.generate(_sample_request())
    assert call_count == 1

    call_count = 0

    def bad_request_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, text="bad schema")

    bad_client = httpx.Client(transport=httpx.MockTransport(bad_request_handler))
    bad_provider = OpenRouterProvider(
        api_key="test-key",
        max_retries=2,
        http_client=bad_client,
        sleep_fn=lambda _: None,
    )

    with pytest.raises(LLMBadRequestError):
        bad_provider.generate(_sample_request())
    assert call_count == 1


def test_openrouter_timeout_raises_after_bounded_retries():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="test-key",
        fallback_model=None,
        max_retries=1,
        http_client=client,
        sleep_fn=lambda _: None,
    )

    with pytest.raises(LLMTimeoutError):
        provider.generate(_sample_request())
    assert call_count == 2


def test_openrouter_malformed_response_raises():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="test-key",
        http_client=client,
        sleep_fn=lambda _: None,
    )

    with pytest.raises(LLMMalformedResponseError):
        provider.generate(_sample_request())


def test_openrouter_stream_parses_sse_chunks():
    sse_body = (
        'data: {"model":"baidu/ernie-5.5-flash-preview:free","choices":[{"delta":{"content":"Hello "}}]}\n\n'
        'data: {"model":"baidu/ernie-5.5-flash-preview:free","choices":[{"delta":{"content":"world"},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sse_body.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="test-key",
        http_client=client,
        sleep_fn=lambda _: None,
    )

    chunks = list(provider.stream(_sample_request()))
    assert "".join(c.delta for c in chunks) == "Hello world"
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.total_tokens == 7


def test_openrouter_health_check_and_api_endpoint():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "baidu/ernie-5.5-flash-preview:free"},
                    {"id": "nvidia/nemotron-3-ultra-550b-a55b:free"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="test-key",
        http_client=client,
    )

    app.dependency_overrides[get_llm_provider] = lambda: provider
    try:
        test_client = TestClient(app)
        res = test_client.get("/api/v1/health/llm")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "healthy"
        assert body["llm"]["model_available"] is True
        assert body["llm"]["fallback_available"] is True
    finally:
        app.dependency_overrides.clear()
