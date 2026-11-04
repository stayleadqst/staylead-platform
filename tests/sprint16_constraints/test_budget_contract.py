from __future__ import annotations

import asyncio

import pytest
from staylead_platform.domains.hospitality.recommendations.rooms import HospitalityRoomAdvice
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    HospitalityGuestBriefPatch,
    required_pending_clarification_fields,
    validate_guest_brief_proposal,
    validate_guest_patch_authorization,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    fact_selection_output_schema,
)
from staylead_platform.platform.contracts.guest_brief import GuestBriefProposal, GuestBriefSnapshot
from staylead_platform.platform.contracts.room_advice import (
    RoomAdviceCandidate,
    RoomAdviceContext,
    RoomAdviceDraft,
)


def _fact(fact_id: str, field: str, value: dict) -> dict:
    return {
        "fact_id": fact_id,
        "hotel_id": "HTL-SYNTH",
        "topic": "room_catalog" if field == "room_type" else "room_rates",
        "subject": "room" if field == "room_type" else "rate",
        "field": field,
        "value": value,
        "conditions": {},
        "status": "confirmed",
        "valid_from": "2026-10-01",
        "valid_to": "2027-09-30",
        "provenance": {
            "source_id": "SRC-CATALOG",
            "source_version": "1.0",
            "source_hash": "synthetic-budget-contract",
            "source_generation": 7,
        },
    }


def _catalog() -> dict:
    return _fact("F-ROOM", "room_type", {
        "room_type_id": "FAM",
        "name": "Family room",
        "max_occupancy": 4,
        "max_adults": 4,
        "max_children": 3,
        "beds": [{"type": "queen", "count": 1, "occupant_capacity": 2}],
        "age_policy": {
            "room_min_age_inclusive": 0,
            "room_max_age_exclusive": None,
            "guardian_required_below_age_exclusive": 18,
            "child_rate_age_max_exclusive": 12,
        },
        "cot_rule": {"allowed": False, "status": "conflict"},
        "extra_bed": {"allowed": None, "status": "unknown"},
        "accessible": "Wheelchair bathroom access not confirmed.",
    })


def _rate() -> dict:
    return _fact("F-RATE", "reference_rate", {
        "rate_id": "RATE-FAM",
        "room_type_id": "FAM",
        "amount": 100,
        "currency": "VND",
        "status": "reference_only",
        "is_quote": False,
        "is_live_availability": False,
        "price_basis": {"unit": "room_night", "included_adults": 2},
        "child_charge_amount": None,
        "child_charge_currency": "VND",
        "child_charge_basis": "per child per room night",
        "child_charge_status": "unknown",
        "extra_adult_charge_amount": None,
        "extra_adult_charge_currency": "VND",
        "extra_adult_charge_basis": "per adult per room night",
        "extra_adult_charge_status": "unknown",
    })


def _candidate() -> RoomAdviceCandidate:
    return RoomAdviceCandidate(
        option_id="A",
        rooms=({"room_index": 0, "room_type_id": "FAM"},),
        assignments=tuple({
            "member_id": f"adult-{number}",
            "room_index": 0,
            "bed_index": 0,
            "bed_type": "queen",
        } for number in (1, 2)),
        rationale=({"claim_code": "party_fit", "fact_ids": ["F-ROOM"]},
                   {"claim_code": "reference_price", "fact_ids": ["F-RATE"]}),
    )


def _context(
    brief: dict, pending_fields: tuple[str, ...] = (), *, locale: str = "en",
) -> RoomAdviceContext:
    return RoomAdviceContext(
        hotel_id="HTL-SYNTH",
        brief_version=4,
        brief_data=brief,
        pending_fields=pending_fields,
        source_generation=7,
        facts=(_catalog(), _rate()),
        question="Please compare rooms against the stated requirements.",
        locale=locale,
    )


