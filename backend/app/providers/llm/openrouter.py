from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from app.providers.llm.base import (
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


logger = logging.getLogger("enterprise-ai.llm.openrouter")


class OpenRouterProvider(LLMProvider):
    """OpenAI-compatible OpenRouter client with bounded retries and fallback."""

    provider_name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://openrouter.ai/api/v1",
        default_model: str = "baidu/ernie-5.5-flash-preview:free",
        fallback_model: str | None = "nvidia/nemotron-3-ultra-550b-a55b:free",
        timeout: float = 30.0,
        max_retries: int = 2,
        default_max_tokens: int = 1024,
        http_client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.default_max_tokens = default_max_tokens
        self._client = http_client
        self._owns_client = http_client is None
        self._sleep = sleep_fn

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise LLMAuthError("OPENROUTER_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "Enterprise AI Intelligence Platform",
        }

    @staticmethod
    def _classify_http_error(status_code: int, detail: str) -> LLMProviderError:
        message = f"OpenRouter HTTP {status_code}: {detail}"
        if status_code in (401, 403):
            return LLMAuthError(message, status_code=status_code)
        if status_code == 429:
            return LLMRateLimitError(message, status_code=status_code)
        if 400 <= status_code < 500:
            return LLMBadRequestError(message, status_code=status_code)
        return LLMUnavailableError(message, status_code=status_code)

    def _build_payload(
        self,
        request: LLMRequest,
        *,
        model: str,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or self.default_max_tokens,
            "stream": stream,
        }
        if request.response_format is not None:
            payload["response_format"] = request.response_format
        return payload

    @staticmethod
    def _parse_usage(raw_usage: Any) -> LLMUsage:
        if not isinstance(raw_usage, dict):
            return LLMUsage()
        return LLMUsage(
            prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
            completion_tokens=int(raw_usage.get("completion_tokens") or 0),
            total_tokens=int(raw_usage.get("total_tokens") or 0),
        )

    def _post_chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"
        try:
            response = client.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"OpenRouter transport error: {exc}") from exc

        if response.status_code >= 400:
            raise self._classify_http_error(
                response.status_code,
                response.text[:300],
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMMalformedResponseError(
                "OpenRouter returned invalid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise LLMMalformedResponseError(
                "OpenRouter response must be a JSON object"
            )
        return data

    def _execute_with_retries(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: LLMProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._post_chat_completion(payload)
            except LLMProviderError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self.max_retries:
                    raise
                delay = min(2.0**attempt * 0.5, 4.0)
                logger.warning(
                    "openrouter_retrying",
                    extra={
                        "event": "openrouter_retrying",
                        "model": payload.get("model"),
                        "attempt": attempt + 1,
                        "status_code": exc.status_code,
                    },
                )
                self._sleep(delay)
        assert last_error is not None
        raise last_error

    def _extract_response(
        self,
        data: dict[str, Any],
        *,
        requested_model: str,
        latency_ms: float,
        used_fallback: bool,
    ) -> LLMResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMMalformedResponseError("OpenRouter response missing choices")

        first = choices[0]
        if not isinstance(first, dict):
            raise LLMMalformedResponseError("OpenRouter choice is not an object")

        message = first.get("message")
        if not isinstance(message, dict):
            raise LLMMalformedResponseError("OpenRouter choice missing message object")

        raw_content = message.get("content")
        if isinstance(raw_content, list):
            parts = [
                str(part.get("text", ""))
                for part in raw_content
                if isinstance(part, dict)
            ]
            raw_content = "".join(parts)

        if not isinstance(raw_content, str) or not raw_content.strip():
            raise LLMMalformedResponseError(
                "OpenRouter choice missing string message content"
            )

        return LLMResponse(
            content=raw_content,
            model=str(data.get("model") or requested_model),
            provider=self.provider_name,
            usage=self._parse_usage(data.get("usage")),
            latency_ms=round(latency_ms, 2),
            finish_reason=first.get("finish_reason"),
            used_fallback=used_fallback,
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not request.messages:
            raise LLMBadRequestError("LLMRequest.messages must not be empty")

        primary_model = request.model or self.default_model
        start = time.perf_counter()

        try:
            payload = self._build_payload(
                request,
                model=primary_model,
                stream=False,
            )
            data = self._execute_with_retries(payload)
            return self._extract_response(
                data,
                requested_model=primary_model,
                latency_ms=(time.perf_counter() - start) * 1000,
                used_fallback=False,
            )
        except LLMProviderError as exc:
            can_fallback = (
                (exc.retryable or isinstance(exc, LLMMalformedResponseError))
                and self.fallback_model is not None
                and self.fallback_model != primary_model
                and request.model is None
            )
            if not can_fallback:
                raise

            logger.warning(
                "openrouter_falling_back",
                extra={
                    "event": "openrouter_falling_back",
                    "primary_model": primary_model,
                    "fallback_model": self.fallback_model,
                },
            )
            fallback_payload = self._build_payload(
                request,
                model=self.fallback_model,  # type: ignore[arg-type]
                stream=False,
            )
            data = self._execute_with_retries(fallback_payload)
            return self._extract_response(
                data,
                requested_model=self.fallback_model,  # type: ignore[arg-type]
                latency_ms=(time.perf_counter() - start) * 1000,
                used_fallback=True,
            )

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        if not request.messages:
            raise LLMBadRequestError("LLMRequest.messages must not be empty")

        model = request.model or self.default_model
        payload = self._build_payload(request, model=model, stream=True)
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"

        try:
            with client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            ) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    raise self._classify_http_error(
                        response.status_code,
                        body[:300],
                    )

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                    except ValueError as exc:
                        raise LLMMalformedResponseError(
                            "OpenRouter stream emitted invalid JSON"
                        ) from exc

                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta_obj = choice.get("delta") or {}
                    delta_text = delta_obj.get("content") or ""
                    finish_reason = choice.get("finish_reason")
                    usage = (
                        self._parse_usage(event.get("usage"))
                        if event.get("usage")
                        else None
                    )
                    if delta_text or finish_reason or usage:
                        yield LLMStreamChunk(
                            delta=delta_text,
                            model=str(event.get("model") or model),
                            provider=self.provider_name,
                            finish_reason=finish_reason,
                            usage=usage,
                        )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"OpenRouter stream timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"OpenRouter stream error: {exc}") from exc

    def check_health(self) -> dict[str, Any]:
        if not self._api_key:
            return {
                "configured": False,
                "reachable": False,
                "provider": self.provider_name,
                "model": self.default_model,
                "fallback_model": self.fallback_model,
                "error": "OPENROUTER_API_KEY is not configured",
            }

        client = self._get_client()
        url = f"{self.base_url}/models"
        try:
            response = client.get(
                url,
                headers=self._headers(),
                timeout=min(self.timeout, 10.0),
            )
            if response.status_code >= 400:
                return {
                    "configured": True,
                    "reachable": False,
                    "provider": self.provider_name,
                    "model": self.default_model,
                    "fallback_model": self.fallback_model,
                    "status_code": response.status_code,
                }
            data = response.json()
            model_ids = {
                item.get("id")
                for item in (data.get("data") or [])
                if isinstance(item, dict)
            }
            return {
                "configured": True,
                "reachable": True,
                "provider": self.provider_name,
                "model": self.default_model,
                "model_available": self.default_model in model_ids,
                "fallback_model": self.fallback_model,
                "fallback_available": (
                    self.fallback_model in model_ids
                    if self.fallback_model
                    else None
                ),
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "provider": self.provider_name,
                "model": self.default_model,
                "fallback_model": self.fallback_model,
                "error": str(exc),
            }
