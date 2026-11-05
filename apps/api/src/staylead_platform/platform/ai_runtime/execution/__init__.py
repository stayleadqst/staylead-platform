"""Provider-neutral, per-request execution controls."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from staylead_platform.platform.contracts.ai_provider import (
    AIProvider,
    GenerationRequest,
    GenerationResult,
    ProviderError,
)


class TraceSink(Protocol):
    """Structural documentation for the small trace surface used by this wrapper."""

    def record(self, stage: str, status: str, **values: Any) -> None: ...


BeforeProviderCall = Callable[[int], Awaitable[None] | None]


class MeteredProvider:
    """Wrap one provider instance with a local guard and durable pre-dispatch hook.

    The caller's hook claims the durable request-level call slot before this class
    invokes the provider. This wrapper never retries and never stores prompt text.
    """

    def __init__(
        self, inner: AIProvider, *, before_call: BeforeProviderCall,
        trace: TraceSink, max_calls: int = 2, max_context_chars: int = 22_000,
        max_output_tokens: int = 700, provider_timeout_seconds: float = 25.0,
    ) -> None:
        self._inner = inner
        self._before_call = before_call
        self._trace = trace
        self._max_calls = max(0, int(max_calls))
        self._max_context_chars = max(1, int(max_context_chars))
        self._max_output_tokens = max(1, int(max_output_tokens))
        self._provider_timeout_seconds = max(0.001, float(provider_timeout_seconds))
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        if len(request.input_text) > self._max_context_chars:
            self._trace.record("provider", "denied", code="context_limit", context_chars=len(request.input_text))
            raise ProviderError("context_limit", "The request context exceeds its configured limit.")
        if request.max_output_tokens > self._max_output_tokens:
            self._trace.record("provider", "denied", code="output_limit")
            raise ProviderError("output_limit", "The request output exceeds its configured limit.")
        if self._calls >= self._max_calls:
            self._trace.record("provider", "denied", code="provider_call_limit")
            raise ProviderError("provider_call_limit", "The request exceeded its provider-call limit.")
        next_call = self._calls + 1
        try:
            claimed = self._before_call(next_call)
            if inspect.isawaitable(claimed):
                await claimed
        except BaseException as exc:
            self._trace.record(
                "provider", "cancelled" if isinstance(exc, asyncio.CancelledError) else "denied",
                code=_safe_error_code(exc), calls=self._calls,
            )
            raise

        # Count once the durable slot is claimed, even if cancellation or timeout
        # happens before the provider returns; retries must not get a fresh slot.
        self._calls = next_call
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._inner.generate(request), timeout=self._provider_timeout_seconds,
            )
        except BaseException as exc:
            duration_ms = max(0, int((time.monotonic() - started) * 1000))
            timed_out = isinstance(exc, TimeoutError)
            status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
            self._trace.record(
                "provider", status, duration_ms=duration_ms,
                code="provider_timeout" if timed_out else _safe_error_code(exc), calls=self._calls,
            )
            if timed_out:
                raise ProviderError(
                    "provider_timeout", "The request exceeded its time limit.", retryable=True,
                ) from exc
            raise

        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        usage = result.usage
        self._trace.record(
            "provider", "ok", duration_ms=duration_ms, calls=self._calls,
            provider=result.provider, deployment=result.deployment, model=result.model,
            provider_request_id=result.request_id, input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens, total_tokens=usage.total_tokens,
        )
        return result


def _safe_error_code(error: BaseException) -> str:
    code = error.code if isinstance(error, ProviderError) else None
    if isinstance(code, str) and code and len(code) <= 64 and all(
        char.isalnum() or char in "_.-" for char in code
    ):
        return code
    return "provider_cancelled" if isinstance(error, asyncio.CancelledError) else "provider_failure"
