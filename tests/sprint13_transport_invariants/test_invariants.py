from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from staylead_platform.domains.hospitality.grounded_claim_format import (
    project_grounded_fact,
)
from staylead_platform.domains.hospitality.recommendations.transport import (
    compare_transport,
)
from staylead_platform.domains.hospitality.registration.local_guide_pack import (
    parse_local_guide_pack,
)
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
)
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    validate_committed_turn_channels,
    validate_guest_brief_proposal,
)
from staylead_platform.domains.hospitality.validators.guest_clarification import (
    validate_pending_guest_clarification,
)
from staylead_platform.platform.contracts.ai_provider import GenerationResult, Usage
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefProposal,
    GuestBriefSnapshot,
)
from staylead_platform.platform.contracts.knowledge import KnowledgeFact
from staylead_platform.platform.contracts.local_guide import LocalGuideResult
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    ConversationFailure,
    GroundedQAOrchestrator,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/hospitality/sprint13-transport-v1"


def _transport_facts() -> tuple[KnowledgeFact, ...]:
    pack = parse_local_guide_pack(FIXTURE)
    return tuple(KnowledgeFact(
        fact_id=item["fact_id"], hotel_id=item["hotel_id"], topic=item["topic"],
        subject=item["subject"], field=item["field"], value=item["value"], conditions=item["conditions"],
        status=item["status"], valid_from=item["valid_from"], valid_to=item["valid_to"],
        provenance=item["source_refs"][0],
    ) for item in pack.pack["facts"] if item["topic"].startswith("local_guide."))


def _fact(fact_id: str, topic: str, subject: str, field: str, value: object,
          conditions: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "fact_id": fact_id, "hotel_id": "HTL-S8-DEMO", "topic": topic, "subject": subject,
        "field": field, "value": value, "conditions": conditions or {}, "status": "confirmed",
        "valid_from": "2026-10-01", "valid_to": "2027-01-01",
        "provenance": {"source_id": "SYNTHETIC-APPROVED", "source_version": "1.0"},
    }


class _Retriever:
    @staticmethod
    def conflicts_for(_facts):
        return []


class _Capability:
    def __init__(self, result: LocalGuideResult) -> None:
        self.result = result

    async def recommend(self, request):
        return self.result


class _Provider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def generate(self, _request):
        return GenerationResult(
            text=json.dumps(self.payload), provider="offline", deployment="test", model="stub",
            request_id="transport-invariant", usage=Usage(),
        )


def _answer(
    payload: dict[str, object], facts: list[dict[str, object]], *, options=(),
    intents=("local_guide", "hotel_information"),
    question="What are the hotel details and nearby options?",
    brief: GuestBriefSnapshot | None = None,
    authorized_targets: tuple[str, ...] = (),
):
    guide = LocalGuideResult(
        hotel_id="HTL-S8-DEMO", generation=1,
        selected_venue_ids=("DIN-01",),
        supported_claims=({
            "venue_id": "DIN-01", "name": "Lotus Noodle", "kind": "dining", "fit_status": "fit",
            "reason_codes": (), "tradeoff_codes": (), "sponsored": False, "sponsor_label": None,
            "price": None, "duration_minutes": None, "hours_status": "confirmed", "unknowns": (),
            "fact_ids": (),
        },),
        transport_options=options,
    )
    orchestrator = GroundedQAOrchestrator(
        provider=_Provider(payload), retriever=_Retriever(), instructions="answer", committed_instructions="answer",
        response_schema=HospitalityGroundedAnswer, selection_instructions="select",
        committed_selection_instructions="select", selection_schema=HospitalityGroundedAnswer,
        clarification_validator=validate_pending_guest_clarification,
        committed_answer_validator=validate_committed_turn_channels,
        safe_fact_projector=project_grounded_fact, local_guide=_Capability(guide),
    )
    return asyncio.run(orchestrator.answer(
        hotel_id="HTL-S8-DEMO", question=question, history=[], brief=brief,
        prefetched_facts=facts, turn_intents=intents,
        authorized_targets=authorized_targets,
    ))


