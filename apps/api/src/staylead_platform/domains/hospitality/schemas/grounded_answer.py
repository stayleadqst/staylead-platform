"""Structured answer wire schema registered by Hospitality composition."""

from pydantic import BaseModel, Field, field_validator

from staylead_platform.domains.hospitality.schemas.guest_brief import HospitalityGuestBriefPatch


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    fact_ids: list[str] = Field(min_length=1, max_length=10)


class GuestBriefClaim(BaseModel):
    """A guest-state statement grounded only in exact saved brief fields."""

    text: str = Field(min_length=1, max_length=2000)
    refs: list[str] = Field(min_length=1, max_length=10)


class HospitalityGroundedAnswer(BaseModel):
    supported_claims: list[GroundedClaim] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=10)
    guest_patch: HospitalityGuestBriefPatch | None = None
    guest_claims: list[GuestBriefClaim] = Field(default_factory=list, max_length=20)
    guest_brief_refs: list[str] = Field(default_factory=list, max_length=20)
    explicit_language_tag: str | None = Field(default=None, max_length=64)
    inferred_language_tag: str | None = Field(default=None, max_length=64)
    label_bundle: dict[str, str] = Field(default_factory=dict, max_length=20)

    @field_validator("label_bundle", mode="before")
    @classmethod
    def _invalid_label_bundle_becomes_empty(cls, value: object) -> object:
        """Keep malformed optional presentation data from invalidating grounded claims."""
        if not isinstance(value, dict) or len(value) > 20:
            return {}
        if any(
            not isinstance(key, str) or not isinstance(label, str) or len(label) > 80
            for key, label in value.items()
        ):
            return {}
        return value
