from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, replace
from typing import get_args

import pytest
from pydantic import ValidationError

from staylead_platform.domains.hospitality.prompts.grounded_qa import GUEST_BRIEF_PATCH_RULES
from staylead_platform.domains.hospitality.recommendations.rooms import (
    HospitalityRoomAdvice,
)
from staylead_platform.domains.hospitality.schemas.fact_selection import FactSelection
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
)
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    GuestPatchAuthorization,
    GuestTurnIntent,
    validate_guest_brief_proposal,
    validate_guest_patch_authorization,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    TURN_INTENTS,
    fact_selection_output_schema,
    preparation_answer_output_schema,
)
from staylead_platform.domains.hospitality.schemas.room_advice import (
    RoomAdvicePreparation,
    RoomAdviceQuestion,
    RoomRationale,
    room_advice_output_schema,
)
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefProposal,
    GuestBriefSnapshot,
)
from staylead_platform.platform.contracts.room_advice import (
    RoomAdviceCandidate,
    RoomAdviceContext,
    RoomAdviceDraft,
)
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    GroundedQAOrchestrator,
)


def _fact(fact_id: str, field: str, value: dict, *, generation: int = 7) -> dict:
    return {
        "fact_id": fact_id, "hotel_id": "HTL-SYNTH", "topic": "room_catalog" if field == "room_type" else "room_rates",
        "subject": "room" if field == "room_type" else "rate", "field": field,
        "value": value, "conditions": {}, "status": "confirmed",
        "valid_from": "2026-10-01", "valid_to": "2027-09-30",
        "provenance": {"source_id": "SRC-CATALOG", "source_version": "1.0",
                       "source_hash": "abc", "source_generation": generation},
    }


def _catalog(*, room_id: str = "FAM", beds: list[dict] | None = None, max_occupancy: int = 4) -> dict:
    return _fact("F-ROOM", "room_type", {
        "room_type_id": room_id, "name": "Family room", "max_occupancy": max_occupancy,
        "max_adults": 4, "max_children": 3,
        "beds": beds or [{"type": "queen", "count": 1, "occupant_capacity": 2},
                         {"type": "twin", "count": 2, "occupant_capacity": 1}],
        "age_policy": {"room_min_age_inclusive": 0, "room_max_age_exclusive": None,
                       "guardian_required_below_age_exclusive": 18,
                       "child_rate_age_max_exclusive": 12},
        "cot_rule": {"allowed": False, "status": "conflict"},
        "extra_bed": {"allowed": None, "status": "unknown"},
        "accessible": "Wheelchair bathroom access not confirmed.",
    })


def _rate(*, amount: int = 100, child_amount: int | None = None) -> dict:
    return _fact("F-RATE", "reference_rate", {
        "rate_id": "RATE-FAM", "room_type_id": "FAM", "amount": amount, "currency": "VND",
        "status": "reference_only", "is_quote": False, "is_live_availability": False,
        "price_basis": {"unit": "room_night", "included_adults": 2},
        "child_charge_amount": child_amount,
        "child_charge_currency": "VND", "child_charge_basis": "per child per room night",
        "child_charge_status": "confirmed" if child_amount is not None else "unknown",
        "extra_adult_charge_amount": None, "extra_adult_charge_currency": "VND",
        "extra_adult_charge_basis": "per adult per room night",
        "extra_adult_charge_status": "unknown",
    })


class _CurrentFactRetriever:
    """Small stand-in for M1's current-facts-by-ID repository boundary."""

    def __init__(self, facts: tuple[dict, ...], generation: int = 7) -> None:
        self.facts = facts
        self.generation = generation

    def get_by_ids(self, hotel_id: str, fact_ids: set[str], *, timeout_seconds=None) -> tuple[dict, ...]:
        del timeout_seconds
        from datetime import UTC, datetime

        today = datetime.now(UTC).date().isoformat()
        return tuple(fact for fact in self.facts if (
            fact.get("hotel_id") == hotel_id
            and fact.get("fact_id") in fact_ids
            and fact.get("status") in {"confirmed", "unknown", "needs_confirmation"}
            and fact.get("valid_from", "9999-12-31") <= today <= fact.get("valid_to", "0000-01-01")
            and fact.get("provenance", {}).get("source_generation", self.generation) == self.generation
        ))


def _context(brief: dict, facts: tuple[dict, ...]) -> RoomAdviceContext:
    return RoomAdviceContext(
        hotel_id="HTL-SYNTH", brief_version=4, brief_data=brief,
        pending_fields=(), source_generation=7, facts=facts,
        question="Find a suitable room", locale="zh",
    )


def test_couple_sharing_is_checked_and_reference_total_is_independently_calculated() -> None:
    room, rate = _catalog(), _rate()
    brief = {
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
        "party": {"adults": 2, "children": [],
                  "bed_sharing": [{"member_ids": ["adult-1", "adult-2"], "allow_share": True}]},
    }
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=tuple({"member_id": f"adult-{n}", "room_index": 0,
                           "bed_index": 0, "bed_type": "queen"} for n in (1, 2)),
        rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"]},
                   {"claim_code": "reference_price", "fact_ids": ["F-RATE"]}),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "ready"
    option = result.options[0]
    assert option["cost"]["total"] == 200
    assert option["cost"]["status"] == "complete"
    assert {item["code"]: item["status"] for item in option["checks"]}["bed_sharing_consent"] == "pass"
    assert [claim["claim_code"] for claim in option["rationale"]] == ["party_fit", "reference_price"]
    assert option["rationale"][0]["text"] == "此安排符合已确认的入住人数和房间规则。"
    assert option["rationale"][1]["text"] == "本次入住的参考房费估算：200 VND。"
    assert result.availability == "unknown"
    assert all(ref["source_generation"] == 7 for ref in result.source_refs)


