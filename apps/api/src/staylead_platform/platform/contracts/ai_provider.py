"""Domain-neutral boundary for a future model provider adapter."""

from typing import Protocol


class AIProvider(Protocol):
    async def generate(self, *, instructions: str, input_text: str) -> str:
        """Generate a response. Implementations must never fabricate a fallback result."""
        ...
