from __future__ import annotations

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
    CANONICAL_BED_TYPES,
    HARD_BED_TYPES_DESCRIPTION,
    GuestTurnIntent,
    SetRoomRequirements,
    validate_guest_brief_proposal,
    validate_guest_patch_authorization,
    validate_preparation_metadata,
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
    RoomAdviceResult,
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


def _without_inline_quotes(operations: tuple[dict, ...]) -> tuple[dict, ...]:
    return tuple({key: value for key, value in operation.items() if key != "current_turn_quote"}
                 for operation in operations)


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


def test_rejected_over_budget_alternative_does_not_poison_valid_option() -> None:
    standard_room = _catalog(room_id="CITY-STD", max_occupancy=2)
    standard_room["fact_id"] = "F-STD"
    standard_room["value"]["beds"] = [{"type": "queen", "count": 1, "occupant_capacity": 2}]
    family_room = deepcopy(standard_room)
    family_room["fact_id"] = "F-FAMILY"
    family_room["value"]["room_type_id"] = "CITY-FAM"

    standard_rate = _rate(amount=1_800_000)
    standard_rate["fact_id"] = "F-RATE-STD"
    standard_rate["value"].update(room_type_id="CITY-STD", rate_id="RATE-STD")
    family_rate = deepcopy(standard_rate)
    family_rate["fact_id"] = "F-RATE-FAMILY"
    family_rate["value"].update(room_type_id="CITY-FAM", rate_id="RATE-FAMILY", amount=2_900_000)

    brief = {
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-04"},
        "party": {"adults": 2, "children": [], "bed_sharing": [
            {"member_ids": ["adult-1", "adult-2"], "allow_share": True}],
        },
        "room_requirements": {
            "budget_amount": 6_000_000, "budget_currency": "VND",
            "budget_basis": "stay_total", "budget_strength": "hard",
        },
    }
    def candidate(option_id: str, room_id: str) -> RoomAdviceCandidate:
        return RoomAdviceCandidate(
            option_id=option_id, rooms=({"room_index": 0, "room_type_id": room_id},),
            assignments=tuple({"member_id": f"adult-{number}", "room_index": 0,
                               "bed_index": 0, "bed_type": "queen"} for number in (1, 2)),
        )

    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (standard_room, standard_rate, family_room, family_rate)),
        draft=RoomAdviceDraft("ready", (
            candidate("standard-queen", "CITY-STD"), candidate("family-queen", "CITY-FAM"),
        )),
    ))
    assert result.status == "ready"
    assert [option["option_id"] for option in result.options] == ["standard-queen"]
    assert result.options[0]["cost"]["total"] == 5_400_000
    assert result.questions == ()
    assert result.explanation_inputs["conflicts"] == []
    rejected = result.explanation_inputs["rejected_alternatives"]
    assert rejected[0]["option_id"] == "family-queen"
    assert rejected[0]["reason"] == "hard_budget_exceeded"
    assert set(rejected[0]["fact_ids"]) == {"F-FAMILY", "F-RATE-FAMILY"}


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


def test_room_advice_question_fields_are_canonical_and_reject_presentation_aliases() -> None:
    schema = room_advice_output_schema()
    field_schema = schema["properties"]["response"]["properties"]["questions"]["items"]["properties"]["field"]
    allowed = field_schema["anyOf"][0]["enum"]
    assert "room_requirements.hard_accessibility_needs" in allowed
    assert "room_requirements.budget_strength" in allowed
    assert "accessibility_confirmation" not in allowed
    assert RoomAdviceQuestion(field="room_requirements.hard_accessibility_needs")
    assert RoomAdviceQuestion(field="party.children.6adf87cf-4a99-4437-b293-d1e417e31c81.age")
    with pytest.raises(ValidationError):
        RoomAdviceQuestion(field="accessibility_confirmation")
    with pytest.raises(ValidationError):
        RoomAdviceQuestion(field="room_requirements.not_a_requirement")
    with pytest.raises(ValidationError):
        RoomAdviceQuestion(field="party.children.not-a-uuid.age")


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


def test_budget_amount_without_strength_remains_pending_and_requires_explicit_classification() -> None:
    question = "Set a 6000000 VND budget for the whole stay."
    operation = {
        "op": "set_room_requirements", "budget_amount": 6_000_000,
        "budget_currency": "VND", "budget_basis": "stay_total",
        "current_turn_quote": question,
    }
    payload = {"turn_intents": ["guest_edit", "room_advice"], "guest_patch": {"ops": [operation]}}
    parsed = FactSelection.model_validate(payload)
    _, authorizations = validate_preparation_metadata(
        parsed, GuestBriefProposal((_without_inline_quotes((operation,))[0],)), question,
    )
    assert authorizations[0]["target_fields"] == [
        "room_requirements.budget_amount", "room_requirements.budget_currency",
        "room_requirements.budget_basis",
    ]
    current = GuestBriefSnapshot(0, {"dates": {}, "party": {"adults": 2, "children": []}})
    updated = validate_guest_brief_proposal(
        current, GuestBriefProposal((_without_inline_quotes((operation,))[0],)),
    )
    assert updated.data["room_requirements"]["budget_amount"] == 6_000_000
    assert "budget_strength" not in updated.data["room_requirements"]
    assert "room_requirements.budget_strength" in updated.pending_fields
    assert updated.status == "partial_success"


