"""Strict Hospitality-owned native output schemas for turn preparation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PATCH_OPERATIONS = ("set_dates", "set_adults", "add_child", "set_child_age", "remove_child", "clarify")
TURN_INTENTS = ("hotel_information", "guest_state", "guest_edit", "courtesy")


def _string(*, maximum: int = 2000, minimum: int = 1) -> dict[str, Any]:
    return {"type": "string", "minLength": minimum, "maxLength": maximum, "pattern": r"\S"}


def _nullable_string(*, maximum: int) -> dict[str, Any]:
    return {"anyOf": [_string(maximum=maximum), {"type": "null"}]}


def _array(item: dict[str, Any], *, maximum: int, minimum: int = 0) -> dict[str, Any]:
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum}


def _closed_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False,
    }


def _operation_schema(
    op: str, properties: dict[str, Any], *, required: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    operation_properties = {"op": {"type": "string", "enum": [op]}, **properties}
    return {
        "type": "object", "properties": operation_properties,
        "required": list(required or operation_properties), "additionalProperties": False,
    }


def _patch_schema() -> dict[str, Any]:
    integer = {"type": "integer"}
    ops = [
        _operation_schema("set_dates", {
            "check_in": _nullable_string(maximum=10), "check_out": _nullable_string(maximum=10),
        }),
        _operation_schema("set_adults", {"count": {**integer, "minimum": 1, "maximum": 30}}),
        _operation_schema("add_child", {"age": {"anyOf": [
            {**integer, "minimum": 0, "maximum": 17}, {"type": "null"},
        ]}}),
        _operation_schema("set_child_age", {
            "member_id": _string(maximum=64), "age": {**integer, "minimum": 0, "maximum": 17},
        }),
        _operation_schema("remove_child", {"member_id": _string(maximum=64)}),
        _operation_schema("clarify", {
            "field": _string(maximum=128), "reason": _nullable_string(maximum=300),
        }),
    ]
    return {"anyOf": [
        _closed_object({"ops": _array({"anyOf": ops}, maximum=12)}),
        {"type": "null"},
    ]}


def _authorization_schema() -> dict[str, Any]:
    return _closed_object({
        "operation_index": {"type": "integer", "minimum": 0, "maximum": 11},
        "op": {"type": "string", "enum": list(PATCH_OPERATIONS)},
        "target_fields": _array(_string(maximum=128), maximum=2, minimum=1),
        "intent": {"type": "string", "enum": ["explicit_request", "clarification"]},
        "current_turn_quote": _string(maximum=500),
    })


def _common_preparation_properties() -> dict[str, Any]:
    return {
        "guest_patch": _patch_schema(),
        "guest_patch_authorizations": _array(_authorization_schema(), maximum=12),
        "turn_intents": _array(
            {"type": "string", "enum": list(TURN_INTENTS)}, maximum=4, minimum=1,
        ),
        "explicit_language_tag": _nullable_string(maximum=64),
        "inferred_language_tag": _nullable_string(maximum=64),
    }


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    return _closed_object({"response": body})


def fact_selection_output_schema() -> dict[str, Any]:
    properties = {
        "fact_ids": _array(_string(maximum=128), maximum=20),
        **_common_preparation_properties(),
    }
    return _envelope(_closed_object(properties))


def preparation_answer_output_schema(
    missing_label_keys: tuple[str, ...], label_bundle_keys: tuple[str, ...],
) -> dict[str, Any]:
    """Shape a high-overlap prep answer without weakening the ordinary answer parser."""
    claim = _closed_object({"text": _string(), "fact_ids": _array(_string(maximum=128), maximum=10, minimum=1)})
    guest_claim = _closed_object({"text": _string(), "refs": _array(_string(maximum=128), maximum=10, minimum=1)})
    label_variants = []
    for keys in dict.fromkeys((tuple(missing_label_keys), tuple(label_bundle_keys))):
        keys = tuple(dict.fromkeys(keys))
        label_variants.append(_closed_object({key: _string(maximum=80) for key in keys}))
    properties = {
        "supported_claims": _array(claim, maximum=20),
        "unknowns": _array(_string(), maximum=20),
        "conflicts": _array(_string(), maximum=10),
        **_common_preparation_properties(),
        "guest_claims": _array(guest_claim, maximum=20),
        "guest_clarification": {"type": "null"},
        "conversational_acknowledgement": {"type": "null"},
        "guest_brief_refs": _array(_string(maximum=128), maximum=20),
        "label_bundle": {"anyOf": label_variants},
    }
    branches: list[dict[str, Any]] = []
    for channel in ("supported_claims", "unknowns", "conflicts", "guest_claims"):
        branch_properties = deepcopy(properties)
        branch_properties[channel]["minItems"] = 1
        branches.append(_closed_object(branch_properties))
    patch_properties = deepcopy(properties)
    patch = patch_properties["guest_patch"]
    patch_properties["guest_patch"] = patch["anyOf"][0]
    patch_properties["guest_patch"]["properties"]["ops"]["minItems"] = 1
    branches.append(_closed_object(patch_properties))
    return _envelope({"anyOf": branches})
