"""Structured answer wire schema registered by Hospitality composition."""

from pydantic import BaseModel, Field


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    fact_ids: list[str] = Field(min_length=1, max_length=10)


class HospitalityGroundedAnswer(BaseModel):
    supported_claims: list[GroundedClaim] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=10)
