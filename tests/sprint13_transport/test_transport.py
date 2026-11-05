from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from staylead_platform.domains.hospitality.recommendations.transport import compare_transport
from staylead_platform.domains.hospitality.registration.local_guide_pack import (
    parse_local_guide_pack,
)
from staylead_platform.domains.hospitality.schemas.grounded_answer import HospitalityGroundedAnswer
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    HospitalityGuestBriefPatch,
    validate_guest_brief_proposal,
    validate_guest_patch_authorization,
)
from staylead_platform.platform.contracts.ai_provider import GenerationResult, Usage
from staylead_platform.platform.contracts.guest_brief import GuestBriefProposal, GuestBriefSnapshot
from staylead_platform.platform.contracts.knowledge import KnowledgeFact
from staylead_platform.platform.contracts.local_guide import LocalGuideResult
from staylead_platform.platform.conversation.orchestrator.grounded_qa import GroundedQAOrchestrator

FIXTURE = __import__("pathlib").Path(__file__).resolve().parents[2] / "fixtures/hospitality/sprint13-transport-v1"
SPRINT15_FIXTURE = FIXTURE.parent / "sprint15-transport-v1"


def _facts() -> tuple[KnowledgeFact, ...]:
    return _facts_for(FIXTURE)


def _facts_for(path) -> tuple[KnowledgeFact, ...]:
    pack = parse_local_guide_pack(path)
    return tuple(KnowledgeFact(
        fact_id=item["fact_id"], hotel_id=item["hotel_id"], topic=item["topic"],
        subject=item["subject"], field=item["field"], value=item["value"], conditions=item["conditions"],
        status=item["status"], valid_from=item["valid_from"], valid_to=item["valid_to"],
        provenance=item["source_refs"][0],
    ) for item in pack.pack["facts"] if item["topic"].startswith("local_guide."))


def test_transport_comparison_rejects_four_seats_for_five_and_recomputes_price() -> None:
    options, fact_ids, unknowns = compare_transport(
        _facts(), {"party": {"adults": 5, "children": []}, "transport_preferences": {
            "luggage_count": 2, "child_seat_count": 0, "access_needs": [],
        }}, (),
    )
    lotus = next(option for option in options if option["provider_id"] == "TR-01")
    assert lotus["checks"]["passenger_capacity"] == {"required": 5, "available": 4, "status": "not_fit"}
    assert lotus["fit_status"] == "not_fit"
    assert lotus["checks"]["child_seat"]["status"] == "not_required"
    assert lotus["price"] == {
        "amount": 180000, "total_amount": 180000, "currency": "VND",
        "basis": "per_vehicle_one_way", "status": "known",
    }
    river = next(option for option in options if option["provider_id"] == "TR-02")
    assert river["price"]["total_amount"] == 225000
    assert river["checks"]["luggage"]["status"] == "unknown"
    assert "availability" in " ".join(river["unknowns"])
    assert fact_ids and unknowns
    assert lotus["contact"] == {
        "url": "https://example.com/synthetic/providers/tr-01", "status": "approved",
        "source_refs": lotus["source_refs"],
    }
    assert river["contact"]["url"] is None
    assert river["contact"]["status"] == "hotel_verification_fallback"


def test_transport_missing_party_and_constraints_remain_unknown() -> None:
    options, _, _ = compare_transport(_facts(), {}, ())
    river = next(option for option in options if option["provider_id"] == "TR-02")
    assert river["checks"]["passenger_capacity"]["required"] is None
    assert river["checks"]["passenger_capacity"]["status"] == "unknown"
    assert river["checks"]["luggage"]["required"] is None
    assert river["checks"]["luggage"]["status"] == "unknown"
    assert river["price"]["total_amount"] is None
    assert river["price"]["status"] == "unknown"
    assert river["fit_status"] == "unknown"


def test_child_seat_zero_requires_explicit_zero_or_complete_current_empty_party() -> None:
    current_empty_party = {"party": {"adults": 2, "children": []}}
    cases = [
        ({}, (), "unknown"),
        ({"party": {"adults": None, "children": []}}, (), "unknown"),
        ({"party": {"adults": 2, "children": None}}, (), "unknown"),
        (current_empty_party, ("party",), "unknown"),
        (current_empty_party, ("transport_preferences.child_seat_count",), "unknown"),
        ({**current_empty_party, "transport_preferences": {"child_seat_count": 0}},
         ("transport_preferences",), "unknown"),
        (current_empty_party, (), "not_required"),
        ({"transport_preferences": {"child_seat_count": 0}}, (), "not_required"),
        ({"transport_preferences": {"child_seat_count": 0}}, ("party",), "not_required"),
    ]
    for brief, pending, expected_status in cases:
        options, _, _ = compare_transport(_facts(), brief, pending)
        child_checks = [option["checks"]["child_seat"] for option in options]
        assert child_checks and all(check["status"] == expected_status for check in child_checks), (brief, pending)
        if expected_status == "not_required" and brief.get("transport_preferences", {}).get("child_seat_count") == 0:
            assert all(check["required"] == 0 for check in child_checks)