def test_budget_without_strength_keeps_known_cost_and_cannot_claim_fit_to_budget() -> None:
    brief = {
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
        "party": {"adults": 2, "children": []},
        "room_requirements": {"budget_amount": 1_000, "budget_currency": "VND",
                              "budget_basis": "stay_total"},
    }
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
                     {"member_id": "adult-2", "room_index": 0, "bed_index": 0, "bed_type": "queen"}),
        rationale=(RoomRationale(claim_code="party_fit", fact_ids=["F-ROOM"]),),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (_catalog(), _rate(amount=100))),
        draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "partial"
    assert result.questions[0]["field"] == "room_requirements.budget_strength"
    option = result.options[0]
    assert option["cost"]["total"] == 200
    checks = {check["code"]: check["status"] for check in option["checks"]}
    assert checks["budget_strength"] == "unknown"
    assert not any("budget" in item["text"].casefold() or "stated requirements" in item["text"].casefold()
                   for item in option["rationale"])


def test_budget_strength_question_keeps_priority_when_rate_basis_is_also_unknown() -> None:
    result = RoomAdviceResult(
        status="partial", brief_version=4, source_generation=7,
        questions=({"field": "room_requirements.budget_strength"}, {"field": "room_advice"}),
        explanation_inputs={"unknowns": ["rate_basis", "rate_validity_window"]},
    )
    labels = {
        "question.budget_strength": "Ce budget est-il une limite absolue ou un objectif ?",
        "question.rate_basis": "Confirmez le tarif par chambre et par nuit.",
    }
    localized = HospitalityRoomAdvice.relocalize(result, "fr-FR", labels)
    assert [item["presentation_key"] for item in localized.questions] == [
        "question.budget_strength", "question.rate_basis",
    ]
    assert localized.questions[0]["reason"] == labels["question.budget_strength"]
    assert localized.questions[1]["reason"] == labels["question.rate_basis"]


@pytest.mark.parametrize(("locale", "expected_text", "hotel_step"), [
    ("en", "Your access needs are recorded", "ask the hotel to confirm"),
    ("vi", "Tôi đã ghi nhận yêu cầu tiếp cận", "nhờ khách sạn xác nhận"),
    ("zh", "我已记录您的无障碍需求", "向酒店确认"),
    ("ja", "アクセシビリティのご要望を記録しました", "ホテルにご確認"),
])
def test_unverified_hard_accessibility_need_gives_hotel_confirmation_step(locale, expected_text, hotel_step) -> None:
    room, rate = _catalog(), _rate()
    context = replace(_context({
        "dates": {"check_in": "2026-11-10", "check_out": "2026-11-12"},
        "party": {"adults": 1, "children": []},
        "room_requirements": {"hard_accessibility_needs": ["step-free entry", "wheelchair bathroom"]},
    }, (room, rate)), locale=locale)
    draft = RoomAdviceDraft(
        "needs_clarification", questions=({"field": "room_requirements.hard_accessibility_needs"},),
    )

    result = __import__("asyncio").run(
        HospitalityRoomAdvice().recommend(context=context, draft=draft),
    )

    assert result.status == "needs_clarification"
    assert result.options == ()
    question = result.questions[0]
    assert question["field"] == "room_requirements.hard_accessibility_needs"
    assert question["presentation_key"] == "question.accessibility_confirmation"
    assert expected_text in question["reason"]
    assert hotel_step in question["reason"]
    assert "question.room" not in question["presentation_key"]


@pytest.mark.parametrize("saved_needs,pending_fields", [
    (None, ()),
    (["step-free entry"], ("room_requirements.hard_accessibility_needs",)),
])
def test_accessibility_confirmation_message_requires_saved_nonpending_needs(saved_needs, pending_fields) -> None:
    room, rate = _catalog(), _rate()
    requirements = {"hard_accessibility_needs": saved_needs} if saved_needs else {}
    context = replace(_context({
        "party": {"adults": 1, "children": []},
        "room_requirements": requirements,
    }, (room, rate)), locale="en", pending_fields=pending_fields)
    draft = RoomAdviceDraft(
        "needs_clarification", questions=({"field": "room_requirements.hard_accessibility_needs"},),
    )

    result = __import__("asyncio").run(
        HospitalityRoomAdvice().recommend(context=context, draft=draft),
    )

    question = result.questions[0]
    assert question["presentation_key"] == "question.room"
    assert question["reason"] == "Which room requirement should I use?"
    assert "known_hard_accessibility_needs" not in result.explanation_inputs


