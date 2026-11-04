from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError
from staylead_platform.domains.hospitality.prompts.grounded_qa import GUEST_BRIEF_PATCH_RULES
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    HospitalityGuestBriefPatch,
    validate_guest_brief_proposal,
    validate_guest_patch_authorization,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    fact_selection_output_schema,
)
from staylead_platform.platform.contracts.guest_brief import GuestBriefProposal, GuestBriefSnapshot


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_explicit_soft_view_clear_budget_edit_and_child_add_preserve_unedited_state() -> None:
    child_id = "7f7829fc-8688-4cc7-8ced-10b9f626e03f"
    brief = GuestBriefSnapshot(brief_version=4, data={
        "dates": {"check_in": "2027-02-10", "check_out": "2027-02-13", "nights": 3},
        "party": {
            "adults": 2,
            "children": [{"member_id": child_id, "age": 7}],
            "guardians": {child_id: "adult-1"},
        },
        "room_requirements": {
            "budget_amount": 5000000,
            "budget_currency": "VND",
            "budget_basis": "stay_total",
            "budget_strength": "target",
            "budget_inclusions": ["breakfast"],
            "hard_accessibility_needs": ["step_free"],
            "preferred_views": ["city view"],
        },
    })
    proposal = GuestBriefProposal((
        {"op": "set_room_requirements", "budget_amount": 4200000,
         "clear_fields": ["preferred_views"]},
        {"op": "add_child", "age": 11},
    ))

    applied = validate_guest_brief_proposal(brief, proposal)

    assert applied.data["dates"] == brief.data["dates"]
    assert applied.data["party"]["adults"] == 2
    saved_child = applied.data["party"]["children"][0]
    assert saved_child == {"member_id": child_id, "age": 7}
    assert applied.data["party"]["guardians"] == {child_id: "adult-1"}
    new_child = applied.data["party"]["children"][1]
    assert new_child["age"] == 11 and new_child["member_id"] != child_id
    assert "preferred_views" not in applied.data["room_requirements"]
    assert applied.data["room_requirements"] == {
        "budget_amount": 4200000,
        "budget_currency": "VND",
        "budget_basis": "stay_total",
        "budget_strength": "target",
        "budget_inclusions": ["breakfast"],
        "hard_accessibility_needs": ["step_free"],
    }
    assert applied.applied_delta == {
        "room_requirements": {"preferred_views": None, "budget_amount": 4200000},
        "party": {"children_added": [new_child]},
    }


def test_explicit_soft_view_is_native_wire_and_exact_quote_authorized() -> None:
    brief = GuestBriefSnapshot(brief_version=0, data={"dates": {}, "party": {"adults": 2, "children": []}})
    schema = fact_selection_output_schema(brief)
    room_ops = [
        node for node in _walk(schema)
        if node.get("type") == "object"
        and node.get("properties", {}).get("op", {}).get("enum") == ["set_room_requirements"]
    ]
    assert room_ops
    view_schema = room_ops[0]["properties"]["preferred_views"]
    assert any(item.get("maxItems") == 8 for item in view_schema["anyOf"] if isinstance(item, dict))

    operation = {"op": "set_room_requirements", "preferred_views": ["city view"]}
    parsed = HospitalityGuestBriefPatch.model_validate({"ops": [{
        **operation, "current_turn_quote": "I would prefer a city view.",
    }]})
    canonical = parsed.ops[0].model_dump(exclude_none=True)
    assert canonical["preferred_views"] == ["city view"]
    validate_guest_patch_authorization(
        (operation,), [{
            "operation_index": 0,
            "op": "set_room_requirements",
            "target_fields": ["room_requirements.preferred_views"],
            "intent": "explicit_request",
            "current_turn_quote": "I would prefer a city view.",
        }], "I would prefer a city view.",
    )
    with pytest.raises(ValueError, match="Guest edit authorization does not match the current turn operation"):
        validate_guest_patch_authorization(
            (operation,), [{
                "operation_index": 0,
                "op": "set_room_requirements",
                "target_fields": ["room_requirements.preferred_views"],
                "intent": "explicit_request",
                "current_turn_quote": "I prefer a city view.",
            }], "I would prefer a city view.",
        )
    assert "tentative suggestion" in GUEST_BRIEF_PATCH_RULES
    assert "negation" in GUEST_BRIEF_PATCH_RULES


def test_view_values_are_bounded_and_hard_view_is_not_a_supported_operation() -> None:
    with pytest.raises(ValidationError):
        HospitalityGuestBriefPatch.model_validate({"ops": [{
            "op": "set_room_requirements", "preferred_views": ["x" * 65],
        }]})
    with pytest.raises(ValidationError):
        HospitalityGuestBriefPatch.model_validate({"ops": [{
            "op": "set_room_requirements", "hard_views": ["sea view"],
        }]})
    with pytest.raises(ValidationError):
        HospitalityGuestBriefPatch.model_validate({"ops": [{
            "op": "set_room_requirements", "preferred_views": ["city view"] * 9,
        }]})


def test_native_clear_schema_exposes_only_present_soft_view() -> None:
    brief = GuestBriefSnapshot(
        brief_version=1,
        data={"dates": {}, "party": {"adults": 1, "children": []},
              "room_requirements": {"preferred_views": ["city view"]}},
    )
    schema = fact_selection_output_schema(brief)
    clear_variants = [
        node for node in _walk(schema)
        if node.get("type") == "array"
        and "preferred_views" in node.get("items", {}).get("enum", [])
    ]
    assert clear_variants
    serialized = json.dumps(schema)
    assert '"preferred_views"' in serialized


def test_all_thirteen_room_requirement_fields_clear_and_authorize_with_bounded_limit() -> None:
    fields = [
        "budget_amount",
        "budget_currency",
        "budget_basis",
        "budget_strength",
        "budget_inclusions",
        "sharing",
        "hard_accessibility_needs",
        "preferred_accessibility_needs",
        "hard_bed_types",
        "preferred_bed_types",
        "preferred_views",
        "avoided_bed_types",
        "max_rooms",
    ]
    quote = "Clear every saved room preference and requirement."
    operation = {
        "op": "set_room_requirements",
        "clear_fields": fields,
        "current_turn_quote": quote,
    }

    parsed = HospitalityGuestBriefPatch.model_validate({"ops": [operation]})

    assert parsed.ops[0].clear_fields == fields
    validate_guest_patch_authorization(
        ({key: value for key, value in operation.items() if key != "current_turn_quote"},),
        [{
            "operation_index": 0,
            "op": "set_room_requirements",
            "target_fields": [f"room_requirements.{field}" for field in fields],
            "intent": "explicit_request",
            "current_turn_quote": quote,
        }],
        quote,
    )

    with pytest.raises(ValidationError):
        HospitalityGuestBriefPatch.model_validate({"ops": [{
            "op": "set_room_requirements", "clear_fields": [*fields, "preferred_views"],
        }]})