def _malicious_payload(channel: str) -> dict[str, object]:
    unsafe = "Lotus Shuttle fits the whole group, and license, insurance, rental eligibility and availability are confirmed."
    payload: dict[str, object] = {
        "supported_claims": [], "unknowns": [], "conflicts": [], "guest_claims": [],
        "guest_brief_refs": [], "guest_clarification": None,
        "conversational_acknowledgement": None, "label_bundle": {},
        "turn_intents": ["local_guide", "hotel_information"],
    }
    if channel == "supported_claims":
        payload[channel] = [{"text": unsafe, "fact_ids": ["F-HTL-S8-DEMO-DIN-01-name"]}]
    elif channel in {"unknowns", "conflicts"}:
        payload[channel] = [unsafe]
    elif channel == "guest_claims":
        payload[channel] = [{
            "text": "There are 5 adults, and the shuttle fits everyone.",
            "refs": ["party.adults"],
        }]
        payload["guest_brief_refs"] = ["party.adults"]
    elif channel == "guest_clarification":
        payload[channel] = {
            "field": "dates.check_out", "options": ["11", "12"],
            "text": "Would you prefer 11 or 12?",
        }
    else:
        payload["turn_intents"] = ["courtesy", "local_guide", "hotel_information"]
        payload["conversational_acknowledgement"] = {
            "intent": "thanks_acknowledged", "text": unsafe[:100],
        }
    return payload


def test_transport_result_projects_mixed_faq_and_drops_every_model_prose_channel() -> None:
    transport_facts = _transport_facts()
    options, _, _ = compare_transport(
        transport_facts, {"party": {"adults": 5, "children": []}, "transport_preferences": {
            "luggage_count": 2, "child_seat_count": 0, "access_needs": [],
        }}, (),
    )
    breakfast = _fact(
        "F-HTL-S8-BREAKFAST-HOURS", "service", "breakfast", "breakfast_hours", "07:00-10:00",
        {"timezone": "Asia/Ho_Chi_Minh"},
    )
    venue = _fact("F-HTL-S8-DEMO-DIN-01-name", "local_guide.venue", "DIN-01", "name", "Lotus Noodle")
    expected_fact_sentence = "Breakfast hours: 07:00-10:00 (timezone Asia/Ho_Chi_Minh). [F-HTL-S8-BREAKFAST-HOURS]"

    for channel in ("supported_claims", "unknowns", "conflicts", "guest_claims"):
        brief = GuestBriefSnapshot(brief_version=3, data={
            "party": {"adults": 5, "children": []},
        }) if channel == "guest_claims" else None
        answer = _answer(
            _malicious_payload(channel), [venue, breakfast], options=options, brief=brief,
        )
        assert "fits the whole group" not in answer.answer
        assert "license, insurance" not in answer.answer
        assert expected_fact_sentence in answer.answer
        assert answer.unknowns == ()
        assert not answer.guest_claims


def test_empty_checked_transport_result_still_suppresses_model_transport_claims() -> None:
    venue = _fact("F-HTL-S8-DEMO-DIN-01-name", "local_guide.venue", "DIN-01", "name", "Lotus Noodle")
    breakfast = _fact("F-HTL-S8-BREAKFAST-HOURS", "service", "breakfast", "breakfast_hours", "07:00-10:00")
    payload = _malicious_payload("supported_claims")
    payload["label_bundle"] = {"transport_options": "Transport options"}
    answer = _answer(
        payload, [venue, breakfast], options=(), intents=("local_guide", "hotel_information"),
    )

    assert "fits the whole group" not in answer.answer
    assert "license, insurance" not in answer.answer
    assert "Breakfast hours: 07:00-10:00." in answer.answer
    assert answer.label_bundle == {"transport_options": "Transport options"}


def test_transport_result_drops_model_clarification_and_acknowledgement() -> None:
    options, _, _ = compare_transport(_transport_facts(), {"party": {"adults": 2, "children": []}}, ())
    for channel in ("guest_clarification", "conversational_acknowledgement"):
        if channel == "guest_clarification":
            answer = _answer(
                _malicious_payload(channel), [], options=options,
                question="Which checkout day works, 11/12?",
                brief=GuestBriefSnapshot(brief_version=3, data={
                    "dates": {"check_in": "2026-10-01"},
                    "party": {"adults": 2, "children": []},
                }, pending_fields=("dates.check_out",)),
                authorized_targets=("dates.check_out",),
            )
        else:
            answer = _answer(
                _malicious_payload(channel), [], options=options,
                intents=("courtesy", "local_guide", "hotel_information"),
            )
        assert "Lotus Shuttle fits" not in answer.answer
        assert not answer.acknowledgement
        assert answer.brief_version_used is None


