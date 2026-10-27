"""Provider-neutral contracts for grounded hospitality room advice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

AdviceStatus = Literal[
    "ready", "needs_clarification", "infeasible", "unsupported",
    "processing_limit", "conflict", "partial",
]


@dataclass(frozen=True)
class RoomAdviceContext:
    """Trusted request context assembled by the platform, never by the model."""

    hotel_id: str
    brief_version: int
    brief_data: dict[str, Any]
    pending_fields: tuple[str, ...]
    source_generation: int
    facts: tuple[dict[str, Any], ...]
    question: str
    locale: str | None = None
    turn_intents: tuple[str, ...] = ()
    hotel_information_fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoomAdviceHotelClaim:
    """One checked FAQ statement and its selected current source facts."""

    text: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class RoomAdviceHotelAnswer:
    """Grounded hotel-information answer carried with mixed room advice."""

    supported_claims: tuple[RoomAdviceHotelClaim, ...] = ()
    unknowns: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoomAdviceCandidate:
    """One model-proposed arrangement; deterministic domain checks remain authoritative."""

    option_id: str
    rooms: tuple[dict[str, Any], ...]
    assignments: tuple[dict[str, Any], ...]
    rationale: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RoomAdviceDraft:
    status: Literal["ready", "needs_clarification", "infeasible", "unsupported"]
    options: tuple[RoomAdviceCandidate, ...] = ()
    questions: tuple[dict[str, str], ...] = ()
    hotel_answer: RoomAdviceHotelAnswer | None = None


@dataclass(frozen=True)
class RoomAdviceResult:
    """Validated, source-bound advice safe for the application to persist and present."""

    status: AdviceStatus
    brief_version: int
    source_generation: int
    source_refs: tuple[dict[str, Any], ...] = ()
    options: tuple[dict[str, Any], ...] = ()
    questions: tuple[dict[str, str], ...] = ()
    explanation_inputs: dict[str, Any] = field(default_factory=dict)
    availability: Literal["unknown"] = "unknown"
    hotel_answer: RoomAdviceHotelAnswer | None = None


class RoomAdviceUseCase(Protocol):
    def eligible_facts(self, context: RoomAdviceContext) -> tuple[dict[str, Any], ...]: ...

    def preparation_instructions(
        self, locale: str | None, *, include_hotel_answer: bool = False,
    ) -> str: ...

    def preparation_output_schema(self, *, include_hotel_answer: bool = False) -> dict[str, Any]: ...

    def parse_draft(self, text: str) -> RoomAdviceDraft: ...

    def select_facts(
        self, facts: tuple[dict[str, Any], ...], *, question: str,
        brief_data: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]: ...

    async def recommend(
        self, *, context: RoomAdviceContext, draft: RoomAdviceDraft,
        deadline: float | None = None,
    ) -> RoomAdviceResult: ...

    def relocalize(
        self, result: RoomAdviceResult, locale: str | None,
    ) -> RoomAdviceResult: ...
