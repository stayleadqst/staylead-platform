"""Native preparation schemas keep strict provider output aligned with Hospitality models."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from staylead_platform.domains.hospitality.prompts.grounded_qa import (
    GUEST_BRIEF_PATCH_RULES,
)
from staylead_platform.domains.hospitality.schemas.fact_selection import FactSelection
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    fact_selection_output_schema,
    preparation_answer_output_schema,
)


def _assert_strict_objects(schema: dict[str, Any]) -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties", {})
        assert schema.get("additionalProperties") is False
        assert schema.get("required") == list(properties)
        for value in properties.values():
            _assert_strict_objects(value)
    if schema_type == "array":
        _assert_strict_objects(schema["items"])
    for variant in schema.get("anyOf", ()):
        _assert_strict_objects(variant)


def _selection_payload() -> dict[str, Any]:
    return {
        "fact_ids": [],
        "guest_patch": {"ops": [
            {"op": "set_dates", "check_in": "2026-12-10", "check_out": None},
            {"op": "set_adults", "count": 2},
        ]},
        "guest_patch_authorizations": [
            {"operation_index": 0, "op": "set_dates", "target_fields": ["dates.check_in"],
             "intent": "explicit_request", "current_turn_quote": "check-in is 2026-12-10"},
            {"operation_index": 1, "op": "set_adults", "target_fields": ["party.adults"],
             "intent": "explicit_request", "current_turn_quote": "two adults"},
        ],
        "turn_intents": ["guest_edit"],
        "explicit_language_tag": None,
        "inferred_language_tag": "en",
    }


def test_low_and_high_overlap_schemas_are_closed_and_use_string_operation_names() -> None:
    schemas = (
        fact_selection_output_schema(),
        preparation_answer_output_schema(("send",), ("send", "hours")),
    )
    for schema in schemas:
        _assert_strict_objects(schema)
    assert schemas[0]["properties"]["response"]["type"] == "object"
    assert "anyOf" in schemas[1]["properties"]["response"]

    low_schema = schemas[0]["properties"]["response"]
    auth_op = low_schema["properties"]["guest_patch_authorizations"]["items"]["properties"]["op"]
    assert auth_op == {
        "type": "string",
        "enum": ["set_dates", "set_adults", "add_child", "set_child_age", "remove_child",
                 "set_room_requirements", "set_child_guardian", "set_bed_sharing", "clarify"],
    }
    patch = low_schema["properties"]["guest_patch"]["anyOf"][0]
    op_schemas = patch["properties"]["ops"]["items"]["anyOf"]
    assert all(operation["properties"]["op"]["type"] == "string" for operation in op_schemas)


def test_captured_object_valued_authorization_op_is_rejected_and_string_op_is_accepted() -> None:
    assert "operation-name string only" in GUEST_BRIEF_PATCH_RULES
    captured = _selection_payload()
    captured["guest_patch_authorizations"][0]["op"] = {
        "op": "set_dates", "check_in": "2026-12-10", "check_out": None,
    }
    with pytest.raises(ValidationError):
        FactSelection.model_validate_json(json.dumps(captured))

    corrected = _selection_payload()
    selection = FactSelection.model_validate_json(json.dumps(corrected))
    assert len(selection.fact_ids) == 0
    assert [operation.op for operation in selection.guest_patch.ops] == ["set_dates", "set_adults"]
    assert [authorization.op for authorization in selection.guest_patch_authorizations] == [
        "set_dates", "set_adults",
    ]

    corrected["supported_claims"] = []
    corrected["unknowns"] = []
    corrected["conflicts"] = []
    corrected["guest_claims"] = []
    corrected["guest_clarification"] = None
    corrected["conversational_acknowledgement"] = None
    corrected["guest_brief_refs"] = []
    corrected["label_bundle"] = {"send": "Send"}
    answer = HospitalityGroundedAnswer.model_validate(corrected)
    assert [authorization.op for authorization in answer.guest_patch_authorizations] == [
        "set_dates", "set_adults",
    ]


def test_empty_fact_selection_and_noop_metadata_are_valid() -> None:
    payload = {
        "fact_ids": [], "guest_patch": None, "guest_patch_authorizations": [],
        "turn_intents": ["guest_state"], "explicit_language_tag": None,
        "inferred_language_tag": None,
    }
    parsed = FactSelection.model_validate(payload)
    assert parsed.fact_ids == []
    assert parsed.guest_patch is None
    assert parsed.guest_patch_authorizations == []


def test_high_overlap_prep_schema_keeps_flat_provider_response_compatible() -> None:
    schema = preparation_answer_output_schema(("send",), ("send", "hours"))
    flat = {
        "supported_claims": [], "unknowns": [], "conflicts": [],
        "guest_patch": None, "guest_patch_authorizations": [], "turn_intents": ["hotel_information"],
        "guest_claims": [], "guest_clarification": None, "conversational_acknowledgement": None,
        "guest_brief_refs": [], "explicit_language_tag": None, "inferred_language_tag": None,
        "label_bundle": {"send": "Send"},
    }
    _assert_strict_objects(schema)
    response_schema = schema["properties"]["response"]
    branches = response_schema["anyOf"]
    assert len(branches) == 5
    assert all(
        branch["properties"]["guest_clarification"] == {"type": "null"}
        and branch["properties"]["conversational_acknowledgement"] == {"type": "null"}
        for branch in branches
    )
    assert all(
        any(branch["properties"][name]["minItems"] == 1 for name in (
            "supported_claims", "unknowns", "conflicts", "guest_claims",
        ))
        or branch["properties"]["guest_patch"].get("type") == "object"
        for branch in branches
    )
    # Adapters that ignore schema/envelope hints continue returning the original flat domain object.
    HospitalityGroundedAnswer.model_validate(flat)