def test_child_guardian_age_and_unknown_child_fee_prevent_complete_budget_claim() -> None:
    room, rate = _catalog(), _rate()
    brief = {
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
        "party": {"adults": 2, "children": [{"member_id": "child-1", "age": 7}],
                  "guardians": {"child-1": "adult-1"},
                  "bed_sharing": [{"member_ids": ["adult-1", "adult-2"], "allow_share": True}]},
    }
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "adult-2", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-1", "room_index": 0, "bed_index": 1, "bed_type": "twin"},
        ),
        rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"]},
                   {"claim_code": "reference_price", "fact_ids": ["F-RATE"]},
                   {"claim_code": "charges_confirmation", "fact_ids": ["F-RATE"]}),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    option = result.options[0]
    checks = {item["code"]: item["status"] for item in option["checks"]}
    assert checks["guardian_relationship"] == "pass"
    assert checks["child_age_policy"] == "pass"  # Age 7 uses the declared range, not sample-only boundary rows.
    assert option["cost"]["nightly_subtotal"] == 100
    assert option["cost"]["total"] is None
    assert option["cost"]["status"] == "incomplete"
    assert not any(claim["claim_code"] == "reference_price" for claim in option["rationale"])
    assert any(claim["claim_code"] == "charges_confirmation" and claim["text"] ==
               "此估算未包含部分儿童费用或额外床位费用。" for claim in option["rationale"])
    assert result.status == "partial"


def test_missing_source_version_and_unsupported_model_rationale_are_not_released() -> None:
    room, rate = _catalog(), _rate()
    room["provenance"] = {"source_generation": 6, "source_id": "SRC-OLD", "source_version": "1.0"}
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": []}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
        rationale=({"claim_code": "party_fit", "text": "Room is available and guaranteed.", "fact_ids": ["F-RATE"]},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "unsupported"
    assert result.options == ()


def test_adversarial_free_text_is_rejected_and_localized_rationale_uses_checked_template() -> None:
    room, rate = _catalog(), _rate()
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": []}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
        rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"],
                    "text": "此房型包含免费晚餐和专属折扣。"},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.options == ()
    assert result.status == "unsupported"

    trusted = RoomAdviceCandidate(
        option_id="B", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
        rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"]},),
    )
    fallback = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=replace(_context(brief, (room, rate)), locale="ko"),
        draft=RoomAdviceDraft("ready", (trusted,)),
    ))
    rationale = fallback.options[0]["rationale"][0]
    assert rationale["locale"] == "en"
    assert rationale["locale_fallback"] is True


def test_native_room_advice_schema_parses_localized_mixed_room_candidates() -> None:
    schema = room_advice_output_schema()
    assert schema["additionalProperties"] is False
    option_schema = schema["properties"]["response"]["properties"]["options"]["items"]
    assert option_schema["additionalProperties"] is False
    rationale_schema = option_schema["properties"]["rationale"]["items"]["properties"]["claim_code"]
    assert set(rationale_schema["enum"]) == set(get_args(RoomRationale.model_fields["claim_code"].annotation))
    assert set(RoomAdviceQuestion.model_fields) == {"field"}
    payload = RoomAdvicePreparation.model_validate({
        "options": [{
            "option_id": "A",
            "rooms": [{"room_index": 0, "room_type_id": "CITY-STD"},
                      {"room_index": 1, "room_type_id": "CITY-FAM"}],
            "assignments": [{"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"}],
            "rationale": [{"claim_code": "policy_confirmation", "fact_ids": ["F-ROOM"]}],
        }], "questions": [],
    })
    assert len(payload.options[0].rooms) == 2
    assert payload.options[0].rationale[0].claim_code == "policy_confirmation"


def test_duplicate_rooms_and_unassigned_rooms_are_rejected() -> None:
    room, rate = _catalog(), _rate()
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": []}}
    duplicate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},
                               {"room_index": 0, "room_type_id": "FAM"}),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (duplicate,)),
    ))
    assert result.options == ()
    assert "duplicate_room_index" in result.explanation_inputs["conflicts"]


def test_missing_dates_preserve_nightly_reference_estimate_and_mark_total_partial() -> None:
    room, rate = _catalog(), _rate(amount=1_800_000)
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context({"party": {"adults": 1, "children": []}}, (room, rate)),
        draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    cost = result.options[0]["cost"]
    assert cost["nightly_subtotal"] == 1_800_000
    assert cost["total"] is None
    assert cost["status"] == "incomplete"
    assert result.status == "partial"


