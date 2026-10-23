"""Bounded M1 candidate selection schema for low-overlap multilingual requests."""

from pydantic import BaseModel, Field

from staylead_platform.domains.hospitality.schemas.guest_brief import HospitalityGuestBriefPatch


class FactSelection(BaseModel):
    fact_ids: list[str] = Field(default_factory=list, max_length=20)
    guest_patch: HospitalityGuestBriefPatch | None = None
