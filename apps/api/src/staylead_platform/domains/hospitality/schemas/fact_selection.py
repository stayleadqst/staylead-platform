"""Bounded M1 candidate selection schema for low-overlap multilingual requests."""

from pydantic import BaseModel, Field

from staylead_platform.domains.hospitality.schemas.guest_brief import (
    GuestPatchAuthorization,
    GuestTurnIntent,
    HospitalityGuestBriefPatch,
)


class FactSelection(BaseModel):
    fact_ids: list[str] = Field(default_factory=list, max_length=20)
    guest_patch: HospitalityGuestBriefPatch | None = None
    guest_patch_authorizations: list[GuestPatchAuthorization] = Field(default_factory=list, max_length=12)
    turn_intents: list[GuestTurnIntent] = Field(default_factory=list, max_length=6)
    explicit_language_tag: str | None = Field(default=None, max_length=64)
    inferred_language_tag: str | None = Field(default=None, max_length=64)