def test_preparation_native_and_pydantic_intents_are_in_parity_and_support_booking() -> None:
    assert set(get_args(GuestTurnIntent)) == set(TURN_INTENTS)
    assert FactSelection.model_validate({"turn_intents": ["booking_request"]}).turn_intents == ["booking_request"]
    assert HospitalityGroundedAnswer.model_validate({"turn_intents": ["booking_request"]}).turn_intents == ["booking_request"]
    add_child = {"op": "add_child", "age": 5, "guardian_adult_index": 1,
                 "share_bed_with_guardian": True}
    authorization = {"operation_index": 0, "op": "add_child",
                     "target_fields": ["party.children", "party.guardians", "party.bed_sharing"],
                     "intent": "explicit_request", "current_turn_quote": "My child will share with me."}
    payload = {"turn_intents": ["guest_edit", "booking_request"],
               "guest_patch": {"ops": [add_child]}, "guest_patch_authorizations": [authorization]}
    assert len(FactSelection.model_validate(payload).guest_patch_authorizations[0].target_fields) == 3
    assert len(HospitalityGroundedAnswer.model_validate(payload).guest_patch_authorizations[0].target_fields) == 3
    fact_response = fact_selection_output_schema()["properties"]["response"]["properties"]
    answer_response = preparation_answer_output_schema((), ())["properties"]["response"]["anyOf"][0]["properties"]
    answer_schema = answer_response["turn_intents"]
    assert fact_response["turn_intents"]["items"]["enum"] == list(TURN_INTENTS)
    assert answer_schema["items"]["enum"] == list(TURN_INTENTS)
    pydantic_target_schema = GuestPatchAuthorization.model_json_schema()["properties"]["target_fields"]
    for response in (fact_response, answer_response):
        authorization = response["guest_patch_authorizations"]["items"]
        assert authorization["properties"]["target_fields"]["maxItems"] == 11
        target_item = authorization["properties"]["target_fields"]["items"]
        target_enum = target_item["anyOf"][0]["enum"]
        assert "room_requirements" in target_enum
        assert "room_requirements.budget_amount" in target_enum
        assert "room_requirements.max_rooms" in target_enum
        assert pydantic_target_schema["maxItems"] == 11
        assert target_item["anyOf"][0]["maxLength"] == pydantic_target_schema["items"]["maxLength"] == 128
        assert target_item["anyOf"][1]["maxLength"] == pydantic_target_schema["items"]["maxLength"]
        pydantic_pattern = re.compile(pydantic_target_schema["items"]["pattern"])
        dynamic_pattern = re.compile(target_item["anyOf"][1]["pattern"])
        assert all(pydantic_pattern.fullmatch(field) for field in target_enum)
        assert dynamic_pattern.fullmatch("party.children.123e4567.age")
        assert pydantic_pattern.fullmatch("party.children.123e4567.age")
        assert not dynamic_pattern.fullmatch("room_requirements.budget_basis,room_requirements.max_rooms")
        assert not pydantic_pattern.fullmatch("room_requirements.budget_basis,room_requirements.max_rooms")
        add_child = response["guest_patch"]["anyOf"][0]["properties"]["ops"]["items"]["anyOf"][2]
        assert {"guardian_adult_index", "share_bed_with_guardian"} <= set(add_child["properties"])
    assert "Whenever `guest_patch.ops` contains an edit, include `guest_edit`" in GUEST_BRIEF_PATCH_RULES
    assert "Do not infer a room" in GUEST_BRIEF_PATCH_RULES
    assert "set `max_rooms` only when the guest explicitly states a" in GUEST_BRIEF_PATCH_RULES
    assert "maximum number of rooms" in GUEST_BRIEF_PATCH_RULES


def test_room_requirement_clarification_uses_aggregate_target_but_edits_stay_granular() -> None:
    question = "Please clarify my room requirements."
    operation = {"op": "clarify", "field": "room_requirements", "reason": "Confirm the constraints."}
    authorization = {
        "operation_index": 0,
        "op": "clarify",
        "target_fields": ["room_requirements"],
        "intent": "clarification",
        "current_turn_quote": "room requirements",
    }
    validate_guest_patch_authorization((operation,), (authorization,), question)

    payload = {
        "turn_intents": ["guest_edit"],
        "guest_patch": {"ops": [operation]},
        "guest_patch_authorizations": [authorization],
    }
    for model in (FactSelection, HospitalityGroundedAnswer):
        parsed = model.model_validate(payload)
        assert parsed.guest_patch_authorizations[0].target_fields == ["room_requirements"]

    set_operation = {"op": "set_room_requirements", "budget_amount": 6_000_000}
    with pytest.raises(ValueError):
        validate_guest_patch_authorization(
            (set_operation,),
            ({**authorization, "op": "set_room_requirements", "intent": "explicit_request"},),
            question,
        )


def test_room_requirement_authorization_covers_four_budget_fields_and_up_to_eleven_canonical_targets() -> None:
    question = (
        "For the whole stay set a hard 6000000 VND maximum; avoid bed sharing; require step-free access; "
        "prefer near the lift; require queen, prefer twin, avoid bunk, and use at most 2 rooms."
    )
    operation = {
        "op": "set_room_requirements", "budget_amount": 6_000_000,
        "budget_currency": "VND", "budget_basis": "stay_total", "budget_strength": "hard",
        "sharing": "avoid", "hard_accessibility_needs": ["step-free"],
        "preferred_accessibility_needs": ["near lift"], "hard_bed_types": ["queen"],
        "preferred_bed_types": ["twin"], "avoided_bed_types": ["bunk"], "max_rooms": 2,
        "clear_fields": [],
    }
    target_fields = [
        "room_requirements.budget_amount", "room_requirements.budget_currency",
        "room_requirements.budget_basis", "room_requirements.budget_strength",
        "room_requirements.sharing", "room_requirements.hard_accessibility_needs",
        "room_requirements.preferred_accessibility_needs", "room_requirements.hard_bed_types",
        "room_requirements.preferred_bed_types", "room_requirements.avoided_bed_types",
        "room_requirements.max_rooms",
    ]
    authorization = {
        "operation_index": 0, "op": "set_room_requirements", "target_fields": target_fields,
        "intent": "explicit_request", "current_turn_quote": question,
    }
    validate_guest_patch_authorization((operation,), (authorization,), question)
    payload = {
        "turn_intents": ["guest_edit", "room_advice"],
        "guest_patch": {"ops": [operation]}, "guest_patch_authorizations": [authorization],
    }
    for model in (FactSelection, HospitalityGroundedAnswer):
        parsed = model.model_validate(payload)
        assert len(parsed.guest_patch_authorizations[0].target_fields) == 11
    with pytest.raises(ValueError):
        validate_guest_patch_authorization(
            (operation,), ({**authorization, "target_fields": ["room_requirements.budget_amount,"]},), question,
        )


