"""Structured answer wire schema registered by Hospitality composition."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from staylead_platform.domains.hospitality.schemas.guest_brief import HospitalityGuestBriefPatch


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    fact_ids: list[str] = Field(min_length=1, max_length=10)


class GuestBriefClaim(BaseModel):
    """A guest-state statement grounded only in exact saved brief fields."""

    text: str = Field(min_length=1, max_length=2000)
    refs: list[str] = Field(min_length=1, max_length=10)


class GuestClarification(BaseModel):
    """A typed question about an explicit, still-pending checkout date choice."""

    field: str = Field(min_length=1, max_length=64)
    options: list[str] = Field(min_length=2, max_length=2)
    text: str = Field(min_length=1, max_length=500)


class ConversationalAcknowledgement(BaseModel):
    """A bounded translation of one nonfactual social intent."""

    intent: Literal["thanks_acknowledged"]
    text: str = Field(min_length=1, max_length=160)


class HospitalityGroundedAnswer(BaseModel):
    supported_claims: list[GroundedClaim] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=10)
    guest_patch: HospitalityGuestBriefPatch | None = None
    guest_claims: list[GuestBriefClaim] = Field(default_factory=list, max_length=20)
    guest_clarification: GuestClarification | None = None
    conversational_acknowledgement: ConversationalAcknowledgement | None = None
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


def committed_answer_output_schema(label_keys: tuple[str, ...]) -> dict[str, object]:
    """Build Codex's final-answer schema with at least one substantive channel."""
    if (
        len(set(label_keys)) != len(label_keys)
        or any(not isinstance(key, str) or not key for key in label_keys)
    ):
        raise ValueError("Presentation label keys must be unique, non-empty strings.")

    def text(*, max_length: int = 2000) -> dict[str, object]:
        return {"type": "string", "minLength": 1, "maxLength": max_length, "pattern": r"\S"}

    def string_array(*, maximum: int) -> dict[str, object]:
        return {"type": "array", "items": text(max_length=2000), "minItems": 0, "maxItems": maximum}

    properties: dict[str, object] = {
        "supported_claims": {
            "type": "array", "minItems": 0, "maxItems": 20,
            "items": {
                "type": "object", "properties": {
                    "text": text(),
                    "fact_ids": {"type": "array", "items": text(max_length=128), "minItems": 1, "maxItems": 10},
                },
                "required": ["text", "fact_ids"], "additionalProperties": False,
            },
        },
        "unknowns": string_array(maximum=20),
        "conflicts": string_array(maximum=10),
        "guest_claims": {
            "type": "array", "minItems": 0, "maxItems": 20,
            "items": {
                "type": "object", "properties": {
                    "text": text(),
                    "refs": {"type": "array", "items": text(max_length=128), "minItems": 1, "maxItems": 10},
                },
                "required": ["text", "refs"], "additionalProperties": False,
            },
        },
        "guest_brief_refs": {"type": "array", "items": text(max_length=128), "minItems": 0, "maxItems": 20},
        "guest_clarification": {
            "anyOf": [
                {"type": "object", "properties": {
                    "field": {"type": "string", "enum": ["dates.check_out"]},
                    "options": {"type": "array", "items": text(max_length=16), "minItems": 2, "maxItems": 2},
                    "text": text(max_length=500),
                }, "required": ["field", "options", "text"], "additionalProperties": False},
                {"type": "null"},
            ],
        },
        "conversational_acknowledgement": {
            "anyOf": [
                {"type": "object", "properties": {
                    "intent": {"type": "string", "enum": ["thanks_acknowledged"]},
                    "text": text(max_length=160),
                }, "required": ["intent", "text"], "additionalProperties": False},
                {"type": "null"},
            ],
        },
        "label_bundle": {
            "type": "object",
            "properties": {key: text(max_length=80) for key in label_keys},
            "required": list(label_keys),
            "additionalProperties": False,
        },
    }
    branches: list[dict[str, object]] = []
    for channel in ("supported_claims", "guest_claims", "unknowns", "conflicts"):
        branch_properties = {key: dict(value) for key, value in properties.items()}
        branch_properties[channel] = dict(branch_properties[channel])
        branch_properties[channel]["minItems"] = 1  # type: ignore[index]
        branches.append({
            "type": "object", "properties": branch_properties,
            "required": list(properties), "additionalProperties": False,
        })
    for channel in ("guest_clarification", "conversational_acknowledgement"):
        branch_properties = {key: dict(value) for key, value in properties.items()}
        nullable = branch_properties[channel]
        if isinstance(nullable, dict):
            branch_properties[channel] = next(item for item in nullable["anyOf"] if item.get("type") == "object")
        branches.append({
            "type": "object", "properties": branch_properties,
            "required": list(properties), "additionalProperties": False,
        })
    return {
        "type": "object",
        "properties": {"response": {"anyOf": branches}},
        "required": ["response"],
        "additionalProperties": False,
    }
