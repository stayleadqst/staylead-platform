"""Domain-neutral outcomes for validating model-authored factual claims."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeAlias


class ClaimConsistencyStatus(StrEnum):
    """Whether a factual assertion is bound to current cited source properties."""

    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AssertionConsistency:
    """One independently classified assertion span from a claim."""

    text: str
    status: ClaimConsistencyStatus
    fact_ids: tuple[str, ...] = ()
    subject: str | None = None
    field: str | None = None
    property_name: str | None = None
    reason: str | None = None
    assertive: bool = True


@dataclass(frozen=True)
class ClaimConsistencyResult:
    """Per-assertion outcomes; unknown or contradicted prose is never supported."""

    assertions: tuple[AssertionConsistency, ...]


ClaimConsistencyValidator: TypeAlias = Callable[
    [str, list[dict[str, Any]], str], ClaimConsistencyResult
]