def test_explicit_budget_context_and_hard_access_requirement_round_trip_without_view_inference() -> None:
    base = GuestBriefSnapshot(1, {
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03", "nights": 2},
        "party": {"adults": 2, "children": []},
    })

    applied = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "set_room_requirements",
        "budget_amount": 5000000,
        "budget_currency": "VND",
        "budget_basis": "stay_total",
        "budget_strength": "target",
        "budget_inclusions": ["breakfast"],
        "hard_accessibility_needs": ["wheelchair_access"],
    },)))

    requirements = applied.data["room_requirements"]
    assert requirements == {
        "budget_amount": 5000000,
        "budget_currency": "VND",
        "budget_basis": "stay_total",
        "budget_strength": "target",
        "budget_inclusions": ["breakfast"],
        "hard_accessibility_needs": ["wheelchair_access"],
    }
    assert applied.pending_fields == ()
    # View is not a supported hard field; a soft/negated view statement cannot create one.
    assert "view" not in requirements
    assert "preferred_views" not in requirements
    assert "source_rate_inclusions" not in requirements


def test_budget_inclusions_are_in_native_wire_and_authorized_targets() -> None:
    brief = GuestBriefSnapshot(1, {
        "dates": {"check_in": None, "check_out": None, "nights": None},
        "party": {"adults": 2, "children": []},
    })
    schema = fact_selection_output_schema(brief)
    body = schema["properties"]["response"]
    patch_schema = body["properties"]["guest_patch"]["anyOf"][0]
    operation_schemas = patch_schema["properties"]["ops"]["items"]["anyOf"]
    room_variants = next(
        schema["anyOf"] for schema in operation_schemas
        if schema.get("anyOf", [{}])[0].get("properties", {}).get("op", {}).get("enum")
        == ["set_room_requirements"]
    )
    set_room = room_variants[0]
    assert "budget_inclusions" in set_room["properties"]
    assert set_room["properties"]["budget_inclusions"]["anyOf"][0]["maxItems"] == 8

    operation = {
        "op": "set_room_requirements",
        "budget_inclusions": ["breakfast"],
        "current_turn_quote": "include breakfast in the budget",
    }
    patch = HospitalityGuestBriefPatch.model_validate({"ops": [operation]})
    validate_guest_patch_authorization(
        operations=({"op": "set_room_requirements", "budget_inclusions": ["breakfast"]},),
        authorizations=({
            "operation_index": 0,
            "op": "set_room_requirements",
            "target_fields": ["room_requirements.budget_inclusions"],
            "intent": "explicit_request",
            "current_turn_quote": "include breakfast in the budget",
        },),
        question="Please include breakfast in the budget.",
    )
    assert patch.ops[0].budget_inclusions == ["breakfast"]


def test_missing_budget_currency_and_basis_remain_unknown_without_breaking_existing_strength_pending() -> None:
    base = GuestBriefSnapshot(1, {
        "dates": {"check_in": None, "check_out": None, "nights": None},
        "party": {"adults": 2, "children": []},
    })
    applied = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "set_room_requirements",
        "budget_amount": 3000000,
    },)))

    assert applied.data["room_requirements"] == {"budget_amount": 3000000}
    assert applied.pending_fields == ("room_requirements.budget_strength",)
    assert "budget_currency" not in applied.data["room_requirements"]
    assert "budget_basis" not in applied.data["room_requirements"]
    required = required_pending_clarification_fields(
        applied.pending_fields,
        ("room_requirements.budget_amount",),
    )
    assert required == applied.pending_fields

    without_budget = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "set_room_requirements",
        "sharing": "prefer",
    },)))
    assert without_budget.pending_fields == ()


@pytest.mark.parametrize(
    ("budget_strength", "expected_questions"),
    [
        (None, {
            "room_requirements.budget_currency", "room_requirements.budget_basis",
            "room_requirements.budget_strength",
        }),
        ("hard", {"room_requirements.budget_currency", "room_requirements.budget_basis"}),
    ],
)
def test_room_processor_never_uses_missing_budget_currency_or_basis_for_fit(
    budget_strength: str | None, expected_questions: set[str],
) -> None:
    requirements = {"budget_amount": 500}
    if budget_strength is not None:
        requirements["budget_strength"] = budget_strength
    context = _context({
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03", "nights": 2},
        "party": {"adults": 2, "children": []},
        "room_requirements": requirements,
    })
    result = asyncio.run(HospitalityRoomAdvice().recommend(
        context=context,
        draft=RoomAdviceDraft("ready", (_candidate(),)),
    ))

    assert result.status == "needs_clarification"
    assert result.options == ()
    assert {question["field"] for question in result.questions} == expected_questions