def test_four_budget_targets_validate_with_null_native_placeholders_and_max_rooms_requires_explicit_target() -> None:
    question = "Ngân sách tối đa 6000000 VND cho toàn bộ tiền phòng."
    operation = {
        "op": "set_room_requirements", "budget_amount": 6_000_000,
        "budget_currency": "VND", "budget_basis": "stay_total", "budget_strength": "hard",
        "sharing": None, "hard_accessibility_needs": None,
        "preferred_accessibility_needs": None, "hard_bed_types": None,
        "preferred_bed_types": None, "avoided_bed_types": None, "max_rooms": None,
        "clear_fields": [],
    }
    targets = [
        "room_requirements.budget_amount", "room_requirements.budget_currency",
        "room_requirements.budget_basis", "room_requirements.budget_strength",
    ]
    authorization = {
        "operation_index": 0, "op": "set_room_requirements", "target_fields": targets,
        "intent": "explicit_request", "current_turn_quote": question,
    }
    validate_guest_patch_authorization((operation,), (authorization,), question)
    assert "room_requirements.max_rooms" not in targets
    payload = {
        "turn_intents": ["guest_edit", "room_advice"],
        "guest_patch": {"ops": [operation]}, "guest_patch_authorizations": [authorization],
    }
    FactSelection.model_validate(payload)
    HospitalityGroundedAnswer.model_validate(payload)
    with pytest.raises(ValidationError):
        FactSelection.model_validate({
            **payload,
            "guest_patch_authorizations": [{**authorization, "target_fields": [
                "room_requirements.budget_amount",
                "room_requirements.budget_currency,room_requirements.budget_basis",
            ]}],
        })

    clear_operation = {
        "op": "set_room_requirements", "budget_amount": None, "budget_currency": None,
        "budget_basis": None, "budget_strength": None, "sharing": None,
        "hard_accessibility_needs": None, "preferred_accessibility_needs": None,
        "hard_bed_types": None, "preferred_bed_types": None, "avoided_bed_types": None,
        "max_rooms": None, "clear_fields": ["budget_amount", "max_rooms"],
    }
    clear_authorization = {
        "operation_index": 0, "op": "set_room_requirements",
        "target_fields": ["room_requirements.budget_amount", "room_requirements.max_rooms"],
        "intent": "explicit_request", "current_turn_quote": "Clear the budget and room limit.",
    }
    validate_guest_patch_authorization(
        (clear_operation,), (clear_authorization,), "Clear the budget and room limit.",
    )


def test_native_null_room_requirement_placeholders_preserve_values_and_explicit_clear_works() -> None:
    current = GuestBriefSnapshot(2, {
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-02", "nights": 1},
        "party": {"adults": 2, "children": [], "bed_sharing": [
            {"member_ids": ["adult-1", "adult-2"], "allow_share": True}]},
        "room_requirements": {"budget_amount": 500, "budget_currency": "VND",
                              "budget_basis": "stay_total", "sharing": "allow",
                              "hard_accessibility_needs": ["step-free shower"]},
    })
    bed_only = {"op": "set_room_requirements", "budget_amount": None, "budget_currency": None,
                "budget_basis": None, "budget_strength": None, "sharing": None,
                "hard_accessibility_needs": None, "preferred_accessibility_needs": None,
                "hard_bed_types": ["queen"], "preferred_bed_types": None, "avoided_bed_types": None,
                "max_rooms": None, "clear_fields": []}
    updated = validate_guest_brief_proposal(current, GuestBriefProposal((bed_only,)))
    assert updated.data["room_requirements"]["budget_amount"] == 500
    assert updated.data["room_requirements"]["sharing"] == "allow"
    assert updated.data["room_requirements"]["hard_accessibility_needs"] == ["step-free shower"]
    assert updated.data["room_requirements"]["hard_bed_types"] == ["queen"]
    cleared = validate_guest_brief_proposal(current, GuestBriefProposal(({
        **bed_only, "hard_bed_types": None, "clear_fields": ["budget_amount"],
    },)))
    assert "budget_amount" not in cleared.data["room_requirements"]
    assert cleared.data["room_requirements"]["sharing"] == "allow"
    with __import__("pytest").raises(ValueError):
        validate_guest_brief_proposal(current, GuestBriefProposal(({
            **bed_only, "clear_fields": ["budget_amount"], "budget_amount": 200,
        },)))


