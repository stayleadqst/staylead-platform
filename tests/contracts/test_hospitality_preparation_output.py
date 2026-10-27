"""Native preparation schemas keep strict provider output aligned with Hospitality models."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from staylead_platform.domains.hospitality.schemas.fact_selection import FactSelection
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
)
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    validate_guest_brief_proposal,
    validate_preparation_metadata,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    fact_selection_output_schema,
    preparation_answer_output_schema,
)
from staylead_platform.platform.contracts.guest_brief import GuestBriefProposal, GuestBriefSnapshot


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


def _assert_supported_structured_output_composition(value: Any) -> None:
    unsupported = {"not", "allOf", "oneOf", "if", "then", "else", "dependentSchemas", "unevaluatedProperties"}
    if isinstance(value, dict):
        assert unsupported.isdisjoint(value)
        for child in value.values():
            _assert_supported_structured_output_composition(child)
    elif isinstance(value, list):
        for child in value:
            _assert_supported_structured_output_composition(child)


def _selection_payload() -> dict[str, Any]:
    return {
        "fact_ids": [],
        "guest_patch": {"ops": [
            {"op": "set_dates", "check_in": "2026-12-10", "check_out": None,
             "current_turn_quote": "check-in is 2026-12-10"},
            {"op": "set_adults", "count": 2, "current_turn_quote": "two adults"},
        ]},
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
        _assert_supported_structured_output_composition(schema)
    assert schemas[0]["properties"]["response"]["type"] == "object"
    assert "anyOf" in schemas[1]["properties"]["response"]

    low_schema = schemas[0]["properties"]["response"]
    assert "guest_patch_authorizations" not in low_schema["properties"]
    patch = low_schema["properties"]["guest_patch"]["anyOf"][0]
    op_schemas = patch["properties"]["ops"]["items"]["anyOf"]
    operations = [variant for item in op_schemas for variant in item.get("anyOf", (item,))]
    assert all(operation["properties"]["op"]["type"] == "string" for operation in operations)
    assert all("current_turn_quote" in operation["required"] for operation in operations)
    assert all(operation["properties"]["current_turn_quote"]["maxLength"] == 500 for operation in operations)
    add_child_variants = next(
        item["anyOf"] for item in op_schemas
        if item.get("anyOf", [{}])[0].get("properties", {}).get("op", {}).get("enum") == ["add_child"]
    )
    for variant in add_child_variants:
        properties = variant["properties"]
        assert properties["share_bed_with_guardian"]["type"] == ["boolean", "null"]
        assert properties["requires_separate_bed"]["type"] in (["boolean", "null"], "null")
    add_child_variants = next(item["anyOf"] for item in op_schemas
                              if item.get("anyOf", [{}])[0].get("properties", {}).get("op", {}).get("enum") == ["add_child"])
    for variant in add_child_variants:
        properties = variant["properties"]
        assert properties["share_bed_with_guardian"]["type"] == ["boolean", "null"]
        assert properties["requires_separate_bed"]["type"] in (["boolean", "null"], "null")


def test_inline_quotes_are_derived_and_parallel_authorization_metadata_is_rejected() -> None:
    captured = _selection_payload()
    selection = FactSelection.model_validate_json(json.dumps(captured))
    assert len(selection.fact_ids) == 0
    assert [operation.op for operation in selection.guest_patch.ops] == ["set_dates", "set_adults"]
    intents, authorizations = validate_preparation_metadata(
        selection, GuestBriefProposal(tuple(item.model_dump(mode="json") for item in selection.guest_patch.ops)),
        "check-in is 2026-12-10 and two adults",
    )
    assert intents == ("guest_edit",)
    assert [item["op"] for item in authorizations] == ["set_dates", "set_adults"]
    assert [item["target_fields"] for item in authorizations] == [["dates.check_in"], ["party.adults"]]
    assert validate_preparation_metadata(
        selection, GuestBriefProposal(tuple(item.model_dump(mode="json") for item in selection.guest_patch.ops)),
        "check-in is 2026-12-10 and two adults",
    ) == (intents, authorizations)
    with pytest.raises(ValueError, match="derived from inline"):
        validate_preparation_metadata(
            FactSelection.model_validate({**captured, "guest_patch_authorizations": []}),
            GuestBriefProposal(tuple(item.model_dump(mode="json") for item in selection.guest_patch.ops)),
            "check-in is 2026-12-10 and two adults",
        )
    without_quote = _selection_payload()
    without_quote["guest_patch"]["ops"][0].pop("current_turn_quote")
    with pytest.raises(ValidationError):
        FactSelection.model_validate(without_quote)

    corrected = _selection_payload()
    corrected.pop("fact_ids")
    corrected["supported_claims"] = []
    corrected["unknowns"] = []
    corrected["conflicts"] = []
    corrected["guest_claims"] = []
    corrected["guest_clarification"] = None
    corrected["conversational_acknowledgement"] = None
    corrected["guest_brief_refs"] = []
    corrected["label_bundle"] = {"send": "Send"}
    answer = HospitalityGroundedAnswer.model_validate(corrected)
    _, answer_authorizations = validate_preparation_metadata(
        answer, GuestBriefProposal(tuple(item.model_dump(mode="json") for item in answer.guest_patch.ops)),
        "check-in is 2026-12-10 and two adults",
    )
    assert [authorization["op"] for authorization in answer_authorizations] == ["set_dates", "set_adults"]


def test_empty_fact_selection_and_noop_metadata_are_valid() -> None:
    payload = {
        "fact_ids": [], "guest_patch": None,
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
        "guest_patch": None, "turn_intents": ["hotel_information"],
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


def test_sharing_schema_uses_only_canonical_adults_and_current_saved_child_ids() -> None:
    saved_child_id = "4ed1bb17-dde4-4964-ad7f-cfc9a088b553"
    brief = GuestBriefSnapshot(3, {
        "party": {"adults": 2, "children": [{"member_id": saved_child_id, "age": 7}]},
    })

    def member_id_enum(schema: dict[str, Any]) -> list[str]:
        body = schema["properties"]["response"]
        branch = next(item for item in body.get("anyOf", (body,))
                      if "guest_patch" in item.get("properties", {}))
        patch = branch["properties"]["guest_patch"]["anyOf"][0]
        ops = patch["properties"]["ops"]["items"]["anyOf"]
        operations = [variant for item in ops for variant in item.get("anyOf", (item,))]
        operation = next(item for item in operations
                         if item["properties"]["op"].get("enum") == ["set_bed_sharing"])
        return operation["properties"]["member_ids"]["items"]["enum"]

    for schema in (
        fact_selection_output_schema(brief),
        preparation_answer_output_schema(("send",), ("send",), brief),
    ):
        allowed_ids = member_id_enum(schema)
        assert allowed_ids == [*(f"adult-{index}" for index in range(1, 31)), saved_child_id]
        assert "child-1" not in allowed_ids

    question = "We are two adults and our seven-year-old may share my bed; I am the guardian."
    malformed = GuestBriefProposal(({
        "op": "set_bed_sharing", "member_ids": ["adult-1", "child-1"], "allow_share": True,
        "current_turn_quote": question,
    },))
    with pytest.raises(ValueError, match="distinct current party members"):
        validate_guest_brief_proposal(brief, malformed)
    valid_saved_child = GuestBriefProposal(({
        "op": "set_bed_sharing", "member_ids": ["adult-1", saved_child_id], "allow_share": True,
        "current_turn_quote": "our seven-year-old may share my bed",
    },))
    updated = validate_guest_brief_proposal(brief, valid_saved_child)
    assert updated.data["party"]["bed_sharing"] == [{
        "member_ids": sorted(("adult-1", saved_child_id)), "allow_share": True,
    }]


def test_new_child_sharing_is_valid_only_through_inline_add_child_consent() -> None:
    brief = GuestBriefSnapshot(0, {"party": {"adults": 1, "children": []}})
    question = "We are one adult and our seven-year-old may share my bed; I am the guardian."
    proposal = GuestBriefProposal(({
        "op": "add_child", "age": 7, "guardian_adult_index": 1,
        "share_bed_with_guardian": True, "current_turn_quote": question,
    },))

    updated = validate_guest_brief_proposal(brief, proposal)
    child = updated.data["party"]["children"][0]
    child_id = child["member_id"]
    assert updated.data["party"]["guardians"][child_id] == "adult-1"
    assert updated.data["party"]["bed_sharing"] == [{
        "member_ids": sorted(("adult-1", child_id)), "allow_share": True,
    }]
