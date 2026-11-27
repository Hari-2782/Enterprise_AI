from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.providers.llm.base import (
    LLMBadRequestError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
)


class MockLLMProvider(LLMProvider):
    """Deterministic in-memory LLM provider for automated testing."""

    provider_name = "mock"

    def __init__(
        self,
        *,
        default_model: str = "mock-ernie-flash",
        canned_response: str = "Mock grounded response.",
    ) -> None:
        self.default_model = default_model
        self.canned_response = canned_response
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not request.messages:
            raise LLMBadRequestError("LLMRequest.messages must not be empty")
        self.calls.append(request)
        model = request.model or self.default_model
        prompt_tokens = sum(len(m.content.split()) for m in request.messages)
        completion_tokens = len(self.canned_response.split())
        return LLMResponse(
            content=self.canned_response,
            model=model,
            provider=self.provider_name,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            latency_ms=1.0,
            finish_reason="stop",
            used_fallback=False,
        )

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        response = self.generate(request)
        words = response.content.split(" ")
        for idx, word in enumerate(words):
            is_last = idx == len(words) - 1
            delta = word if is_last else f"{word} "
            yield LLMStreamChunk(
                delta=delta,
                model=response.model,
                provider=self.provider_name,
                finish_reason="stop" if is_last else None,
                usage=response.usage if is_last else None,
            )

    def check_health(self) -> dict[str, Any]:
        return {
            "configured": True,
            "reachable": True,
            "provider": self.provider_name,
            "model": self.default_model,
            "model_available": True,
        }
