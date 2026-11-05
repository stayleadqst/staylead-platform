from __future__ import annotations

import asyncio

import pytest
from staylead_platform.infrastructure.observability.turn_trace import TurnTrace
from staylead_platform.platform.ai_runtime.execution import MeteredProvider
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)


class FakeProvider:
    def __init__(self, *, delay: float = 0) -> None:
        self.calls = 0
        self.delay = delay

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return GenerationResult("{}", "fake", "offline", "test", "req-1", Usage(3, 2, 5))


def request(*, context: str = "{}", output: int = 140) -> GenerationRequest:
    return GenerationRequest("instructions", context, max_output_tokens=output)


def test_durable_slot_is_claimed_before_provider_and_cap_is_enforced() -> None:
    provider = FakeProvider()
    trace = TurnTrace()
    claimed: list[int] = []
    wrapped = MeteredProvider(
        provider, before_call=lambda index: claimed.append(index), trace=trace, max_calls=2,
    )
    async def run() -> None:
        await wrapped.generate(request())
        await wrapped.generate(request())
        with pytest.raises(ProviderError) as raised:
            await wrapped.generate(request())
        assert raised.value.code == "provider_call_limit"
    asyncio.run(run())
    assert claimed == [1, 2]
    assert provider.calls == 2


def test_rejected_durable_slot_does_not_dispatch() -> None:
    provider = FakeProvider()
    async def reject(_index: int) -> None:
        raise ProviderError("turn_lease_expired", "Request expired.")
    wrapped = MeteredProvider(provider, before_call=reject, trace=TurnTrace())
    async def run() -> None:
        with pytest.raises(ProviderError):
            await wrapped.generate(request())
    asyncio.run(run())
    assert provider.calls == 0


def test_injected_provider_timeout_is_enforced() -> None:
    provider = FakeProvider(delay=0.05)
    trace = TurnTrace()
    wrapped = MeteredProvider(
        provider, before_call=lambda _index: None, trace=trace, provider_timeout_seconds=0.005,
    )
    async def run() -> None:
        with pytest.raises(ProviderError) as raised:
            await wrapped.generate(request())
        assert raised.value.code == "provider_timeout"
    asyncio.run(run())
    assert provider.calls == 1
    assert trace.events[-1]["code"] == "provider_timeout"


def test_context_and_output_bounds_reject_before_durable_slot() -> None:
    provider = FakeProvider()
    claimed: list[int] = []
    wrapped = MeteredProvider(
        provider, before_call=lambda index: claimed.append(index), trace=TurnTrace(),
        max_context_chars=3, max_output_tokens=140,
    )
    async def run() -> None:
        with pytest.raises(ProviderError, match="context"):
            await wrapped.generate(request(context="long"))
        with pytest.raises(ProviderError, match="output"):
            await wrapped.generate(request(output=141))
    asyncio.run(run())
    assert claimed == []
    assert provider.calls == 0
