"""Domain-neutral read port for hotel-scoped guest-eligible knowledge facts."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class KnowledgeFact:
    fact_id: str
    hotel_id: str
    topic: str
    subject: str
    field: str
    value: Any
    conditions: dict[str, Any]
    status: str
    valid_from: str
    valid_to: str
    provenance: dict[str, Any]


class KnowledgeFactRepository(Protocol):
    def list_guest_facts(
        self, hotel_id: str, *, limit: int = 400, timeout_seconds: float | None = None,
    ) -> list[KnowledgeFact]: ...

    def get_guest_facts(
        self, hotel_id: str, fact_ids: set[str], *, timeout_seconds: float | None = None,
    ) -> list[KnowledgeFact]: ...
