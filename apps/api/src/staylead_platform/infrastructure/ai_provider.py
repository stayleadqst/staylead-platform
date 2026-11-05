"""Foundry Grok OpenAI-compatible Chat Completions adapter."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import SecretStr

from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)

TraceCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class FoundryGrokConfig:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        deployment: str,
        timeout_seconds: float = 25.0,
        trace_callback: TraceCallback | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.timeout_seconds = min(max(timeout_seconds, 1.0), 60.0)
        self.trace_callback = trace_callback

    def __repr__(self) -> str:
        return f"FoundryGrokConfig(base_url={self.base_url!r}, deployment={self.deployment!r})"


class FoundryGrokProvider:
    def __init__(self, config: FoundryGrokConfig) -> None:
        self._config = config

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        url = f"{self._config.base_url}/chat/completions"
        payload = {
            "model": self._config.deployment,
            "messages": [
                {"role": "system", "content": request.instructions},
                {"role": "user", "content": request.input_text},
            ],
            "max_completion_tokens": request.max_output_tokens,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                post_kwargs: dict[str, Any] = {
                    "json": payload,
                    "headers": {
                        "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                }
                if self._config.trace_callback is not None:
                    post_kwargs["extensions"] = {"trace": self._config.trace_callback}
                response = await client.post(url, **post_kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderError("provider_timeout", "The model request timed out.", retryable=True) from exc
        except httpx.RequestError as exc:
            raise ProviderError("provider_unavailable", "The model service could not be reached.", retryable=True) from exc
        if response.status_code in (401, 403):
            raise ProviderError("provider_auth", "The model service rejected server credentials.")
        if response.status_code == 429:
            raise ProviderError("provider_rate_limited", "The model service is rate limited.", retryable=True)
        if response.status_code >= 500:
            raise ProviderError("provider_unavailable", "The model service is unavailable.", retryable=True)
        if response.status_code >= 400:
            raise ProviderError("provider_request_rejected", "The model service rejected the request.")
        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
            if not isinstance(text, str) or not text.strip():
                raise ValueError("empty completion")
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise ProviderError("provider_invalid_response", "The model service returned an invalid response.") from exc
        return GenerationResult(
            text=text,
            provider="foundry_grok",
            deployment=self._config.deployment,
            model=body.get("model"),
            request_id=response.headers.get("x-request-id") or response.headers.get("request-id"),
            usage=Usage(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
        )