def test_preparation_native_and_pydantic_intents_are_in_parity_and_support_booking() -> None:
    assert set(get_args(GuestTurnIntent)) == set(TURN_INTENTS)
    assert FactSelection.model_validate({"turn_intents": ["booking_request"]}).turn_intents == ["booking_request"]
    assert HospitalityGroundedAnswer.model_validate({"turn_intents": ["booking_request"]}).turn_intents == ["booking_request"]
    add_child = {"op": "add_child", "age": 5, "guardian_adult_index": 1,
                 "share_bed_with_guardian": True,
                 "current_turn_quote": "My child will share with me."}
    payload = {"turn_intents": ["guest_edit", "booking_request"],
               "guest_patch": {"ops": [add_child]}}
    fact_selection = FactSelection.model_validate(payload)
    answer = HospitalityGroundedAnswer.model_validate(payload)
    for parsed in (fact_selection, answer):
        _, authorizations = validate_preparation_metadata(
            parsed, GuestBriefProposal((add_child,)), "My child will share with me."
        )
        assert len(authorizations[0]["target_fields"]) == 3
    fact_response = fact_selection_output_schema()["properties"]["response"]["properties"]
    answer_response = preparation_answer_output_schema((), ())["properties"]["response"]["anyOf"][0]["properties"]
    answer_schema = answer_response["turn_intents"]
    assert fact_response["turn_intents"]["items"]["enum"] == list(TURN_INTENTS)
    assert answer_schema["items"]["enum"] == list(TURN_INTENTS)
    for response in (fact_response, answer_response):
        assert "guest_patch_authorizations" not in response
        op_schemas = response["guest_patch"]["anyOf"][0]["properties"]["ops"]["items"]["anyOf"]
        flattened = [variant for item in op_schemas for variant in item.get("anyOf", (item,))]
        assert all("current_turn_quote" in item["required"] for item in flattened)
        add_child_variants = response["guest_patch"]["anyOf"][0]["properties"]["ops"]["items"]["anyOf"][2]["anyOf"]
        assert len(add_child_variants) == 2
        assert all({"guardian_adult_index", "share_bed_with_guardian", "requires_separate_bed"}
                   <= set(add_child["properties"]) for add_child in add_child_variants)
    assert "Whenever `guest_patch.ops` contains an edit, include `guest_edit`" in GUEST_BRIEF_PATCH_RULES
    assert "Do not infer a room" in GUEST_BRIEF_PATCH_RULES
    assert "set `max_rooms` only when the guest explicitly states a" in GUEST_BRIEF_PATCH_RULES
    assert "maximum number of rooms" in GUEST_BRIEF_PATCH_RULES
    assert "canonical `adult-1` through `adult-N` IDs are valid member IDs for a" in GUEST_BRIEF_PATCH_RULES
    assert "place that consent operation after `set_adults`" in GUEST_BRIEF_PATCH_RULES
    assert "targets are exactly" not in GUEST_BRIEF_PATCH_RULES


def test_mixed_room_advice_prompt_preserves_source_numeric_literals() -> None:
    from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
        ConversationFailure,
        _validate_supported_literals,
    )

    instructions = HospitalityRoomAdvice.preparation_instructions(
        "en", include_hotel_answer=True,
    )
    assert "preserve every number exactly as it is" in instructions
    assert "`3800000`, not" in instructions
    assert "Do not reformat, round, convert, or calculate numbers in `hotel_answer`" in instructions

    source = [{"value": {"amount": 3800000, "currency": "VND"}, "conditions": {}}]
    _validate_supported_literals("Reference rate is 3800000 VND per room night.", source)
    with pytest.raises(ConversationFailure, match="unsupported number"):
        _validate_supported_literals("Reference rate is 3,800,000 VND per room night.", source)


