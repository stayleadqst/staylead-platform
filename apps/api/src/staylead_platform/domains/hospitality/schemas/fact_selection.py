"""Bounded M1 candidate selection schema for low-overlap multilingual requests."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from staylead_platform.domains.hospitality.schemas.guest_brief import (
    GuestPatchAuthorization,
    GuestTurnIntent,
    HospitalityGuestBriefPatch,
    validate_inline_patch_quotes,
)


class FactSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_ids: list[str] = Field(default_factory=list, max_length=20)
    guest_patch: HospitalityGuestBriefPatch | None = None
    guest_patch_authorizations: list[GuestPatchAuthorization] = Field(default_factory=list, max_length=12)
    turn_intents: list[GuestTurnIntent] = Field(default_factory=list, max_length=6)
    explicit_language_tag: str | None = Field(default=None, max_length=64)
    inferred_language_tag: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _patch_quotes_are_inline(self) -> Self:
        validate_inline_patch_quotes(self.guest_patch)
        return self
