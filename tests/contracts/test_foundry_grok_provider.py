"""Offline wire-contract checks for the Foundry Grok HTTP adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, Self

import httpx
import pytest
from pydantic import SecretStr
from staylead_platform.infrastructure.ai_provider import (
    FoundryGrokConfig,
    FoundryGrokProvider,
)
from staylead_platform.platform.contracts.ai_provider import GenerationRequest


class OfflineResponse:
    status_code = 200
    headers: ClassVar[dict[str, str]] = {"x-request-id": "offline-test-request"}

    @staticmethod
    def json() -> dict[str, Any]:
        return {
            "model": "offline-model",
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        }


def run_offline_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    trace_callback: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
) -> tuple[dict[str, Any], Any]:
    captured: dict[str, Any] = {}

    class Client:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            json: dict[str, Any],
            headers: dict[str, str],
            extensions: dict[str, Any] | None = None,
        ) -> OfflineResponse:
            captured.update(url=url, payload=json, headers=headers)
            if extensions is not None:
                captured["extensions"] = extensions
            return OfflineResponse()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    provider = FoundryGrokProvider(FoundryGrokConfig(
        base_url="https://foundry.example.test/openai/v1/",
        api_key=SecretStr("offline-secret"),
        deployment="grok-deployment",
        timeout_seconds=25.0,
        trace_callback=trace_callback,
    ))
    result = asyncio.run(provider.generate(GenerationRequest(
        instructions="Return one JSON object.",
        input_text='{"question":"What time is breakfast?"}',
        max_output_tokens=140,
    )))
    return captured, result


def test_foundry_grok_uses_reasoning_inclusive_completion_cap_and_no_trace_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, result = run_offline_request(monkeypatch)

    payload = captured["payload"]
    assert captured["url"] == "https://foundry.example.test/openai/v1/chat/completions"
    assert captured["timeout"] == 25.0
    assert "extensions" not in captured
    assert payload["max_completion_tokens"] == 140
    assert "max_tokens" not in payload
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["content"] == "Return one JSON object."
    assert result.text == '{"ok":true}'
    assert result.request_id == "offline-test-request"


def test_foundry_grok_wires_optional_httpx_trace_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def trace(event_name: str, info: dict[str, Any]) -> None:
        return None

    captured, result = run_offline_request(monkeypatch, trace_callback=trace)

    assert captured["extensions"] == {"trace": trace}
    assert captured["timeout"] == 25.0
    assert captured["payload"]["max_completion_tokens"] == 140
    assert result.text == '{"ok":true}'
    assert result.request_id == "offline-test-request"
