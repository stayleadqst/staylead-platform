"""Development-only server-side operator credentials and principals."""

from __future__ import annotations

import hmac
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


@dataclass(frozen=True)
class OperatorPrincipal:
    operator_id: str
    property_id: str
    permissions: frozenset[str]


class DevOperatorCredential(BaseModel):
    """A server-configured opaque bearer credential; never serialize to clients."""

    model_config = ConfigDict(extra="forbid")

    token: SecretStr = Field(min_length=32, max_length=512)
    operator_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    property_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    permissions: frozenset[str]

    @field_validator("permissions")
    @classmethod
    def supported_permissions_only(cls, value: frozenset[str]) -> frozenset[str]:
        if not value or not value <= {"guide:read", "guide:write"}:
            raise ValueError("Operator credentials require supported guide permissions.")
        return value

    def principal(self) -> OperatorPrincipal:
        return OperatorPrincipal(self.operator_id, self.property_id, self.permissions)


def resolve_dev_operator(token: str, credentials: Iterable[DevOperatorCredential]) -> OperatorPrincipal | None:
    """Compare against every configured token without exposing token values."""
    matched: OperatorPrincipal | None = None
    for credential in credentials:
        equal = hmac.compare_digest(token.encode("utf-8"), credential.token.get_secret_value().encode("utf-8"))
        if equal:
            matched = credential.principal()
    return matched
