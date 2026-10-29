"""Provider-neutral text generation contracts used by M3."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GenerationRequest:
    """Provider-neutral generation request with optional native-structured-output hints."""

    instructions: str
    input_text: str
    max_output_tokens: int = 700
    # Adapters may ignore these when their API does not support JSON Schema output.
    response_schema: dict[str, Any] | None = None
    response_envelope_key: str | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str
    deployment: str
    model: str | None
    request_id: str | None
    usage: Usage


class ProviderError(RuntimeError):
    """Safe, typed failure from an AI provider; message never contains credentials."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class AIProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