def test_bunk_age_boundary_conflict_is_not_resolved_by_model_candidate() -> None:
    room = _catalog(room_id="PINE-CABIN", beds=[
        {"type": "queen", "count": 1, "occupant_capacity": 2},
        {"type": "bunk", "count": 1, "occupant_capacity": 2},
    ])
    room["value"]["age_policy"]["boundary_cases"] = [
        {"age_years": 5, "bedding_rule": "no upper bunk"},
        {"age_years": 6, "bedding_rule": "upper bunk prohibited"},
    ]
    room["value"]["age_and_sharing"] = "Upper bunk only from age 6."
    rate = _rate()
    rate["value"]["room_type_id"] = "PINE-CABIN"
    for age, expected_status, expected_option in ((5, "conflict", False), (6, "partial", True)):
        brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
                 "party": {"adults": 1, "children": [{"member_id": "child-1", "age": age}],
                           "guardians": {"child-1": "adult-1"}}}
        candidate = RoomAdviceCandidate(
            option_id="A", rooms=({"room_index": 0, "room_type_id": "PINE-CABIN"},),
            assignments=(
                {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
                {"member_id": "child-1", "room_index": 0, "bed_index": 1, "bed_type": "bunk", "bed_position": "upper"},
            ),
        )
        result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
            context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
        ))
        assert result.status == expected_status
        assert bool(result.options) is expected_option
        assert any(ref["fact_id"] == "F-ROOM" and ref["source_version"] == "1.0"
                   for ref in result.source_refs)


def test_cot_and_extra_bed_requirements_are_retained_as_policy_or_cost_unknowns() -> None:
    room, rate = _catalog(), _rate()
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
    )
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": []},
             "room_requirements": {"hard_bed_types": ["cot"]}}
    cot_result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert cot_result.status == "conflict"
    room["value"]["cot"] = "Nôi miễn phí, tối đa 1; cần xác nhận."
    conflicting_cot = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert conflicting_cot.status == "partial"
    assert {item["code"]: item["status"] for item in conflicting_cot.options[0]["checks"]}["cot_policy"] == "unknown"
    brief["room_requirements"] = {"hard_bed_types": ["extra bed"]}
    extra_result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert extra_result.status == "partial"
    checks = {item["code"]: item["status"] for item in extra_result.options[0]["checks"]}
    assert checks["extra_bed_policy"] == "unknown"
    assert extra_result.options[0]["cost"]["total"] is None


def test_sharing_avoid_and_hard_bed_types_apply_to_the_whole_assignment() -> None:
    room = _catalog(beds=[{"type": "queen", "count": 1, "occupant_capacity": 2},
                          {"type": "single", "count": 1, "occupant_capacity": 1}])
    rate = _rate()
    rate["value"]["price_basis"]["included_adults"] = 3
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "adult-2", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "adult-3", "room_index": 0, "bed_index": 1, "bed_type": "single"},
        ),
    )
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 3, "children": [], "bed_sharing": [
                 {"member_ids": ["adult-1", "adult-2"], "allow_share": True}]},
             "room_requirements": {"sharing": "avoid"}}
    avoided = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert avoided.status == "conflict"
    assert avoided.options == ()
    brief["room_requirements"] = {"hard_bed_types": ["single"]}
    bed_mismatch = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert bed_mismatch.status == "conflict"


def test_age_fifteen_remains_minor_but_uses_source_adult_rate_band() -> None:
    room, rate = _catalog(), _rate()
    rate["value"]["price_basis"]["included_adults"] = 1
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": [{"member_id": "child-15", "age": 15}],
                       "guardians": {"child-15": "adult-1"}}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-15", "room_index": 0, "bed_index": 1, "bed_type": "twin"},
        ),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    checks = {item["code"]: item["status"] for item in result.options[0]["checks"]}
    assert checks["guardian_relationship"] == "pass"
    assert result.options[0]["cost"]["status"] == "incomplete"  # Adult-rate band extra fee is unknown.
    assert any(item["label"] == "extra adult charges" for item in result.options[0]["cost"]["breakdown"])


def test_confirmed_cross_currency_child_fee_is_not_added_to_room_rate_total() -> None:
    room, rate = _catalog(), _rate()
    rate["value"]["child_charge_amount"] = 50
    rate["value"]["child_charge_currency"] = "USD"
    rate["value"]["child_charge_status"] = "confirmed"
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": [{"member_id": "child-1", "age": 7}],
                       "guardians": {"child-1": "adult-1"}}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-1", "room_index": 0, "bed_index": 1, "bed_type": "twin"},
        ),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    cost = result.options[0]["cost"]
    assert cost["currency"] == "VND"
    assert cost["nightly_subtotal"] == 100
    assert cost["total"] is None
    assert cost["status"] == "incomplete"


def test_hard_budget_conflict_keeps_source_refs_for_rejected_candidate() -> None:
    room, rate = _catalog(), _rate(amount=1_800_000)
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 1, "children": []},
             "room_requirements": {"budget_amount": 100, "budget_currency": "VND",
                                   "budget_basis": "stay_total", "budget_strength": "hard"}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "conflict"
    assert result.options == ()
    assert {ref["fact_id"] for ref in result.source_refs} == {"F-ROOM", "F-RATE"}


