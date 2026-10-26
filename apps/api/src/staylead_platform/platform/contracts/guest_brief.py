"""Provider-neutral contracts for a versioned guest-provided brief.

The contract deliberately treats brief data and patch operations as opaque JSON.
The domain validator owns their meaning; the platform only scopes and persists them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class GuestBriefSnapshot:
    brief_version: int
    data: dict[str, Any]
    pending_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class GuestBriefSourceRef:
    source_utterance_id: str
    request_id: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class GuestBriefProposal:
    operations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ValidatedGuestBriefPatch:
    """Domain-validated canonical state and delta for atomic platform storage."""

    data: dict[str, Any]
    pending_fields: tuple[str, ...]
    applied_delta: dict[str, Any]
    status: Literal["applied", "no_change", "clarification", "partial_success"]
    source_fields: tuple[str, ...]


@dataclass(frozen=True)
class GuestBriefContext:
    """Trusted server context. Never populate scope/version from model output."""

    session_id: str
    hotel_id: str
    request_id: str
    expected_brief_version: int
    source_utterance_id: str
    source_utterance: str
    answer_only_receipt_id: str | None = None


@dataclass(frozen=True)
class GuestBriefReceipt:
    request_id: str
    status: Literal["applied", "no_change", "clarification", "partial_success"]
    brief_version_before: int
    brief_version_after: int
    applied_delta: dict[str, Any]
    source_refs: tuple[GuestBriefSourceRef, ...]
    answer_status: Literal["pending", "completed", "failed"] = "pending"
    brief_version_used: int | None = None


@dataclass(frozen=True)
class GuestBriefMutationResult:
    brief: GuestBriefSnapshot
    receipt: GuestBriefReceipt
    replayed: bool = False
    conflict: bool = False


@dataclass(frozen=True)
class PreparedGuestTurn:
    """One bounded preparation call, with an optional provisional FAQ answer."""

    provisional_answer: Any | None
    guest_patch: GuestBriefProposal | None
    selected_fact_ids: tuple[str, ...] = ()
    source_utterance_id: str | None = None
    preparation_calls: int = 0
    retrieval_fact_ids: tuple[str, ...] = ()
    provider: str | None = None
    deployment: str | None = None
    model: str | None = None
    provider_request_ids: tuple[str, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    explicit_language_tag: str | None = None
    inferred_language_tag: str | None = None


@dataclass(frozen=True)
class GuestBriefAnswerCommit:
    brief_version_used: int
    brief_dependent: bool
    answer_status: Literal["completed", "failed"]
    answer_payload: dict[str, Any] = field(default_factory=dict)
