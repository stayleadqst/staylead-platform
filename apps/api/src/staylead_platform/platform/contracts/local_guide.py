"""Provider- and domain-neutral port contracts for scoped local-guide use.

The platform may carry an opaque guest brief and result, but Hospitality owns
the meaning of those values and validates all candidate facts before returning
them. No model-supplied hotel or source identity is part of this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class LocalGuideRequest:
    """Trusted request context supplied by the server-side M3 adapter."""

    hotel_id: str
    question: str
    locale: str | None
    brief_version: int
    brief_data: dict[str, Any]
    now: datetime
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class LocalGuideResult:
    """Small selected result; detailed facts remain server-side and cited."""

    hotel_id: str
    generation: int
    selected_venue_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()
    supported_claims: tuple[dict[str, Any], ...] = ()
    unknowns: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    source_refs: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class LocalGuideCapability(Protocol):
    """One bounded domain capability callable by the generic M3 orchestrator."""

    async def recommend(self, request: LocalGuideRequest) -> LocalGuideResult: ...