def test_whole_party_rationale_requires_every_room_sharing_and_guardian_check() -> None:
    room, rate = _catalog(), _rate()
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 3, "children": []}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},
                               {"room_index": 1, "room_type_id": "FAM"}),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "adult-2", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "adult-3", "room_index": 1, "bed_index": 0, "bed_type": "queen"},
        ), rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"]},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    checks = result.options[0]["checks"]
    assert sum(item["code"] == "bed_sharing_consent" and item["status"] == "unknown" for item in checks) == 1
    assert not any(item["claim_code"] == "party_fit" for item in result.options[0]["rationale"])

    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 2, "children": [
                 {"member_id": "child-1", "age": 8}, {"member_id": "child-2", "age": 8}],
                 "guardians": {"child-2": "adult-2"}}}
    candidate = RoomAdviceCandidate(
        option_id="B", rooms=({"room_index": 0, "room_type_id": "FAM"},
                               {"room_index": 1, "room_type_id": "FAM"}),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-1", "room_index": 0, "bed_index": 1, "bed_type": "twin"},
            {"member_id": "adult-2", "room_index": 1, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-2", "room_index": 1, "bed_index": 1, "bed_type": "twin"},
        ), rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"]},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert [item["status"] for item in result.options[0]["checks"]
            if item["code"] == "guardian_relationship"] == ["unknown", "pass"]
    assert not any(item["claim_code"] == "party_fit" for item in result.options[0]["rationale"])


def test_bunk_position_has_one_guest_capacity_even_with_sharing_consent() -> None:
    room = _catalog(room_id="PINE-CABIN", beds=[
        {"type": "queen", "count": 1, "occupant_capacity": 2},
        {"type": "bunk", "count": 1, "occupant_capacity": 2},
    ])
    rate = _rate()
    rate["value"]["room_type_id"] = "PINE-CABIN"
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 1, "children": [
                 {"member_id": "child-1", "age": 8}, {"member_id": "child-2", "age": 9}],
                 "guardians": {"child-1": "adult-1", "child-2": "adult-1"},
                 "bed_sharing": [{"member_ids": ["child-1", "child-2"], "allow_share": True}]}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "PINE-CABIN"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-1", "room_index": 0, "bed_index": 1, "bed_type": "bunk", "bed_position": "upper"},
            {"member_id": "child-2", "room_index": 0, "bed_index": 1, "bed_type": "bunk", "bed_position": "upper"},
        ),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "conflict"
    assert result.options == ()


def test_unsupported_rate_basis_never_emits_a_calculated_room_subtotal() -> None:
    room, rate = _catalog(), _rate(amount=1_800_000)
    rate["value"]["price_basis"]["unit"] = "person_night"
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-04"},
             "party": {"adults": 2, "children": [], "bed_sharing": [
                 {"member_ids": ["adult-1", "adult-2"], "allow_share": True}]}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=tuple({"member_id": f"adult-{index}", "room_index": 0,
                           "bed_index": 0, "bed_type": "queen"} for index in (1, 2)),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    cost = result.options[0]["cost"]
    assert cost["nightly_subtotal"] is None
    assert cost["total"] is None
    assert all(item["amount"] is None for item in cost["breakdown"] if item["label"] == "reference room rate")
    assert any(item["code"] == "rate_basis" and item["status"] == "unknown"
               for item in result.options[0]["checks"])
    assert any(item["field"] == "room_advice" and item["locale"] == "zh"
               and "每间客房每晚" in item["reason"] for item in result.questions)


def test_confirmed_mandatory_fee_is_included_in_hard_per_night_budget_check() -> None:
    room, rate = _catalog(), _rate(amount=2_600_000, child_amount=2_000_000)
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 1, "children": [{"member_id": "child-1", "age": 7}],
                       "guardians": {"child-1": "adult-1"}},
             "room_requirements": {"budget_amount": 3_000_000, "budget_currency": "VND",
                                   "budget_basis": "per_night", "budget_strength": "hard"}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-1", "room_index": 0, "bed_index": 1, "bed_type": "twin"},
        ),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "conflict"
    assert result.options == ()
    assert "hard_budget_exceeded" in result.explanation_inputs["conflicts"]


def test_known_base_cost_lower_bound_rejects_hard_budget_despite_unknown_child_fee() -> None:
    room, rate = _catalog(), _rate(amount=2_600_000)
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 1, "children": [{"member_id": "child-1", "age": 7}],
                       "guardians": {"child-1": "adult-1"}}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "child-1", "room_index": 0, "bed_index": 1, "bed_type": "twin"},
        ),
    )
    for basis, over_budget, under_budget in (
        ("stay_total", 1_000_000, 6_000_000),
        ("per_night", 1_000_000, 3_000_000),
    ):
        brief["room_requirements"] = {
            "budget_amount": over_budget, "budget_currency": "VND",
            "budget_basis": basis, "budget_strength": "hard",
        }
        rejected = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
            context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
        ))
        assert rejected.status == "conflict"
        assert rejected.options == ()
        assert "hard_budget_exceeded" in rejected.explanation_inputs["conflicts"]

        brief["room_requirements"]["budget_amount"] = under_budget
        uncertain = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
            context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
        ))
        assert uncertain.status == "partial"
        assert uncertain.options[0]["cost"]["total"] is None
        assert any(item["code"] == "budget" and item["status"] == "unknown"
                   for item in uncertain.options[0]["checks"])


