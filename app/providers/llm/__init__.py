from app.core.config import settings
from app.providers.llm.base import (
    ChatMessage,
    LLMAuthError,
    LLMBadRequestError,
    LLMMalformedResponseError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    LLMTimeoutError,
    LLMUnavailableError,
    LLMUsage,
)
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openrouter import OpenRouterProvider


def get_llm_provider() -> LLMProvider:
    """Build the configured LLM provider from application settings."""
    provider = settings.model_provider.strip().lower()
    if provider == "mock":
        return MockLLMProvider(default_model=settings.openrouter_model)
    if provider == "openrouter":
        api_key = (
            settings.openrouter_api_key.get_secret_value()
            if settings.openrouter_api_key
            else None
        )
        return OpenRouterProvider(
            api_key=api_key,
            base_url=settings.openrouter_base_url,
            default_model=settings.openrouter_model,
            fallback_model=settings.openrouter_fallback_model,
            timeout=settings.openrouter_timeout,
            max_retries=settings.openrouter_max_retries,
            default_max_tokens=settings.openrouter_max_tokens,
        )
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.model_provider}")


__all__ = [
    "ChatMessage",
    "LLMAuthError",
    "LLMBadRequestError",
    "LLMMalformedResponseError",
    "LLMProvider",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamChunk",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "LLMUsage",
    "MockLLMProvider",
    "OpenRouterProvider",
    "get_llm_provider",
]
