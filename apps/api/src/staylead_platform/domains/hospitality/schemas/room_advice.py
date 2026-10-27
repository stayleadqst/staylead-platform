"""Strict model candidate shape for the second room-advice preparation call."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from staylead_platform.domains.hospitality.schemas.grounded_answer import GroundedClaim


class RoomAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: str = Field(min_length=1, max_length=64)
    room_index: int = Field(ge=0, le=9)
    bed_index: int | None = Field(default=None, ge=0, le=19)
    bed_type: str | None = Field(default=None, max_length=64)
    bed_position: Literal["upper", "lower"] | None = None


class ProposedRoom(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_index: int = Field(ge=0, le=9)
    room_type_id: str = Field(min_length=1, max_length=64)


class RoomRationale(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_code: Literal[
        "party_fit", "bed_setup", "reference_price", "policy_confirmation",
        "accessibility_confirmation", "preference_tradeoff", "charges_confirmation",
    ]
    fact_ids: list[str] = Field(min_length=1, max_length=8)


class RoomAdviceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: str = Field(min_length=1, max_length=64)
    rooms: list[ProposedRoom] = Field(min_length=1, max_length=10)
    assignments: list[RoomAssignment] = Field(min_length=1, max_length=40)
    rationale: list[RoomRationale] = Field(default_factory=list, max_length=8)


class RoomAdviceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1, max_length=64)


class RoomAdviceHotelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported_claims: list[GroundedClaim] = Field(default_factory=list, max_length=4)
    unknowns: list[str] = Field(default_factory=list, max_length=4)
    conflicts: list[str] = Field(default_factory=list, max_length=4)


class RoomAdvicePreparation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    options: list[RoomAdviceOption] = Field(default_factory=list, max_length=4)
    questions: list[RoomAdviceQuestion] = Field(default_factory=list, max_length=6)
    hotel_answer: RoomAdviceHotelAnswer | None = None


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": required if required is not None else list(properties),
            "additionalProperties": False}


def room_advice_output_schema(*, include_hotel_answer: bool = False) -> dict[str, Any]:
    id_text = {"type": "string", "minLength": 1, "maxLength": 64, "pattern": r"\S"}
    assignment = _object({
        "member_id": id_text, "room_index": {"type": "integer", "minimum": 0, "maximum": 9},
        "bed_index": {"anyOf": [{"type": "integer", "minimum": 0, "maximum": 19}, {"type": "null"}]},
        "bed_type": {"anyOf": [id_text, {"type": "null"}]},
        "bed_position": {"anyOf": [{"type": "string", "enum": ["upper", "lower"]}, {"type": "null"}]},
    })
    room = _object({"room_index": {"type": "integer", "minimum": 0, "maximum": 9},
                    "room_type_id": id_text})
    rationale = _object({
        "claim_code": {"type": "string", "enum": [
            "party_fit", "bed_setup", "reference_price", "policy_confirmation", "accessibility_confirmation"
            , "preference_tradeoff", "charges_confirmation"
        ]},
        "fact_ids": {"type": "array", "items": id_text, "minItems": 1, "maxItems": 8},
    })
    option = _object({
        "option_id": id_text,
        "rooms": {"type": "array", "items": room, "minItems": 1, "maxItems": 10},
        "assignments": {"type": "array", "items": assignment, "minItems": 1, "maxItems": 40},
        "rationale": {"type": "array", "items": rationale, "maxItems": 8},
    })
    question = _object({"field": id_text})
    body_properties = {
        "options": {"type": "array", "items": option, "maxItems": 4},
        "questions": {"type": "array", "items": question, "maxItems": 6},
    }
    if include_hotel_answer:
        body_properties["hotel_answer"] = {
            "anyOf": [
                _object({
                    "supported_claims": {"type": "array", "items": _object({
                        "text": {"type": "string", "minLength": 1, "maxLength": 2000, "pattern": r"\S"},
                        "fact_ids": {"type": "array", "items": id_text, "minItems": 1, "maxItems": 10},
                    }), "maxItems": 4},
                    "unknowns": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 2000}, "maxItems": 4},
                    "conflicts": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 2000}, "maxItems": 4},
                }),
                {"type": "null"},
            ],
        }
    body = _object(body_properties)
    return _object({"response": body})