def test_rate_validity_covers_charged_nights_not_checkout_day() -> None:
    room, rate = _catalog(), _rate(amount=100)
    rate["valid_from"] = "2026-10-01"
    rate["valid_to"] = "2026-11-01"
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
    )
    one_night = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
                 "party": {"adults": 1, "children": []}}
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(one_night, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.options[0]["cost"]["total"] == 100

    two_nights = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
                  "party": {"adults": 1, "children": []}}
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(two_nights, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.options[0]["cost"]["total"] is None
    assert result.options[0]["cost"]["status"] == "incomplete"
    assert any(item["code"] == "rate_validity_window" and item["status"] == "unknown"
               for item in result.options[0]["checks"])


def test_relocalization_changes_only_presentation_and_never_calls_provider() -> None:
    room, rate = _catalog(), _rate()
    rate["value"]["price_basis"]["unit"] = "person_night"
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 2, "children": [], "bed_sharing": [
                 {"member_ids": ["adult-1", "adult-2"], "allow_share": True}]}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=tuple({"member_id": f"adult-{index}", "room_index": 0,
                           "bed_index": 0, "bed_type": "queen"} for index in (1, 2)),
        rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"]},),
    )
    advice = HospitalityRoomAdvice()
    original = __import__("asyncio").run(advice.recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    original_snapshot = deepcopy(original)

    class NoCallProvider:
        calls = 0

        async def generate(self, _request):
            self.calls += 1
            raise AssertionError("relocalization must not call an AI provider")

    provider = NoCallProvider()
    orchestrator = GroundedQAOrchestrator(
        provider=provider, retriever=object(), instructions="", committed_instructions="",
        response_schema=RoomAdvicePreparation, selection_instructions="",
        committed_selection_instructions="", selection_schema=RoomAdvicePreparation,
        room_advice=advice,
    )
    english = orchestrator.relocalize_room_advice(original, "en")
    fallback = orchestrator.relocalize_room_advice(english, "ko-KR")

    assert original.options[0]["rationale"][0]["text"] == "此安排符合已确认的入住人数和房间规则。"
    assert english.options[0]["rationale"][0]["text"] == (
        "This arrangement fits the confirmed party and verified room rules."
    )
    assert english.questions[0]["locale"] == "en"
    assert "per room per night" in english.questions[0]["reason"]
    assert fallback.options[0]["rationale"][0]["locale"] == "en"
    assert fallback.options[0]["rationale"][0]["locale_fallback"] is True
    assert fallback.questions[0]["locale_fallback"] is True

    def non_presentation(result):
        data = asdict(result)
        for option in data["options"]:
            for item in option["rationale"]:
                for key in ("text", "locale", "locale_fallback"):
                    item.pop(key, None)
        for question in data["questions"]:
            for key in ("reason", "locale", "locale_fallback"):
                question.pop(key, None)
        return data

    assert non_presentation(original) == non_presentation(english) == non_presentation(fallback)
    assert asdict(original) == asdict(original_snapshot)
    fallback.options[0]["checks"][0]["status"] = "mutated-copy"
    assert original.options[0]["checks"][0]["status"] == "pass"
    assert provider.calls == 0


def test_conflicting_room_catalogue_source_has_conflict_status_and_both_refs() -> None:
    room, rate = _catalog(), _rate()
    second = _catalog()
    second["fact_id"] = "F-ROOM-2"
    second["value"]["max_occupancy"] = 3
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": []}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, second, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "conflict"
    assert {ref["fact_id"] for ref in result.source_refs} == {"F-ROOM", "F-ROOM-2"}


def test_party_above_checked_assignment_limit_returns_processing_limit() -> None:
    room, rate = _catalog(), _rate()
    brief = {"party": {"adults": 1, "children": [
        {"member_id": f"child-{index}", "age": 8} for index in range(40)
    ]}}
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", ()),
    ))
    assert result.status == "processing_limit"
    assert result.options == ()


def test_mixed_room_advice_carries_checked_hotel_answer_in_the_same_provider_call() -> None:
    import asyncio
    import json

    import pytest

    from staylead_platform.domains.hospitality.schemas.guest_brief import (
        validate_committed_turn_channels,
    )
    from staylead_platform.platform.contracts.ai_provider import GenerationResult, Usage
    from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
        ConversationFailure,
    )

    class Provider:
        def __init__(self):
            self.calls = []
            self.faq_fact_id = "F-FAQ"
            self.include_options = True

        async def generate(self, request):
            self.calls.append(request)
            return GenerationResult(
                text=json.dumps({
                    "options": ([{
                        "option_id": "A",
                        "rooms": [{"room_index": 0, "room_type_id": "FAM"}],
                        "assignments": [{"member_id": "adult-1", "room_index": 0,
                                         "bed_index": 0, "bed_type": "queen"}],
                        "rationale": [{"claim_code": "party_fit", "fact_ids": ["F-ROOM"]}],
                    }] if self.include_options else []),
                    "questions": [],
                    "hotel_answer": {
                        "supported_claims": [{
                            "text": "Breakfast is served from 06:00 to 10:00.",
                            "fact_ids": [self.faq_fact_id],
                        }],
                        "unknowns": [], "conflicts": [],
                    },
                }),
                provider="fake", deployment="test", model="fake", request_id="mixed-1",
                usage=Usage(input_tokens=30, output_tokens=20, total_tokens=50),
            )

    faq = _fact("F-FAQ", "breakfast_hours", {"hours": "06:00-10:00"})
    facts = (_catalog(), _rate(), faq)
    provider = Provider()
    advice = HospitalityRoomAdvice()
    orchestrator = GroundedQAOrchestrator(
        provider=provider, retriever=_CurrentFactRetriever(facts), instructions="", committed_instructions="",
        response_schema=RoomAdvicePreparation, selection_instructions="",
        committed_selection_instructions="", selection_schema=RoomAdvicePreparation,
        committed_answer_validator=validate_committed_turn_channels,
        room_advice=advice,
    )
    context = replace(
        _context({
            "dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
            "party": {"adults": 1, "children": []},
        }, facts),
        turn_intents=("hotel_information", "room_advice"),
        hotel_information_fact_ids=("F-FAQ",),
    )

    result, _generation = asyncio.run(orchestrator.recommend_committed_room_advice(context=context))

    assert len(provider.calls) == 1
    request = provider.calls[0]
    request_payload = json.loads(request.input_text)
    assert request.max_output_tokens == 700
    assert request.response_schema == advice.preparation_output_schema(include_hotel_answer=True)
    assert [item["fact_id"] for item in request_payload["hotel_information_facts"]] == ["F-FAQ"]
    assert result.status == "ready"
    assert result.hotel_answer is not None
    claim = result.hotel_answer.supported_claims[0]
    assert claim.text == "Breakfast is served from 06:00 to 10:00."
    assert claim.fact_ids == ("F-FAQ",)
    assert {ref["fact_id"] for ref in result.source_refs} >= {"F-FAQ", "F-ROOM"}
    assert "hotel_answer" not in advice.preparation_output_schema()
    assert "hotel_answer" in advice.preparation_output_schema(include_hotel_answer=True)["properties"]["response"]["properties"]

    provider.faq_fact_id = "F-NOT-SELECTED"
    with pytest.raises(ConversationFailure, match="outside M1 selection"):
        asyncio.run(orchestrator.recommend_committed_room_advice(context=context))
    assert len(provider.calls) == 2

    provider.faq_fact_id = "F-FAQ"
    provider.include_options = False
    needs_clarification, _ = asyncio.run(
        orchestrator.recommend_committed_room_advice(context=context),
    )
    assert len(provider.calls) == 3
    assert needs_clarification.status == "needs_clarification"
    assert needs_clarification.hotel_answer is not None
    assert needs_clarification.hotel_answer.supported_claims[0].fact_ids == ("F-FAQ",)