def test_sprint15_transport_pack_uses_real_service_models_with_unknown_trip_facts() -> None:
    facts = _facts_for(SPRINT15_FIXTURE)
    options, _, _ = compare_transport(facts, {"transport_preferences": {"mode": "taxi"}}, ())
    assert {option["name"] for option in options} == {"GrabCar", "Green SM Car"}
    assert {option["mode"] for option in options} == {"taxi"}
    assert len(options) == 4
    assert {option["route"]["from"] for option in options} | {option["route"]["to"] for option in options} == {
        "HTL-S8-DEMO", "DIN-01", "ATT-01", "ATT-02",
    }
    assert all(option["checks"]["passenger_capacity"]["available"] is None for option in options)
    assert all(option["checks"]["passenger_capacity"]["status"] == "unknown" for option in options)
    assert all(option["checks"]["luggage"]["available"] is None for option in options)
    assert all(option["checks"]["child_seat"]["available"] == "unknown" for option in options)
    assert all(option["price"] == {"amount": None, "total_amount": None, "currency": None,
                                    "basis": None, "status": "unknown"} for option in options)
    assert {option["contact"]["url"] for option in options} == {
        "https://www.grab.com/vn/transport/car/", "https://www.greensm.com/vn-vi/greensm-car",
    }
    assert all(option["synthetic"] is True and option["source_refs"] for option in options)


def test_sprint15_pack_rejects_unapproved_official_contact_variants(tmp_path) -> None:
    import json
    import shutil

    for unsafe_url in (
        "https://www.grab.com/vn/transport/car/?guest=1",
        "https://www.grab.com.evil.test/vn/transport/car/",
        "https://www.greensm.com.evil.test/vn-vi/greensm-car",
    ):
        target = tmp_path / SPRINT15_FIXTURE.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(SPRINT15_FIXTURE, target)
        providers_path = target / "providers.json"
        providers = json.loads(providers_path.read_text(encoding="utf-8"))
        providers[0]["contact_url"] = unsafe_url
        providers_path.write_text(json.dumps(providers), encoding="utf-8")
        try:
            parse_local_guide_pack(target)
        except ValueError as exc:
            assert "contact" in str(exc)
        else:
            raise AssertionError(f"unapproved provider contact accepted: {unsafe_url}")


def test_child_seat_support_without_quantity_does_not_fit_positive_request() -> None:
    brief = {
        "party": {"adults": 2, "children": [{"age": 2}, {"age": 3}]},
        "transport_preferences": {
            "mode": "taxi", "luggage_count": 0, "child_seat_count": 2, "access_needs": [],
        },
    }
    options, _, _ = compare_transport(_facts(), brief, ())
    river = next(option for option in options if option["provider_id"] == "TR-02")
    assert river["checks"]["child_seat"] == {
        "required": 2, "available": "supported", "status": "unknown",
    }

    unsupported_facts = tuple(
        replace(fact, value="unsupported")
        if fact.subject == "TR-02" and fact.field == "child_seat" else fact
        for fact in _facts()
    )
    unsupported_options, _, _ = compare_transport(unsupported_facts, brief, ())
    unsupported = next(option for option in unsupported_options if option["provider_id"] == "TR-02")
    assert unsupported["checks"]["child_seat"] == {
        "required": 2, "available": "unsupported", "status": "not_fit",
    }
    assert unsupported["fit_status"] == "not_fit"


def test_per_person_transport_total_uses_current_complete_party_count() -> None:
    options, _, _ = compare_transport(
        _facts(), {"party": {"adults": 3, "children": []}, "transport_preferences": {
            "luggage_count": 0, "child_seat_count": 0, "access_needs": [],
        }}, (),
    )
    river = next(option for option in options if option["provider_id"] == "TR-02")
    assert river["price"] == {
        "amount": 45000, "total_amount": 135000, "currency": "VND",
        "basis": "per_person_one_way", "status": "known",
    }


