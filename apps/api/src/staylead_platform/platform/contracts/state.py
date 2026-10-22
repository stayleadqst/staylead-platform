"""Neutral scope, expected-version and result-freshness contracts."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

Payload = TypeVar("Payload", bound=BaseModel)


@dataclass(frozen=True)
class StateScope:
    hotel_id: str
    subject_id: str


@dataclass(frozen=True)
class ExpectedVersion:
    value: int


@dataclass(frozen=True)
class StateEnvelope(Generic[Payload]):
    scope: StateScope
    version: int
    payload: Payload


class ResultFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    NEEDS_CHECK = "needs_check"


@dataclass(frozen=True)
class SourceVersion:
    source_id: str
    version: str


@dataclass(frozen=True)
class ResultDependencies:
    brief_version: int | None
    sources: tuple[SourceVersion, ...]
    freshness: ResultFreshness
    affected_dependencies: tuple[str, ...] = ()


class DomainValidator(Protocol[Payload]):
    def validate(self, payload: object) -> Payload: ...