def test_new_child_keeps_guardian_separation_and_adult_sharing_as_separate_facts() -> None:
    question = (
        "Stay 2026-11-10 to 2026-11-12. We are two adults and one child. "
        "I am the child’s parent and guardian; the adults may share a queen bed, "
        "and the child needs a separate sleeping place."
    )
    operations = (
        {"op": "set_dates", "check_in": "2026-11-10", "check_out": "2026-11-12",
         "current_turn_quote": "Stay 2026-11-10 to 2026-11-12."},
        {"op": "set_adults", "count": 2, "current_turn_quote": "We are two adults and one child."},
        {"op": "add_child", "age": None, "guardian_adult_index": 1,
         "requires_separate_bed": True,
         "current_turn_quote": "I am the child’s parent and guardian; the adults may share a queen bed, and the child needs a separate sleeping place."},
        {"op": "set_bed_sharing", "member_ids": ["adult-1", "adult-2"], "allow_share": True,
         "current_turn_quote": "the adults may share a queen bed"},
    )
    assert operations.index(next(op for op in operations if op["op"] == "set_adults")) < operations.index(
        next(op for op in operations if op["op"] == "set_bed_sharing")
    )
    payload = {"turn_intents": ["guest_edit", "room_advice"],
               "guest_patch": {"ops": list(operations)}}
    fact_selection = FactSelection.model_validate(payload)
    answer = HospitalityGroundedAnswer.model_validate(payload)
    canonical_operations = _without_inline_quotes(operations)
    _, authorizations = validate_preparation_metadata(
        fact_selection, GuestBriefProposal(canonical_operations), question
    )
    validate_preparation_metadata(answer, GuestBriefProposal(canonical_operations), question)
    target_fields = {
        "party.children", "party.guardians",
    }
    assert set(authorizations[2]["target_fields"]) == target_fields

    native_patch_ops = fact_selection_output_schema()["properties"]["response"]["properties"][
        "guest_patch"
    ]["anyOf"][0]["properties"]["ops"]["items"]["anyOf"]
    native_operations = [variant for item in native_patch_ops for variant in item.get("anyOf", (item,))]
    native_add_child_variants = [
        item for item in native_operations
        if item.get("properties", {}).get("op", {}).get("enum") == ["add_child"]
    ]
    assert len(native_add_child_variants) == 2
    separations = [
        (set(item["properties"]["requires_separate_bed"]["enum"]),
         set(item["properties"]["share_bed_with_guardian"]["enum"]))
        for item in native_add_child_variants
    ]
    assert not any(True in separate and True in share for separate, share in separations)
    assert any(True in separate and False in share for separate, share in separations)
    assert any(None in separate and True in share for separate, share in separations)
    assert "requires_separate_bed: true" in GUEST_BRIEF_PATCH_RULES
    assert "all current party members" in GUEST_BRIEF_PATCH_RULES
    assert "speaking guest is `adult-1`" in GUEST_BRIEF_PATCH_RULES
    with pytest.raises(ValidationError):
        FactSelection.model_validate({
            **payload,
            "guest_patch": {"ops": [{**operations[2], "share_bed_with_guardian": True}]},
        })

    current = GuestBriefSnapshot(0, {"dates": {}, "party": {"adults": None, "children": []}})
    updated = validate_guest_brief_proposal(current, GuestBriefProposal(operations))
    child = updated.data["party"]["children"][0]
    child_id = child["member_id"]
    assert child["age"] is None
    assert child["requires_separate_bed"] is True
    assert updated.data["party"]["guardians"][child_id] == "adult-1"
    rules = {frozenset(rule["member_ids"]): rule["allow_share"]
             for rule in updated.data["party"]["bed_sharing"]}
    assert rules[frozenset(("adult-1", "adult-2"))] is True
    assert len(rules) == 1  # The hard separation rule is stored on the child, not duplicated as pair rules.
    assert f"party.children.{child_id}.age" in updated.pending_fields

    relax = {"op": "set_child_separate_bed", "child_id": child_id, "requires_separate_bed": False}
    relax_auth = {"operation_index": 0, "op": "set_child_separate_bed",
                  "target_fields": [f"party.children.{child_id}.requires_separate_bed"],
                  "intent": "explicit_request", "current_turn_quote": "The child may share a sleeping surface now."}
    validate_guest_patch_authorization((relax,), (relax_auth,), question + " The child may share a sleeping surface now.")
    relaxed = validate_guest_brief_proposal(
        GuestBriefSnapshot(1, updated.data, updated.pending_fields), GuestBriefProposal((relax,)),
    )
    assert "requires_separate_bed" not in relaxed.data["party"]["children"][0]
    assert relaxed.data["party"]["bed_sharing"] == updated.data["party"]["bed_sharing"]
    reaffirmed = validate_guest_brief_proposal(
        GuestBriefSnapshot(2, updated.data, updated.pending_fields),
        GuestBriefProposal(({"op": "set_child_separate_bed", "child_id": child_id,
                            "requires_separate_bed": True},)),
    )
    still_relaxed = validate_guest_brief_proposal(
        GuestBriefSnapshot(2, relaxed.data, relaxed.pending_fields),
        GuestBriefProposal(({"op": "set_child_separate_bed", "child_id": child_id,
                            "requires_separate_bed": False},)),
    )
    assert reaffirmed.status == still_relaxed.status == "no_change"
    assert reaffirmed.applied_delta == still_relaxed.applied_delta == {}

    refusal = {"op": "add_child", "age": None, "guardian_adult_index": 1,
               "share_bed_with_guardian": False}
    refusal_authorization = {"operation_index": 0, "op": "add_child",
                             "target_fields": ["party.children", "party.guardians", "party.bed_sharing"],
                             "intent": "explicit_request", "current_turn_quote": question}
    validate_guest_patch_authorization((refusal,), (refusal_authorization,), question)
    refusal_brief = validate_guest_brief_proposal(
        GuestBriefSnapshot(0, {"dates": {}, "party": {"adults": 2, "children": []}}),
        GuestBriefProposal((refusal,)),
    )
    refusal_child = refusal_brief.data["party"]["children"][0]
    assert refusal_brief.data["party"]["bed_sharing"] == [{
        "member_ids": sorted((refusal_child["member_id"], "adult-1")), "allow_share": False,
    }]

    room, rate = _catalog(), _rate()
    candidate = RoomAdviceCandidate(
        option_id="separate-child-bed", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=(
            {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": "adult-2", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
            {"member_id": child_id, "room_index": 0, "bed_index": 1, "bed_type": "twin"},
        ),
    )
    ready_brief = deepcopy(updated.data)
    ready_brief["party"]["children"][0]["age"] = 7
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(ready_brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.options
    checks = {check["code"]: check["status"] for check in result.options[0]["checks"]}
    assert checks["separate_bed_requirement"] == "pass"

    violating = replace(candidate, option_id="child-shares", assignments=(
        {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
        {"member_id": child_id, "room_index": 0, "bed_index": 0, "bed_type": "queen"},
        {"member_id": "adult-2", "room_index": 0, "bed_index": 1, "bed_type": "twin"},
    ))
    rejected = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(ready_brief, (room, rate)), draft=RoomAdviceDraft("ready", (violating,)),
    ))
    assert rejected.options == ()
    assert rejected.status == "conflict"

    ambiguous = replace(candidate, option_id="unidentified-other-surface", assignments=(
        {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
        {"member_id": "adult-2", "room_index": 0, "bed_index": None, "bed_type": "queen"},
        {"member_id": child_id, "room_index": 0, "bed_index": 1, "bed_type": "twin"},
    ))
    uncertain = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(ready_brief, (room, rate)), draft=RoomAdviceDraft("ready", (ambiguous,)),
    ))
    assert uncertain.options
    ambiguous_checks = {check["code"]: check["status"] for check in uncertain.options[0]["checks"]}
    assert ambiguous_checks["separate_bed_requirement"] == "unknown"