def test_mixed_faq_rejects_expired_revoked_and_stale_generation_before_provider_call() -> None:
    import asyncio
    import json

    import pytest

    from staylead_platform.platform.contracts.ai_provider import GenerationResult, Usage
    from staylead_platform.platform.conversation.orchestrator.grounded_qa import ConversationFailure

    class Provider:
        def __init__(self):
            self.calls = []

        async def generate(self, request):
            self.calls.append(request)
            return GenerationResult(
                text=json.dumps({"options": [], "questions": [], "hotel_answer": {
                    "supported_claims": [{"text": "退房时间是11:00。", "fact_ids": ["F-FAQ"]}],
                    "unknowns": [], "conflicts": [],
                }}),
                provider="fake", deployment="test", model="fake", request_id="eligibility",
                usage=Usage(input_tokens=10, output_tokens=10, total_tokens=20),
            )

    for mutation in (
        lambda fact: fact.update(valid_to="2020-01-01"),
        lambda fact: fact.update(status="revoked"),
        lambda fact: fact["provenance"].update(source_generation=6),
    ):
        fact = _fact("F-FAQ", "checkout_time", {"time": "11:00"})
        mutation(fact)
        provider = Provider()
        orchestrator = GroundedQAOrchestrator(
            provider=provider, retriever=_CurrentFactRetriever((fact,)), instructions="", committed_instructions="",
            response_schema=RoomAdvicePreparation, selection_instructions="",
            committed_selection_instructions="", selection_schema=RoomAdvicePreparation,
            room_advice=HospitalityRoomAdvice(),
        )
        context = replace(
            _context({"party": {"adults": 1, "children": []}}, (fact,)),
            turn_intents=("hotel_information", "room_advice"),
            hotel_information_fact_ids=("F-FAQ",),
        )
        with pytest.raises(ConversationFailure, match="no longer current and eligible"):
            asyncio.run(orchestrator.recommend_committed_room_advice(context=context))
        assert provider.calls == []


def test_mixed_faq_revalidates_selected_fact_after_generation() -> None:
    import asyncio
    import json

    import pytest

    from staylead_platform.platform.contracts.ai_provider import GenerationResult, Usage
    from staylead_platform.platform.conversation.orchestrator.grounded_qa import ConversationFailure

    fact = _fact("F-FAQ", "checkout_time", {"time": "11:00"})

    class Provider:
        def __init__(self):
            self.calls = []

        async def generate(self, request):
            self.calls.append(request)
            fact["status"] = "revoked"
            return GenerationResult(
                text=json.dumps({"options": [], "questions": [], "hotel_answer": {
                    "supported_claims": [{"text": "退房时间是11:00。", "fact_ids": ["F-FAQ"]}],
                    "unknowns": [], "conflicts": [],
                }}),
                provider="fake", deployment="test", model="fake", request_id="changed-during-call",
                usage=Usage(input_tokens=10, output_tokens=10, total_tokens=20),
            )

    provider = Provider()
    orchestrator = GroundedQAOrchestrator(
        provider=provider, retriever=_CurrentFactRetriever((fact,)), instructions="", committed_instructions="",
        response_schema=RoomAdvicePreparation, selection_instructions="",
        committed_selection_instructions="", selection_schema=RoomAdvicePreparation,
        room_advice=HospitalityRoomAdvice(),
    )
    context = replace(
        _context({"party": {"adults": 1, "children": []}}, (fact,)),
        turn_intents=("hotel_information", "room_advice"),
        hotel_information_fact_ids=("F-FAQ",),
    )
    with pytest.raises(ConversationFailure, match="changed during generation"):
        asyncio.run(orchestrator.recommend_committed_room_advice(context=context))
    assert len(provider.calls) == 1
