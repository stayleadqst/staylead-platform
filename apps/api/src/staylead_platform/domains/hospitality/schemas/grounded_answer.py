"""Structured answer wire schema registered by Hospitality composition."""

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from staylead_platform.domains.hospitality.schemas.guest_brief import (
    GuestPatchAuthorization,
    GuestTurnIntent,
    HospitalityGuestBriefPatch,
    required_pending_clarification_fields,
    validate_inline_patch_quotes,
)


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    fact_ids: list[str] = Field(min_length=1, max_length=10)


class GuestBriefClaim(BaseModel):
    """A guest-state statement grounded only in exact saved brief fields."""

    text: str = Field(min_length=1, max_length=2000)
    refs: list[str] = Field(min_length=1, max_length=10)


class GuestClarification(BaseModel):
    """A typed question about a current pending guest field."""

    field: str = Field(min_length=1, max_length=64)
    options: list[str] = Field(default_factory=list, max_length=2)
    text: str = Field(min_length=1, max_length=500)


class ConversationalAcknowledgement(BaseModel):
    """A bounded translation of one nonfactual social intent."""

    intent: Literal["thanks_acknowledged"]
    text: str = Field(min_length=1, max_length=160)


class HospitalityGroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_claims: list[GroundedClaim] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=10)
    guest_patch: HospitalityGuestBriefPatch | None = None
    guest_patch_authorizations: list[GuestPatchAuthorization] = Field(default_factory=list, max_length=12)
    turn_intents: list[GuestTurnIntent] = Field(default_factory=list, max_length=6)
    guest_claims: list[GuestBriefClaim] = Field(default_factory=list, max_length=20)
    guest_clarification: GuestClarification | None = None
    conversational_acknowledgement: ConversationalAcknowledgement | None = None
    guest_brief_refs: list[str] = Field(default_factory=list, max_length=20)
    explicit_language_tag: str | None = Field(default=None, max_length=64)
    inferred_language_tag: str | None = Field(default=None, max_length=64)
    label_bundle: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def _patch_quotes_are_inline(self) -> Self:
        validate_inline_patch_quotes(self.guest_patch)
        return self

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


_CHECKOUT_CHOICE = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)")


