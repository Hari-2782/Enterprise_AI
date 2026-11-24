from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal


Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    """Single message in an LLM conversation."""

    role: Role
    content: str


@dataclass(frozen=True)
class LLMUsage:
    """Token consumption metadata reported by an LLM provider."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class LLMRequest:
    """Provider-agnostic generation request."""

    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.1
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Provider-agnostic generation response."""

    content: str
    model: str
    provider: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: float = 0.0
    finish_reason: str | None = None
    used_fallback: bool = False


@dataclass(frozen=True)
class LLMStreamChunk:
    """Incremental text delta emitted during streaming generation."""

    delta: str
    model: str
    provider: str
    finish_reason: str | None = None
    usage: LLMUsage | None = None


class LLMProviderError(Exception):
    """Base error for LLM provider failures."""

    retryable: bool = False

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMBadRequestError(LLMProviderError):
    """Non-retryable client or schema validation error (e.g. HTTP 400/422)."""

    retryable = False


class LLMAuthError(LLMProviderError):
    """Non-retryable authentication or authorization error (HTTP 401/403)."""

    retryable = False


class LLMRateLimitError(LLMProviderError):
    """Retryable rate-limit error (HTTP 429)."""

    retryable = True


class LLMTimeoutError(LLMProviderError):
    """Retryable request or read timeout."""

    retryable = True


class LLMUnavailableError(LLMProviderError):
    """Retryable upstream service or network failure (HTTP 5xx)."""

    retryable = True


class LLMMalformedResponseError(LLMProviderError):
    """Provider returned an unexpected or unparseable payload."""

    retryable = False


class LLMProvider(ABC):
    """Abstract interface for external and mock LLM providers."""

    provider_name: str

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a complete response for the given request."""

    @abstractmethod
    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        """Stream response chunks for the given request."""

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """Return diagnostic connectivity and model availability status."""