def test_guest_budget_coverage_is_not_treated_as_source_rate_inclusion() -> None:
    context = _context({
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03", "nights": 2},
        "party": {"adults": 2, "children": []},
        "room_requirements": {
            "budget_amount": 500,
            "budget_currency": "VND",
            "budget_basis": "stay_total",
            "budget_strength": "hard",
            "budget_inclusions": ["breakfast"],
        },
    })
    result = asyncio.run(HospitalityRoomAdvice().recommend(
        context=context,
        draft=RoomAdviceDraft("ready", (_candidate(),)),
    ))

    option = result.options[0]
    checks = {item["code"]: item["status"] for item in option["checks"]}
    assert checks["budget"] == "unknown"


def test_known_lower_bound_still_rejects_hard_budget_when_guest_inclusions_are_unpriced() -> None:
    context = _context({
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03", "nights": 2},
        "party": {"adults": 2, "children": []},
        "room_requirements": {
            "budget_amount": 150,
            "budget_currency": "VND",
            "budget_basis": "stay_total",
            "budget_strength": "hard",
            "budget_inclusions": ["breakfast"],
        },
    })
    result = asyncio.run(HospitalityRoomAdvice().recommend(
        context=context,
        draft=RoomAdviceDraft("ready", (_candidate(),)),
    ))

    assert result.status == "conflict"
    assert result.options == ()
    assert "hard_budget_exceeded" in result.explanation_inputs["conflicts"]
    assert result.explanation_inputs["rejected_alternatives"][0]["reason"] == "hard_budget_exceeded"


def test_open_locale_can_translate_new_budget_questions_through_checked_presentation_contract() -> None:
    context = _context({
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03", "nights": 2},
        "party": {"adults": 2, "children": []},
        "room_requirements": {"budget_amount": 500, "budget_strength": "hard"},
    })
    result = asyncio.run(HospitalityRoomAdvice().recommend(
        context=context,
        draft=RoomAdviceDraft("ready", (_candidate(),)),
    ))

    request = HospitalityRoomAdvice.localization_request(result, "ko")
    assert request is not None
    expected_keys = set(request["keys"])
    assert expected_keys == {"question.budget_currency", "question.budget_basis"}
    localized = HospitalityRoomAdvice.parse_localization(
        '{"presentation_labels":['
        '{"key":"question.budget_currency","text":"예산 통화는 무엇인가요?"},'
        '{"key":"question.budget_basis","text":"전체 기간인가요, 매일 밤 기준인가요?"}'
        ']}',
        expected_keys=tuple(request["keys"]),
        locale="ko",
    )
    assert set(localized) == expected_keys
    assert localized["question.budget_currency"] == "예산 통화는 무엇인가요?"


def test_known_access_question_retains_accessibility_confirmation_when_budget_context_is_missing() -> None:
    context = _context({
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03", "nights": 2},
        "party": {"adults": 2, "children": []},
        "room_requirements": {
            "budget_amount": 500,
            "budget_basis": "stay_total",
            "budget_strength": "hard",
            "hard_accessibility_needs": ["wheelchair_access"],
        },
    })
    draft = RoomAdviceDraft(
        "ready", (_candidate(),),
        questions=({"field": "room_requirements.hard_accessibility_needs"},),
    )
    result = asyncio.run(HospitalityRoomAdvice().recommend(context=context, draft=draft))

    access_question = next(
        question for question in result.questions
        if question["field"] == "room_requirements.hard_accessibility_needs"
    )
    assert result.explanation_inputs["known_hard_accessibility_needs"] is True
    assert "ask the hotel to confirm" in access_question["reason"].lower()
    assert any(question["field"] == "room_requirements.budget_currency" for question in result.questions)