def committed_answer_output_schema(
    label_keys: tuple[str, ...],
    allowed_guest_refs: tuple[str, ...] = (),
    pending_fields: tuple[str, ...] = (),
    question: str = "",
    turn_intents: tuple[str, ...] = (),
    authorized_targets: tuple[str, ...] = (),
) -> dict[str, object]:
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

    guest_refs: dict[str, object] = {
        "type": "array", "items": text(max_length=128),
        "minItems": 1 if allowed_guest_refs else 0,
        "maxItems": 10 if allowed_guest_refs else 0,
    }
    if allowed_guest_refs:
        guest_refs["items"] = {"type": "string", "enum": list(allowed_guest_refs)}
    else:
        guest_refs["maxItems"] = 0
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
                    "refs": dict(guest_refs),
                },
                "required": ["text", "refs"], "additionalProperties": False,
            },
        },
        "guest_brief_refs": (
            {"type": "array", "items": {"type": "string", "enum": list(allowed_guest_refs)}, "minItems": 0, "maxItems": 20}
            if allowed_guest_refs else {"type": "array", "items": text(max_length=128), "minItems": 0, "maxItems": 0}
        ),
        "guest_clarification": {
            "anyOf": [
                {"type": "object", "properties": {
                    "field": {"type": "string", "enum": ["dates.check_out"]},
                    "options": {"type": "array", "items": text(max_length=16), "minItems": 0, "maxItems": 2},
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
    if not allowed_guest_refs:
        properties["guest_claims"]["maxItems"] = 0  # type: ignore[index]
    choice_matches = _CHECKOUT_CHOICE.findall(question)
    checkout_choices = list(choice_matches[0]) if (
        "dates.check_out" in pending_fields and len(choice_matches) == 1
        and choice_matches[0][0] != choice_matches[0][1]
    ) else []
    clarification_fields = list(required_pending_clarification_fields(pending_fields, authorized_targets))
    clarification = properties["guest_clarification"]
    if isinstance(clarification, dict):
        variants = clarification["anyOf"]
        clarification_object = next(item for item in variants if item.get("type") == "object")
        if clarification_fields:
            clarification_object["properties"]["field"] = {
                "type": "string", "enum": clarification_fields,
            }
            if checkout_choices and "dates.check_out" in clarification_fields:
                clarification_object["properties"]["options"] = {
                    "type": "array", "items": {"type": "string", "enum": checkout_choices},
                    "minItems": 2, "maxItems": 2,
                }
            else:
                clarification_object["properties"]["options"] = {
                    "type": "array", "items": text(max_length=16), "minItems": 0, "maxItems": 0,
                }
            properties["guest_clarification"] = clarification_object
        else:
            properties["guest_clarification"] = {"type": "null"}
    if "party.children." in " ".join(pending_fields) and any(
        ref.endswith(".age") for ref in pending_fields
    ):
        properties["unknowns"]["minItems"] = 1  # type: ignore[index]
    if "hotel_information" not in turn_intents:
        properties["supported_claims"]["maxItems"] = 0  # type: ignore[index]
        properties["conflicts"]["maxItems"] = 0  # type: ignore[index]
        pending_can_be_asked = any(
            field == "dates.check_out" or field.endswith(".age") for field in pending_fields
        )
        missing_guest_state = (
            "guest_state" in turn_intents and not allowed_guest_refs
            and not authorized_targets and not pending_fields
        )
        properties["unknowns"]["maxItems"] = 1 if pending_can_be_asked or missing_guest_state else 0  # type: ignore[index]
    branches: list[dict[str, object]] = []
    channels = ["supported_claims", "unknowns", "conflicts"]
    if "hotel_information" not in turn_intents:
        pending_can_be_asked = any(
            field == "dates.check_out" or field.endswith(".age") for field in pending_fields
        )
        missing_guest_state = (
            "guest_state" in turn_intents and not allowed_guest_refs
            and not authorized_targets and not pending_fields
        )
        channels = ["unknowns"] if pending_can_be_asked or missing_guest_state else []
    if allowed_guest_refs:
        channels.append("guest_claims")
    for channel in channels:
        branch_properties = {key: dict(value) for key, value in properties.items()}
        branch_properties[channel] = dict(branch_properties[channel])
        branch_properties[channel]["minItems"] = 1  # type: ignore[index]
        branches.append({
            "type": "object", "properties": branch_properties,
            "required": list(properties), "additionalProperties": False,
        })
    for channel in (("conversational_acknowledgement",) if "courtesy" in turn_intents else ()):
        branch_properties = {key: dict(value) for key, value in properties.items()}
        nullable = branch_properties[channel]
        if isinstance(nullable, dict):
            branch_properties[channel] = next(item for item in nullable["anyOf"] if item.get("type") == "object")
        branches.append({
            "type": "object", "properties": branch_properties,
            "required": list(properties), "additionalProperties": False,
        })
    if clarification_fields:
        branches.append({
            "type": "object", "properties": {key: dict(value) for key, value in properties.items()},
            "required": list(properties), "additionalProperties": False,
        })
    # A local-guide capability result is rendered from trusted server-side facts;
    # the model's committed turn may therefore contain only its bounded labels.
    # Keep this escape hatch exclusive to guide-only turns with no required
    # clarification, and disallow claims/refs so it cannot satisfy another channel.
    pending_can_be_asked = any(
        field == "dates.check_out" or field.endswith(".age") for field in pending_fields
    )
    missing_guest_state = (
        "guest_state" in turn_intents and not allowed_guest_refs
        and not authorized_targets and not pending_fields
    )
    if (
        "local_guide" in turn_intents
        and set(turn_intents).issubset({"local_guide", "guest_edit"})
        and not clarification_fields
        and not pending_can_be_asked
        and not missing_guest_state
    ):
        branch_properties = {key: dict(value) for key, value in properties.items()}
        for channel in ("supported_claims", "unknowns", "conflicts", "guest_claims", "guest_brief_refs"):
            branch_properties[channel] = dict(branch_properties[channel])
            branch_properties[channel]["maxItems"] = 0  # type: ignore[index]
        branch_properties["guest_clarification"] = {"type": "null"}
        branch_properties["conversational_acknowledgement"] = {"type": "null"}
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