def test_transport_result_still_rejects_guest_claims_without_saved_brief() -> None:
    payload = _malicious_payload("guest_claims")
    with pytest.raises(ConversationFailure, match="guest brief that was not supplied"):
        _answer(payload, [], options=())


def test_pure_venue_flow_uses_checked_cards_and_suppresses_model_prose() -> None:
    venue = _fact("F-HTL-S8-DEMO-DIN-01-name", "local_guide.venue", "DIN-01", "name", "Lotus Noodle")
    payload = _malicious_payload("supported_claims")
    payload["supported_claims"] = [{
        "text": "Lotus Noodle is a dining venue. [F-HTL-S8-DEMO-DIN-01-name]",
        "fact_ids": ["F-HTL-S8-DEMO-DIN-01-name"],
    }]
    answer = _answer(payload, [venue], options=(), intents=("local_guide", "hotel_information"))
    assert "Lotus Noodle is a dining venue." not in answer.answer
    assert answer.local_guide_result.selected_venue_ids == ("DIN-01",)


def test_transport_root_pending_hides_saved_leaf_preferences_and_party_parent() -> None:
    facts = _transport_facts()
    stale = {"party": {"adults": 3, "children": []}, "transport_preferences": {
        "mode": "walk", "luggage_count": 1, "child_seat_count": 0, "access_needs": [],
    }}
    options, _, _ = compare_transport(facts, stale, ("transport_preferences",))
    assert {item["mode"] for item in options} == {"walk", "taxi"}
    for option in options:
        assert option["checks"]["luggage"]["required"] is None
        assert option["checks"]["luggage"]["status"] == "unknown"
    party_pending, _, _ = compare_transport(facts, stale, ("party",))
    assert all(option["checks"]["passenger_capacity"]["required"] is None for option in party_pending)
    assert all(option["checks"]["passenger_capacity"]["status"] == "unknown" for option in party_pending)


def test_transport_root_pending_normalizes_to_remaining_leaves_across_partial_edits() -> None:
    current = GuestBriefSnapshot(brief_version=4, data={
        "dates": {}, "party": {"adults": 3, "children": []},
        "transport_preferences": {
            "mode": "walk", "luggage_count": 1, "child_seat_count": 0, "access_needs": [],
        },
    }, pending_fields=("transport_preferences",))
    taxi = validate_guest_brief_proposal(current, GuestBriefProposal(({
        "op": "set_transport_preferences", "mode": "taxi",
    },)))
    assert "transport_preferences" not in taxi.pending_fields
    assert set(taxi.pending_fields) == {
        "transport_preferences.luggage_count", "transport_preferences.child_seat_count",
        "transport_preferences.access_needs",
    }
    assert taxi.data["transport_preferences"]["mode"] == "taxi"
    partially_resolved = validate_guest_brief_proposal(taxi, GuestBriefProposal(({
        "op": "set_transport_preferences", "luggage_count": 2,
    },)))
    assert set(partially_resolved.pending_fields) == {
        "transport_preferences.child_seat_count", "transport_preferences.access_needs",
    }
    fully_resolved = validate_guest_brief_proposal(partially_resolved, GuestBriefProposal(({
        "op": "set_transport_preferences", "child_seat_count": 0, "access_needs": [],
    },)))
    assert fully_resolved.pending_fields == ()
    options, _, _ = compare_transport(
        _transport_facts(), fully_resolved.data, fully_resolved.pending_fields,
    )
    assert {item["mode"] for item in options} == {"taxi"}
    assert all(item["checks"]["luggage"]["status"] == "unknown" for item in options)


def test_safe_fact_projection_preserves_material_conditions_or_fails_closed() -> None:
    fact = _fact(
        "F-HOTEL-AGE", "policy", "rental", "minimum_age", 21,
        {"reservation_required": True, "applicability": "weekends", "synthetic": True},
    )
    rendered = project_grounded_fact(fact)
    assert rendered == "Minimum age: 21 (reservation required yes, applies to weekends)."

    unsupported = _fact(
        "F-HOTEL-COMPLEX", "policy", "rental", "minimum_age", 21,
        {"eligibility": {"member_tiers": ["gold", "platinum"]}},
    )
    assert "cannot be summarized safely" in project_grounded_fact(unsupported)
