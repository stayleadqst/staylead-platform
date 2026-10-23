"""Domain-neutral read port for hotel-scoped guest-eligible knowledge facts."""

from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True)
class MediaDescriptor:
    """Guest-safe metadata for media bound to approved, cited knowledge facts."""

    media_id: str
    hotel_id: str
    fact_ids: tuple[str, ...]
    kind: str
    mime_type: str
    byte_size: int
    sha256: str
    caption: str
    alt_text: str
    source_id: str
    source_version: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    duration_seconds: float | None = None
    captions_media_id: str | None = None


@dataclass(frozen=True)
class EligibleAsset:
    content: bytes
    mime_type: str
    descriptor: MediaDescriptor


class EligibleMediaRepository(Protocol):
    def list_eligible_media(
        self, hotel_id: str, fact_ids: set[str], now: datetime, *,
        timeout_seconds: float | None = None,
    ) -> list[MediaDescriptor]: ...

    def read_eligible_asset(
        self, hotel_id: str, media_id: str, now: datetime, *,
        timeout_seconds: float | None = None,
    ) -> EligibleAsset | None: ...