def test_transport_edit_is_typed_versioned_and_only_clears_explicit_fields() -> None:
    current = GuestBriefSnapshot(brief_version=4, data={
        "dates": {}, "party": {"adults": 3, "children": []},
        "transport_preferences": {"mode": "walk", "luggage_count": 1, "access_needs": ["step_free"]},
    })
    quote = "Take a taxi and we will have two bags"
    operation = {
        "op": "set_transport_preferences", "mode": "taxi", "luggage_count": 2,
        "current_turn_quote": quote,
    }
    typed = HospitalityGuestBriefPatch.model_validate({"ops": [operation]})
    proposal = GuestBriefProposal((typed.ops[0].model_dump(exclude={"current_turn_quote"}),))
    auth = ({"operation_index": 0, "op": operation["op"], "target_fields": [
        "transport_preferences.mode", "transport_preferences.luggage_count",
    ], "intent": "explicit_request", "current_turn_quote": quote},)
    validate_guest_patch_authorization(proposal.operations, auth, quote)
    applied = validate_guest_brief_proposal(current, proposal)
    assert applied.data["transport_preferences"] == {"mode": "taxi", "luggage_count": 2,
                                                       "access_needs": ["step_free"]}
    assert applied.applied_delta["transport_preferences"] == {"mode": "taxi", "luggage_count": 2}

    clear = validate_guest_brief_proposal(applied, GuestBriefProposal(({
        "op": "set_transport_preferences", "clear_fields": ["access_needs"],
    },)))
    assert clear.data["transport_preferences"] == {"mode": "taxi", "luggage_count": 2}
    assert clear.applied_delta["transport_preferences"] == {"access_needs": None}


def test_transport_pack_rejects_unapproved_contact_host(tmp_path) -> None:
    import json
    import shutil

    target = tmp_path / FIXTURE.name
    shutil.copytree(FIXTURE, target)
    providers_path = target / "providers.json"
    providers = json.loads(providers_path.read_text(encoding="utf-8"))
    providers[0]["contact_url"] = "https://attacker.example/synthetic/provider"
    providers_path.write_text(json.dumps(providers), encoding="utf-8")
    try:
        parse_local_guide_pack(target)
    except ValueError as exc:
        assert "contact" in str(exc)
    else:
        raise AssertionError("unapproved synthetic contact host was accepted")


def test_composed_answer_discards_false_transport_claims_and_keeps_checked_result() -> None:
    transport_facts = _facts()
    options, _, unknowns = compare_transport(
        transport_facts, {"party": {"adults": 5, "children": []}, "transport_preferences": {
            "luggage_count": 2, "child_seat_count": 0, "access_needs": [],
        }}, (),
    )
    transport_ids = tuple(dict.fromkeys(
        ref["fact_id"] for option in options for ref in option["source_refs"]
    ))

    class Provider:
        async def generate(self, request):
            payload = {
                "supported_claims": [{
                    "text": "Lotus fits five passengers, and insurance and availability are confirmed.",
                    "fact_ids": [transport_ids[0]],
                }],
                "unknowns": [], "conflicts": [], "guest_claims": [], "guest_brief_refs": [],
                "guest_clarification": None, "conversational_acknowledgement": None, "label_bundle": {},
            }
            return GenerationResult(
                text=json.dumps(payload), provider="synthetic", deployment="offline", model="fake",
                request_id="transport-adversarial", usage=Usage(),
            )

    class Capability:
        async def recommend(self, request):
            return LocalGuideResult(
                hotel_id=request.hotel_id, generation=1, fact_ids=transport_ids,
                transport_options=options, unknowns=unknowns,
            )

    class Retriever:
        @staticmethod
        def conflicts_for(facts):
            return []

    orchestrator = GroundedQAOrchestrator(
        provider=Provider(), retriever=Retriever(), instructions="answer", committed_instructions="answer",
        response_schema=HospitalityGroundedAnswer, selection_instructions="select",
        committed_selection_instructions="select", selection_schema=HospitalityGroundedAnswer,
        local_guide=Capability(),
    )
    answer = asyncio.run(orchestrator.answer(
        hotel_id="HTL-TRANSPORT-SYNTHETIC", question="Show transport for five adults and two bags.",
        history=[], prefetched_facts=[],
        turn_intents=("local_guide",),
    ))
    lotus = next(option for option in answer.local_guide_result.transport_options if option["provider_id"] == "TR-01")
    assert answer.answer == ""
    assert lotus["fit_status"] == "not_fit"
    assert lotus["checks"]["passenger_capacity"] == {"required": 5, "available": 4, "status": "not_fit"}
    assert any("insurance" in item for item in lotus["unknowns"])
    assert any("availability" in item for item in lotus["unknowns"])