def test_separate_beds_are_a_sharing_constraint_not_an_invented_bed_type() -> None:
    quote = "We now require two separate beds; increase the total room budget to 6500000 VND."
    captured_patch = {
        "ops": [{
            "op": "set_room_requirements", "budget_amount": 6_500_000, "budget_currency": "VND",
            "budget_basis": "stay_total", "budget_strength": "hard", "sharing": None,
            "hard_accessibility_needs": None, "preferred_accessibility_needs": None,
            "hard_bed_types": ["separate beds"], "preferred_bed_types": None,
            "avoided_bed_types": None, "max_rooms": None, "clear_fields": ["preferred_bed_types"],
        }],
    }
    malformed = {"guest_patch": captured_patch, "turn_intents": ["guest_edit", "room_advice"]}
    with pytest.raises(ValidationError):
        FactSelection.model_validate(malformed)
    with pytest.raises(ValidationError):
        HospitalityGroundedAnswer.model_validate(malformed)
    unsupported = deepcopy(malformed)
    unsupported["guest_patch"]["ops"][0]["hard_bed_types"] = ["waterbed"]
    with pytest.raises(ValidationError):
        FactSelection.model_validate(unsupported)

    native_response = fact_selection_output_schema()["properties"]["response"]["properties"]
    native_patch = native_response["guest_patch"]["anyOf"][0]["properties"]["ops"]["items"]["anyOf"]
    native_operations = [variant for item in native_patch for variant in item.get("anyOf", (item,))]
    native_room_requirements = next(
        schema for schema in native_operations
        if schema["properties"]["op"]["enum"] == ["set_room_requirements"]
    )
    native_hard_bed_types = native_room_requirements["properties"]["hard_bed_types"]["anyOf"][0]["items"]["enum"]
    pydantic_hard_bed_types = SetRoomRequirements.model_json_schema()["properties"]["hard_bed_types"]
    assert native_hard_bed_types == list(CANONICAL_BED_TYPES)
    assert pydantic_hard_bed_types["anyOf"][0]["items"]["enum"] == native_hard_bed_types
    assert "separate beds" not in native_hard_bed_types
    assert native_room_requirements["properties"]["hard_bed_types"]["description"] == HARD_BED_TYPES_DESCRIPTION
    assert pydantic_hard_bed_types["description"] == HARD_BED_TYPES_DESCRIPTION
    assert "represented by `set_bed_sharing` with" in GUEST_BRIEF_PATCH_RULES
    assert "A separate-surface arrangement never means `single` or `twin` by itself." in GUEST_BRIEF_PATCH_RULES
    assert "A request for separate sleeping surfaces is not a" in GUEST_BRIEF_PATCH_RULES
    assert "`set_bed_sharing`" in GUEST_BRIEF_PATCH_RULES

    valid_ops = (
        {**captured_patch["ops"][0], "hard_bed_types": None, "current_turn_quote": quote},
        {"op": "set_bed_sharing", "member_ids": ["adult-1", "adult-2"], "allow_share": False,
         "current_turn_quote": quote},
    )
    payload = {"turn_intents": ["guest_edit", "room_advice"], "guest_patch": {"ops": list(valid_ops)}}
    parsed = FactSelection.model_validate(payload)
    canonical_ops = _without_inline_quotes(valid_ops)
    validate_preparation_metadata(parsed, GuestBriefProposal(canonical_ops), quote)
    with pytest.raises(ValueError, match="require the current turn"):
        validate_preparation_metadata(
            FactSelection.model_validate({**payload, "turn_intents": ["room_advice"]}),
            GuestBriefProposal(canonical_ops), quote,
        )

    room, rate = _catalog(
        room_id="CITY-TWN", beds=[{"type": "single", "count": 2, "occupant_capacity": 1}],
        max_occupancy=2,
    ), _rate(amount=1_950_000)
    rate["value"]["room_type_id"] = "CITY-TWN"
    brief = {
        "dates": {"check_in": "2026-11-10", "check_out": "2026-11-13"},
        "party": {"adults": 2, "children": [], "bed_sharing": [
            {"member_ids": ["adult-1", "adult-2"], "allow_share": False}]},
        "room_requirements": {"budget_amount": 6_500_000, "budget_currency": "VND",
                              "budget_basis": "stay_total", "budget_strength": "hard"},
    }
    candidate = RoomAdviceCandidate(
        option_id="two-single-beds", rooms=({"room_index": 0, "room_type_id": "CITY-TWN"},),
        assignments=tuple({"member_id": f"adult-{number}", "room_index": 0,
                           "bed_index": number - 1, "bed_type": "single"} for number in (1, 2)),
    )
    misread_separate_beds = deepcopy(brief)
    misread_separate_beds["room_requirements"] = {
        **misread_separate_beds["room_requirements"], "hard_bed_types": ["twin"],
    }
    rejected = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(misread_separate_beds, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert rejected.status == "conflict"
    assert rejected.options == ()

    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert result.status == "ready"
    assert result.options[0]["cost"]["total"] == 5_850_000
    checks = {check["code"]: check["status"] for check in result.options[0]["checks"]}
    assert checks["bed_configuration"] == "pass"
    assert len({assignment["bed_index"] for assignment in result.options[0]["assignments"]}) == 2
    assert checks.get("bed_sharing_consent") != "conflict"


def test_unsupported_explicit_bed_type_becomes_pending_and_cannot_be_certified() -> None:
    quote = "I require a waterbed."
    operation = {"op": "clarify", "field": "room_requirements.hard_bed_types",
                 "reason": "Please clarify the required bed type.", "current_turn_quote": quote}
    payload = {"turn_intents": ["guest_edit"], "guest_patch": {"ops": [operation]}}
    parsed = FactSelection.model_validate(payload)
    patch = GuestBriefProposal((operation,))
    validate_preparation_metadata(parsed, patch, quote)
    current = GuestBriefSnapshot(3, {
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-02", "nights": 1},
        "party": {"adults": 1, "children": []},
    })
    updated = validate_guest_brief_proposal(current, patch)
    assert "room_requirements.hard_bed_types" in updated.pending_fields
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=replace(_context(updated.data, (_catalog(), _rate())), pending_fields=updated.pending_fields),
        draft=RoomAdviceDraft("ready", (RoomAdviceCandidate(
            option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
            assignments=({"member_id": "adult-1", "room_index": 0,
                          "bed_index": 0, "bed_type": "queen"},),
        ),)),
    ))
    assert result.status == "needs_clarification"
    assert result.options == ()
    resolved = validate_guest_brief_proposal(updated, GuestBriefProposal(({
        "op": "set_room_requirements", "hard_bed_types": ["queen"],
    },)))
    assert "room_requirements.hard_bed_types" not in resolved.pending_fields
    assert resolved.data["room_requirements"]["hard_bed_types"] == ["queen"]


def test_unsupported_soft_bed_preference_remains_a_tradeoff_not_a_hard_clarification() -> None:
    quote = "I would prefer a waterbed, but it is not essential."
    operation = {"op": "set_room_requirements", "preferred_bed_types": ["waterbed"],
                 "current_turn_quote": quote}
    parsed = FactSelection.model_validate({
        "turn_intents": ["guest_edit"], "guest_patch": {"ops": [operation]},
    })
    validate_preparation_metadata(parsed, GuestBriefProposal((operation,)), quote)

    room, rate = _catalog(), _rate()
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-02"},
             "party": {"adults": 1, "children": []},
             "room_requirements": {"preferred_bed_types": ["waterbed"]}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=({"member_id": "adult-1", "room_index": 0,
                      "bed_index": 0, "bed_type": "queen"},),
    )
    result = __import__("asyncio").run(HospitalityRoomAdvice().recommend(
        context=_context(brief, (room, rate)), draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    assert len(result.options) == 1
    assert result.status == "partial"
    assert {check["code"]: check["status"] for check in result.options[0]["checks"]}[
        "preferred_bed_type"
    ] == "not_met"
    assert "Preserve unsupported soft preferred or avoided bed-type wording" in GUEST_BRIEF_PATCH_RULES


def test_room_requirement_clarification_uses_aggregate_target_but_edits_stay_granular() -> None:
    question = "Please clarify my room requirements."
    operation = {"op": "clarify", "field": "room_requirements", "reason": "Confirm the constraints.",
                 "current_turn_quote": "room requirements"}
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
    }
    for model in (FactSelection, HospitalityGroundedAnswer):
        parsed = model.model_validate(payload)
        _, authorizations = validate_preparation_metadata(
            parsed, GuestBriefProposal((_without_inline_quotes((operation,))[0],)), question
        )
        assert authorizations[0]["target_fields"] == ["room_requirements"]

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
        "clear_fields": [], "current_turn_quote": question,
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
    payload = {"turn_intents": ["guest_edit", "room_advice"], "guest_patch": {"ops": [operation]}}
    for model in (FactSelection, HospitalityGroundedAnswer):
        parsed = model.model_validate(payload)
        _, authorizations = validate_preparation_metadata(
            parsed, GuestBriefProposal((_without_inline_quotes((operation,))[0],)), question
        )
        assert len(authorizations[0]["target_fields"]) == 11
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
        "clear_fields": [], "current_turn_quote": question,
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
    payload = {"turn_intents": ["guest_edit", "room_advice"], "guest_patch": {"ops": [operation]}}
    for model in (FactSelection, HospitalityGroundedAnswer):
        parsed = model.model_validate(payload)
        validate_preparation_metadata(parsed, GuestBriefProposal((_without_inline_quotes((operation,))[0],)), question)
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


def test_open_language_bundle_is_bounded_checked_and_preserves_advice() -> None:
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
    checked = __import__("asyncio").run(advice.recommend(
        context=replace(_context(brief, (room, rate)), locale="fr-FR"),
        draft=RoomAdviceDraft("ready", (candidate,)),
    ))
    request = advice.localization_request(checked, "fr-FR")
    assert request is not None
    assert "question.rate_basis" in request["keys"]
    labels = {}
    for key in request["keys"]:
        if key == "claim.party_fit":
            labels[key] = "Cette configuration convient au groupe confirmé et respecte les règles vérifiées."
        elif key == "question.rate_basis":
            labels[key] = "Pouvez-vous confirmer si ce tarif est calculé par chambre et par nuit ?"
        elif key == "claim.reference_price":
            labels[key] = "Estimation indicative du tarif des chambres pour le séjour : {amount} {currency}."
        else:
            labels[key] = "Veuillez confirmer ce détail concernant la chambre."
    payload = {"presentation_labels": [{"key": key, "text": value} for key, value in labels.items()]}
    from staylead_platform.domains.hospitality.schemas.room_advice import (
        RoomAdviceLocalizationPreparation,
    )

    parsed = RoomAdviceLocalizationPreparation.model_validate(payload)
    checked_labels = advice.parse_localization(
        parsed.model_dump_json(), expected_keys=tuple(request["keys"]), locale="fr-FR",
    )
    french = advice.relocalize(checked, "fr-FR", checked_labels)
    assert french.options[0]["rationale"][0]["text"] == labels["claim.party_fit"]
    assert french.options[0]["rationale"][0]["locale"] == "fr"
    assert french.questions[0]["reason"] == labels["question.rate_basis"]
    assert french.questions[0]["locale_fallback"] is False
    assert french.options[0]["cost"] == checked.options[0]["cost"]
    assert french.options[0]["assignments"] == checked.options[0]["assignments"]
    assert french.source_refs == checked.source_refs

    rejected = {}
    for unsafe in (
        "Confirmez le tarif sur https://example.invalid ?",
        "Confirmez le tarif sur ftp://example.invalid ?",
        "Confirmez le tarif par mailto:guest@example.invalid ?",
    ):
        malicious = dict(labels)
        malicious["question.rate_basis"] = unsafe
        malicious_payload = {"presentation_labels": [
            {"key": key, "text": value} for key, value in malicious.items()
        ]}
        rejected = advice.parse_localization(
            RoomAdviceLocalizationPreparation.model_validate(malicious_payload).model_dump_json(),
            expected_keys=tuple(request["keys"]), locale="fr-FR",
        )
        assert rejected == {}
    safe_fallback = advice.relocalize(checked, "fr-FR", rejected)
    assert safe_fallback.options[0]["rationale"][0]["locale"] == "en"
    assert safe_fallback.options[0]["rationale"][0]["locale_fallback"] is True


def test_candidate_translation_labels_project_only_after_checked_rationale_filtering() -> None:
    room, rate = _catalog(), _rate()
    brief = {"dates": {"check_in": "2026-11-01", "check_out": "2026-11-03"},
             "party": {"adults": 2, "children": [], "bed_sharing": [
                 {"member_ids": ["adult-1", "adult-2"], "allow_share": True}]}}
    candidate = RoomAdviceCandidate(
        option_id="A", rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=tuple({"member_id": f"adult-{index}", "room_index": 0,
                           "bed_index": 0, "bed_type": "queen"} for index in (1, 2)),
        rationale=(
            {"claim_code": "party_fit", "fact_ids": ["F-UNSUPPORTED-PARTY-FACT"]},
            {"claim_code": "bed_setup", "fact_ids": ["F-ROOM"]},
            {"claim_code": "reference_price", "fact_ids": ["F-RATE"]},
            {"claim_code": "charges_confirmation", "fact_ids": ["F-UNSUPPORTED-CHARGE-FACT"]},
        ),
    )
    labels = {
        "claim.party_fit": "Cette configuration convient au groupe confirmé et aux règles vérifiées.",
        "claim.bed_setup": "La configuration des lits correspond à la chambre vérifiée.",
        "claim.reference_price": "Tarif indicatif des chambres pour le séjour : {amount} {currency}.",
        "claim.charges_confirmation": "Certains frais d’enfant ou de literie ne sont pas inclus.",
    }

    def run(label_map: dict[str, str]) -> RoomAdviceResult:
        draft = RoomAdviceDraft(
            "ready", (candidate,), presentation_labels=tuple(
                {"key": key, "text": text} for key, text in label_map.items()
            ),
        )
        return __import__("asyncio").run(HospitalityRoomAdvice().recommend(
            context=replace(_context(brief, (room, rate)), locale="fr-FR"), draft=draft,
        ))

    french = run(labels)
    assert [item["claim_code"] for item in french.options[0]["rationale"]] == [
        "bed_setup", "reference_price",
    ]
    assert [item["locale"] for item in french.options[0]["rationale"]] == ["fr", "fr"]
    assert [item["text"] for item in french.options[0]["rationale"]] == [
        labels["claim.bed_setup"],
        labels["claim.reference_price"].format(amount="200", currency="VND"),
    ]
    assert all(item["locale_fallback"] is False for item in french.options[0]["rationale"])

    missing_required = {key: value for key, value in labels.items() if key != "claim.reference_price"}
    forged_superset = {**labels, "question.generic": "Veuillez confirmer cette préférence de chambre."}
    price_mutation = {**labels, "claim.reference_price": "Tarif indicatif : 200 {currency}."}
    for invalid in (missing_required, forged_superset, price_mutation):
        fallback = run(invalid)
        assert all(item["locale"] == "en" and item["locale_fallback"] is True
                   for item in fallback.options[0]["rationale"])


def test_candidate_translation_may_cover_only_m4_derived_checked_questions() -> None:
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
    labels = {
        "claim.party_fit": "Cette configuration convient au groupe confirmé et aux règles vérifiées.",
        "question.rate_basis": "Pouvez-vous confirmer si ce tarif est calculé par chambre et par nuit ?",
    }

    def run(label_map: dict[str, str]) -> RoomAdviceResult:
        draft = RoomAdviceDraft(
            "ready", (candidate,), presentation_labels=tuple(
                {"key": key, "text": text} for key, text in label_map.items()
            ),
        )
        return __import__("asyncio").run(HospitalityRoomAdvice().recommend(
            context=replace(_context(brief, (room, rate)), locale="fr-FR"), draft=draft,
        ))

    checked_question = run(labels)
    assert checked_question.questions[0]["presentation_key"] == "question.rate_basis"
    assert checked_question.questions[0]["reason"] == labels["question.rate_basis"]
    assert checked_question.questions[0]["locale_fallback"] is False
    assert checked_question.options[0]["rationale"][0]["text"] == labels["claim.party_fit"]

    unrelated_superset = run({**labels, "question.dates": "Quelles sont vos dates d'arrivée et de départ ?"})
    assert unrelated_superset.questions[0]["locale"] == "en"
    assert unrelated_superset.questions[0]["locale_fallback"] is True


@pytest.mark.parametrize(("field", "explanation", "expected_key"), [
    ("dates.check_in", {}, "question.dates"),
    ("party.adults", {}, "question.party"),
    ("party.children.age", {}, "question.age"),
    ("room_requirements.max_rooms", {}, "question.room"),
    ("room_requirements.hard_accessibility_needs", {"known_hard_accessibility_needs": True}, "question.accessibility_confirmation"),
    ("room_requirements.hard_accessibility_needs", {}, "question.room"),
    ("room_advice", {"unknowns": ["rate_basis"]}, "question.rate_basis"),
    ("room_advice", {"unknowns": ["rate_validity_window"]}, "question.rate_validity_window"),
    ("room_advice", {"conflicts": ["hard_budget_exceeded"]}, "question.hard_budget_exceeded"),
    ("room_advice", {"conflicts": ["source_fact_conflict"]}, "question.source_fact_conflict"),
    ("room_advice", {"conflicts": ["other_known_rule"]}, "question.room_rule_conflict"),
    ("unrecognized_field", {}, "question.generic"),
])
def test_open_language_questions_cover_each_checked_reason_branch(field, explanation, expected_key) -> None:
    result = RoomAdviceResult(
        status="conflict", brief_version=1, source_generation=1,
        questions=({"field": field},), explanation_inputs=explanation,
    )
    label = "Texte français de confirmation pour la demande concernée."
    localized = HospitalityRoomAdvice.relocalize(result, "fr", {expected_key: label})
    assert localized.questions[0]["reason"] == label
    assert localized.questions[0]["presentation_key"] == expected_key
    assert localized.questions[0]["locale"] == "fr"
    assert localized.questions[0]["locale_fallback"] is False


@pytest.mark.parametrize(("field", "explanation", "expected_key"), [
    ("dates.check_in", {}, "question.dates"),
    ("party.adults", {}, "question.party"),
    ("party.children.age", {}, "question.age"),
    ("room_requirements.max_rooms", {}, "question.room"),
    ("room_requirements.hard_accessibility_needs", {"known_hard_accessibility_needs": True}, "question.accessibility_confirmation"),
    ("room_requirements.hard_accessibility_needs", {}, "question.room"),
    ("room_advice", {"unknowns": ["rate_basis"]}, "question.rate_basis"),
    ("room_advice", {"unknowns": ["rate_validity_window"]}, "question.rate_validity_window"),
    ("room_advice", {"conflicts": ["hard_budget_exceeded"]}, "question.hard_budget_exceeded"),
    ("room_advice", {"conflicts": ["source_fact_conflict"]}, "question.source_fact_conflict"),
    ("room_advice", {"conflicts": ["other_known_rule"]}, "question.room_rule_conflict"),
    ("unrecognized_field", {}, "question.generic"),
])
def test_japanese_questions_cover_each_checked_reason_branch(field, explanation, expected_key) -> None:
    result = RoomAdviceResult(
        status="conflict", brief_version=1, source_generation=1,
        questions=({"field": field},), explanation_inputs=explanation,
    )
    localized = HospitalityRoomAdvice.relocalize(result, "ja-JP")
    assert localized.questions[0]["presentation_key"] == expected_key
    assert localized.questions[0]["locale"] == "ja"
    assert localized.questions[0]["locale_fallback"] is False
    assert any("\u3040" <= char <= "\u30ff" for char in localized.questions[0]["reason"])


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
