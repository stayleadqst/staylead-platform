"""PostgreSQL version/currentness/selection contracts for persisted room advice."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, update

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.domains.hospitality.recommendations.rooms import HospitalityRoomAdvice
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    ScopeError,
    StaleSource,
    VersionConflict,
    apply_migrations,
    commit_language_preference,
    create_session,
    get_active_snapshot,
    get_guest_brief,
    get_guest_brief_receipt,
    get_room_advice_result,
    hotels,
    knowledge_facts,
    knowledge_sources,
    room_advice_results,
    save_room_advice_result,
    select_room_advice_option,
    sessions,
    update_room_advice_presentation,
)
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import (
    import_fixture_pack,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    Usage,
)
from staylead_platform.platform.contracts.room_advice import RoomAdviceResult

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1"
TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")


class RoomAdviceProvider:
    """Offline model double for the real /messages and PostgreSQL integration path."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        if "current_question" in payload:
            value = {"options": [], "questions": [{
                "field": "party.adults",
            }]}
        elif "candidate_index" in payload:
            value = {
                "fact_ids": [], "guest_patch": None,
                "turn_intents": ["room_advice"], "explicit_language_tag": None,
                "inferred_language_tag": None,
            }
        else:
            value = {
                "supported_claims": [], "unknowns": ["I will check the room fit."], "conflicts": [],
                "guest_patch": None, "turn_intents": ["room_advice"],
                "guest_claims": [], "guest_clarification": None,
                "conversational_acknowledgement": None, "guest_brief_refs": [],
                "explicit_language_tag": None, "inferred_language_tag": None,
                "label_bundle": {},
            }
        return GenerationResult(
            text=json.dumps(value), provider="offline-fake", deployment="s7-test",
            model="mock-room-advice", request_id=f"s7-fake-{len(self.calls)}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


class HappyPathRoomAdviceProvider(RoomAdviceProvider):
    def _patch(self, question: str) -> dict[str, object]:
        if "one more night" in question.lower():
            ops = [{"op": "set_dates", "check_in": None, "check_out": "2026-11-05",
                    "current_turn_quote": "checkout is 2026-11-05"}]
        else:
            ops = [
                {"op": "set_dates", "check_in": "2026-11-01", "check_out": "2026-11-04",
                 "current_turn_quote": "check in 2026-11-01 and check out 2026-11-04"},
                {"op": "set_adults", "count": 2, "current_turn_quote": "Two adults"},
                {"op": "set_bed_sharing", "member_ids": ["adult-1", "adult-2"], "allow_share": True,
                 "current_turn_quote": "we can share a queen bed"},
            ]
        return {"ops": ops}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        question = str(payload.get("question", payload.get("current_question", "")))
        if "current_question" in payload:
            brief = payload["committed_guest_brief"]
            facts = payload["guest_facts"]
            room = next(item for item in facts if item.get("field") == "room_type"
                        and item.get("value", {}).get("room_type_id") == "CITY-STD")
            rate = next(item for item in facts if item.get("field") == "reference_rate"
                        and item.get("value", {}).get("room_type_id") == "CITY-STD")
            beds = room["value"]["beds"]
            bed_slot = (0, beds[0]["type"])
            members = [f"adult-{index}" for index in range(1, brief["party"]["adults"] + 1)]
            candidate = {
                "option_id": f"city-standard-{len([p for p in self.calls if 'current_question' in p])}",
                "rooms": [{"room_index": 0, "room_type_id": "CITY-STD"}],
                "assignments": [
                    {"member_id": member, "room_index": 0, "bed_index": bed_index, "bed_type": bed_type}
                    for member in members for bed_index, bed_type in [bed_slot]
                ],
                "rationale": [{
                    "claim_code": "reference_price",
                    "fact_ids": [rate["fact_id"]],
                }],
            }
            value: dict[str, object] = {"options": [candidate], "questions": []}
        elif "candidate_index" in payload:
            patch = self._patch(question)
            value = {"fact_ids": [], "guest_patch": patch,
                     "turn_intents": ["guest_edit", "room_advice"], "explicit_language_tag": None,
                     "inferred_language_tag": None}
        else:
            patch = self._patch(question)
            keys = payload.get("missing_label_keys", [])
            value = {
                "supported_claims": [], "unknowns": ["I will check the room fit."], "conflicts": [],
                "guest_patch": patch,
                "turn_intents": ["guest_edit", "room_advice"], "guest_claims": [],
                "guest_clarification": None, "conversational_acknowledgement": None,
                "guest_brief_refs": [], "explicit_language_tag": None, "inferred_language_tag": None,
                "label_bundle": {key: f"label-{key}" for key in keys},
            }
        return GenerationResult(
            text=json.dumps(value), provider="offline-fake", deployment="s7-test",
            model="mock-room-advice", request_id=f"s7-fake-{len(self.calls)}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


class BookingIntentProvider(RoomAdviceProvider):
    def __init__(self, mixed: bool = False) -> None:
        super().__init__()
        self.mixed = mixed

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        intents = ["booking_request", "hotel_information"] if self.mixed else ["booking_request"]
        if "candidate_index" in payload:
            value = {
                "fact_ids": [], "guest_patch": None,
                "turn_intents": intents, "explicit_language_tag": None,
                "inferred_language_tag": None,
            }
        else:
            value = {
                "supported_claims": [], "unknowns": ["I could not confirm booking details from hotel records."] if self.mixed else [], "conflicts": [],
                "guest_patch": None, "turn_intents": intents,
                "guest_claims": [], "guest_clarification": None,
                "conversational_acknowledgement": None, "guest_brief_refs": [],
                "explicit_language_tag": None, "inferred_language_tag": None,
                "label_bundle": {},
            }
        return GenerationResult(
            text=json.dumps(value), provider="offline-fake", deployment="s7-test",
            model="mock-booking-intent", request_id=f"s7-booking-{len(self.calls)}",
            usage=Usage(input_tokens=2, output_tokens=2, total_tokens=4),
        )


class UnknownChildSharingProvider(RoomAdviceProvider):
    def __init__(self) -> None:
        super().__init__()
        self.schemas: list[dict[str, object] | None] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        self.schemas.append(request.response_schema)
        question = str(payload["question"])
        patch = {"ops": [
            {"op": "set_adults", "count": 1, "current_turn_quote": "I am one adult"},
            {"op": "add_child", "age": 7, "guardian_adult_index": 1,
             "share_bed_with_guardian": None, "requires_separate_bed": None,
             "current_turn_quote": "Our seven-year-old"},
            {"op": "set_bed_sharing", "member_ids": ["adult-1", "child-1"],
             "allow_share": True, "current_turn_quote": "Our seven-year-old may share my bed"},
        ]}
        if "candidate_index" in payload:
            value = {
                "fact_ids": [], "guest_patch": patch, "turn_intents": ["guest_edit"],
                "explicit_language_tag": None, "inferred_language_tag": None,
            }
        else:
            value = {
                "supported_claims": [], "unknowns": [], "conflicts": [],
                "guest_patch": patch, "turn_intents": ["guest_edit"], "guest_claims": [],
                "guest_clarification": None, "conversational_acknowledgement": None,
                "guest_brief_refs": [], "explicit_language_tag": None,
                "inferred_language_tag": None, "label_bundle": {},
            }
        assert "Our seven-year-old" in question
        return GenerationResult(
            text=json.dumps(value), provider="offline-fake", deployment="s7-test",
            model="mock-invalid-child-id", request_id="s7-invalid-child-id",
            usage=Usage(input_tokens=4, output_tokens=5, total_tokens=9),
        )


class LanguageOnlyRoomAdviceProvider(HappyPathRoomAdviceProvider):
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        question = str(payload.get("question", payload.get("current_question", "")))
        if "locale" in payload and "presentation_templates" in payload:
            self.calls.append(payload)
            translations = {
                "claim.party_fit": "Cette configuration convient au groupe confirmé et respecte les règles vérifiées.",
                "claim.bed_setup": "La configuration des lits indiquée correspond aux lits vérifiés.",
                "claim.reference_price": "Estimation indicative du tarif pour le séjour : {amount} {currency}.",
                "claim.policy_confirmation": "Certains détails de la chambre restent à confirmer.",
                "claim.accessibility_confirmation": "L'accessibilité de cette chambre n'est pas confirmée.",
                "claim.preference_tradeoff": "Cette option ne répond pas à une préférence de partage ou de type de lit.",
                "claim.charges_confirmation": "Certains frais d'enfant ou de couchage supplémentaire ne sont pas inclus.",
                "question.dates": "Quelles sont vos dates d'arrivée et de départ ?",
                "question.party": "Combien d'adultes séjourneront ?",
                "question.age": "Quel âge a chaque enfant ?",
                "question.room": "Quelle exigence de chambre dois-je retenir ?",
                "question.rate_basis": "Pouvez-vous confirmer si ce tarif est calculé par chambre et par nuit ?",
                "question.rate_validity_window": "Ces dates dépassent la période du tarif source. Pouvez-vous confirmer le tarif actuel ?",
                "question.hard_budget_exceeded": "Cette option dépasse le budget confirmé. Souhaitez-vous modifier le budget ou essayer une autre option ?",
                "question.source_fact_conflict": "Les informations sources sur la chambre sont contradictoires. Puis-je chercher une autre option ?",
                "question.room_rule_conflict": "Cette option contredit une règle confirmée. Souhaitez-vous essayer une autre disposition ?",
                "question.generic": "Pouvez-vous confirmer ce détail concernant la chambre ?",
            }
            value = {"presentation_labels": [
                {"key": key, "text": translations[key]}
                for key in payload["presentation_templates"]
            ]}
            return GenerationResult(
                text=json.dumps(value, ensure_ascii=False), provider="offline-fake", deployment="s7-test",
                model="mock-french-localization", request_id=f"s7-french-{len(self.calls)}",
                usage=Usage(input_tokens=2, output_tokens=4, total_tokens=6),
            )
        if "french" in question.lower() and "candidate_index" in payload:
            self.calls.append(payload)
            value = {
                "fact_ids": [], "guest_patch": None,
                "turn_intents": ["room_advice"], "explicit_language_tag": "fr",
                "inferred_language_tag": None,
            }
            return GenerationResult(
                text=json.dumps(value), provider="offline-fake", deployment="s7-test",
                model="mock-language-only", request_id=f"s7-language-{len(self.calls)}",
                usage=Usage(input_tokens=2, output_tokens=2, total_tokens=4),
            )
        if "french" in question.lower() and "current_question" in payload:
            self.calls.append(payload)
            alternate = {
                "option_id": "must-not-replace-existing-option",
                "rooms": [{"room_index": 0, "room_type_id": "LAGOON-FAM"}],
                "assignments": [{"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "king"}],
                "rationale": [],
            }
            return GenerationResult(
                text=json.dumps({"options": [alternate], "questions": []}),
                provider="offline-fake", deployment="s7-test", model="must-not-run",
                request_id=f"s7-must-not-run-{len(self.calls)}", usage=Usage(),
            )
        generated = await super().generate(request)
        if "presentation_templates" in payload and "current_question" in payload:
            value = json.loads(generated.text)
            value["presentation_labels"] = [{
                "key": "claim.reference_price",
                "text": "Estimation indicative du tarif pour le séjour : {amount} {currency}.",
            }]
            return GenerationResult(
                text=json.dumps(value, ensure_ascii=False), provider=generated.provider,
                deployment=generated.deployment, model=generated.model,
                request_id=generated.request_id, usage=generated.usage,
            )
        return generated


class AdviceThenBookingProvider(LanguageOnlyRoomAdviceProvider):
    def __init__(self) -> None:
        super().__init__()
        self.booking_mode = False

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        question = str(payload.get("question", payload.get("current_question", "")))
        if not self.booking_mode or "How do I book a room?" not in question:
            return await super().generate(request)
        self.calls.append(payload)
        if "candidate_index" in payload:
            value = {
                "fact_ids": [], "guest_patch": None,
                "turn_intents": ["booking_request"], "explicit_language_tag": None,
                "inferred_language_tag": None,
            }
        else:
            value = {
                "supported_claims": [], "unknowns": [], "conflicts": [],
                "guest_patch": None, "turn_intents": ["booking_request"],
                "guest_claims": [], "guest_clarification": None,
                "conversational_acknowledgement": None, "guest_brief_refs": [],
                "explicit_language_tag": None, "inferred_language_tag": None,
                "label_bundle": {},
            }
        return GenerationResult(
            text=json.dumps(value), provider="offline-fake", deployment="s7-test",
            model="mock-booking-after-room-advice", request_id=f"s7-after-booking-{len(self.calls)}",
            usage=Usage(input_tokens=2, output_tokens=2, total_tokens=4),
        )


class MixedHotelAnswerRoomAdviceProvider(HappyPathRoomAdviceProvider):
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        if "candidate_index" in payload:
            self.calls.append(payload)
            selected_name = next(
                item["fact_id"] for item in payload["candidate_index"]
                if item.get("fact_id") == "F-HTL-CITY01-001"
            )
            patch = self._patch(str(payload.get("question", "")))
            value = {
                "fact_ids": [selected_name], "guest_patch": patch,
                "turn_intents": ["hotel_information", "guest_edit", "room_advice"],
                "explicit_language_tag": None, "inferred_language_tag": None,
            }
            return GenerationResult(
                text=json.dumps(value), provider="offline-fake", deployment="s7-test",
                model="mock-mixed-room-advice", request_id=f"s7-mixed-{len(self.calls)}",
                usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
            )
        generated = await super().generate(request)
        if "current_question" not in payload:
            return generated
        value = json.loads(generated.text)
        value["hotel_answer"] = {
            "supported_claims": [{
                "text": "The hotel is Harbor City Demo [F-HTL-CITY01-001].",
                "fact_ids": ["F-HTL-CITY01-001"],
            }],
            "unknowns": [], "conflicts": [],
        }
        return GenerationResult(
            text=json.dumps(value), provider=generated.provider, deployment=generated.deployment,
            model=generated.model, request_id=generated.request_id, usage=generated.usage,
        )


class PineAgeAndAccessibilityProvider(RoomAdviceProvider):
    """Exercise contextual clear-fields, M4, French labels, and persisted result in one API path."""

    def __init__(self) -> None:
        super().__init__()
        self.child_id: str | None = None
        self.schemas: list[dict[str, object] | None] = []

    def _patch(self, question: str) -> dict[str, object]:
        if "seven-year-old" not in question:
            assert self.child_id is not None
            return {"ops": [
                {"op": "set_child_age", "member_id": self.child_id, "age": 8,
                 "current_turn_quote": "change my saved child's age to 8"},
                {"op": "set_room_requirements", "clear_fields": [
                    "hard_accessibility_needs",
                ], "current_turn_quote": "remove the step-free entry and wheelchair bathroom requirements"},
            ]}
        return {"ops": [
            {"op": "set_adults", "count": 1, "current_turn_quote": "one adult"},
            {"op": "add_child", "age": 7, "guardian_adult_index": 1,
             "share_bed_with_guardian": True, "requires_separate_bed": None,
             "current_turn_quote": "I am one adult with my seven-year-old; I am the guardian and we may share a bed"},
            {"op": "set_dates", "check_in": "2026-11-10", "check_out": "2026-11-12",
             "current_turn_quote": "Check in 2026-11-10, check out 2026-11-12"},
            {"op": "set_room_requirements", "hard_accessibility_needs": [
                "step-free entry", "wheelchair-accessible bathroom",
            ], "current_turn_quote": "We require step-free entry and wheelchair-accessible bathroom"},
        ]}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        self.schemas.append(request.response_schema)
        question = str(payload.get("question", payload.get("current_question", "")))
        if "current_question" in payload:
            facts = payload["guest_facts"]
            brief = payload["committed_guest_brief"]
            if (brief.get("room_requirements") or {}).get("hard_accessibility_needs"):
                value = {"options": [], "questions": [{
                    "field": "room_requirements.hard_accessibility_needs",
                }]}
                return GenerationResult(
                    text=json.dumps(value), provider="offline-fake", deployment="s7-test",
                    model="mock-pine-clear-and-french", request_id=f"s7-pine-clear-{len(self.calls)}",
                    usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
                )
            room = next(fact for fact in facts if fact.get("field") == "room_type"
                        and fact.get("value", {}).get("room_type_id") == "PINE-LOFT")
            rate = next(fact for fact in facts if fact.get("field") == "reference_rate"
                        and fact.get("value", {}).get("room_type_id") == "PINE-LOFT")
            child_id = brief["party"]["children"][0]["member_id"]
            templates = payload.get("presentation_templates", {})
            french = {
                "claim.party_fit": "Cette configuration convient au groupe confirmé et respecte les règles vérifiées.",
                "claim.reference_price": "Estimation indicative du tarif pour le séjour : {amount} {currency}.",
                "claim.charges_confirmation": "Certains frais d'enfant ou de couchage supplémentaire ne sont pas inclus.",
            }
            value = {
                "options": [{
                    "option_id": "pine-loft-age-eight",
                    "rooms": [{"room_index": 0, "room_type_id": "PINE-LOFT"}],
                    "assignments": [
                        {"member_id": "adult-1", "room_index": 0, "bed_index": 0, "bed_type": "queen"},
                        {"member_id": child_id, "room_index": 0, "bed_index": 0, "bed_type": "queen"},
                    ],
                    "rationale": [
                        {"claim_code": "party_fit", "fact_ids": [room["fact_id"]]},
                        {"claim_code": "reference_price", "fact_ids": [rate["fact_id"]]},
                        {"claim_code": "charges_confirmation", "fact_ids": [rate["fact_id"]]},
                    ],
                }],
                "questions": [],
                "presentation_labels": [
                    {"key": key, "text": french[key]}
                    for key in french if key in templates
                ],
            }
        else:
            patch = self._patch(question)
            intents = ["guest_edit"]
            locale = None
            if "recommend a room" in question.lower():
                intents.append("room_advice")
                if "in French" in question:
                    locale = "fr"
            value = {
                "fact_ids": [], "guest_patch": patch,
                "turn_intents": intents, "explicit_language_tag": locale,
                "inferred_language_tag": None,
            }
            if "candidate_index" not in payload:
                value = {
                    "supported_claims": [], "unknowns": ["I can check the room fit next."], "conflicts": [],
                    "guest_patch": patch, "turn_intents": intents, "guest_claims": [],
                    "guest_clarification": None, "conversational_acknowledgement": None,
                    "guest_brief_refs": [], "explicit_language_tag": locale,
                    "inferred_language_tag": None, "label_bundle": {},
                }
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="offline-fake", deployment="s7-test",
            model="mock-pine-clear-and-french", request_id=f"s7-pine-clear-{len(self.calls)}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to an isolated Sprint 7 PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    assert apply_migrations(database) == 8
    import_fixture_pack(database, FIXTURE_ROOT)
    yield database
    database.dispose()


def _confirm(client: TestClient, session: dict[str, object], challenge: dict[str, object], request_id: str):
    return client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": request_id,
              "confirmation_token": challenge["brief_confirmation"]["token"]},
    )


def _scope(engine):
    snapshot = get_active_snapshot(engine, "HTL-CITY01")
    assert snapshot is not None
    session_id = str(uuid.uuid4())
    create_session(engine, session_id, "HTL-CITY01", datetime.now(UTC) + timedelta(hours=1))
    with engine.connect() as connection:
        hotel = connection.execute(select(hotels).where(hotels.c.hotel_id == "HTL-CITY01")).mappings().one()
    source = next(source for source in snapshot.sources if source.status == "approved")
    with engine.connect() as connection:
        fact_id = connection.execute(select(knowledge_facts.c.fact_id).where(
            knowledge_facts.c.hotel_id == "HTL-CITY01",
            knowledge_facts.c.source_id == source.source_id,
        ).limit(1)).scalar_one()
    source_refs = [{
        "source": {
            "hotel_id": source.hotel_id,
            "source_id": source.source_id,
            "hotel_generation": source.hotel_generation,
            "source_version": source.source_version,
            "source_hash": source.source_hash,
            "status": source.status,
            "guest_approved": source.guest_approved,
            "valid_from": source.valid_from,
            "valid_to": source.valid_to,
        },
        "fact_ids": [fact_id],
    }]
    return session_id, snapshot, hotel, source_refs


def test_result_snapshot_is_idempotent_persisted_and_selection_is_versioned(engine) -> None:
    session_id, snapshot, hotel, source_refs = _scope(engine)
    request_id = f"s7-{uuid.uuid4()}"
    payload = {
        "status": "ready", "availability": "unknown", "options": [
        {"option_id": "option-a", "rooms": [{"room_index": 0, "room_type_id": "CITY-STD"}]},
        ], "questions": [], "explanation_inputs": {},
    }
    saved = save_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=request_id,
        payload=payload, brief_version=0, source_generation=snapshot.generation,
        config_version=hotel["config_version"], source_refs=source_refs, expected_state_version=0,
    )
    replay = save_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=request_id,
        payload=payload, brief_version=0, source_generation=snapshot.generation,
        config_version=hotel["config_version"], source_refs=source_refs, expected_state_version=0,
    )
    assert replay["result_id"] == saved["result_id"]
    assert replay["result_version"] == saved["result_version"] == 1
    assert replay["dependency_fingerprint"] == saved["dependency_fingerprint"]
    assert replay["created_at"] == saved["created_at"]
    assert get_room_advice_result(engine, session_id=session_id, hotel_id="HTL-CITY01")["currentness"] == "current"

    other_session_id = str(uuid.uuid4())
    create_session(engine, other_session_id, "HTL-CITY01", datetime.now(UTC) + timedelta(hours=1))
    assert get_room_advice_result(
        engine, session_id=other_session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
    ) is None
    assert get_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-OTHER", result_id=saved["result_id"],
    ) is None
    with pytest.raises(ScopeError):
        select_room_advice_option(
            engine, session_id=other_session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
            expected_result_version=1, option_id="option-a",
        )
    with pytest.raises(VersionConflict):
        select_room_advice_option(
            engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
            expected_result_version=2, option_id="option-a",
        )
    with pytest.raises(ScopeError):
        select_room_advice_option(
            engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
            expected_result_version=1, option_id="forged-option",
        )

    selected = select_room_advice_option(
        engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
        expected_result_version=1, option_id="option-a",
    )
    assert (selected["result_id"], selected["result_version"], selected["option_id"]) == (
        saved["result_id"], 1, "option-a",
    )
    assert get_room_advice_result(engine, session_id=session_id, hotel_id="HTL-CITY01")["selection"]["option_id"] == "option-a"

    # A later committed turn supersedes older advice even when the source set is unchanged.
    with engine.begin() as connection:
        connection.execute(update(sessions).where(sessions.c.session_id == session_id)
                           .values(state_version=1))
    latest = save_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=f"s7-{uuid.uuid4()}",
        payload={"status": "ready", "availability": "unknown", "options": [
            {"option_id": "option-b", "rooms": [{"room_index": 0, "room_type_id": "CITY-STD"}]},
        ], "questions": [], "explanation_inputs": {}},
        brief_version=0, source_generation=snapshot.generation,
        config_version=hotel["config_version"], source_refs=source_refs, expected_state_version=1,
    )
    assert latest["result_version"] == 2
    assert get_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
    )["currentness"] == "stale"
    assert get_room_advice_result(engine, session_id=session_id, hotel_id="HTL-CITY01")["result_id"] == latest["result_id"]
    result_before_language_change = get_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=latest["result_id"],
    )
    commit_language_preference(
        engine, session_id=session_id, hotel_id="HTL-CITY01", language_tag="fr",
        source="explicit", expected_revision=0,
    )
    result_after_language_change = get_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=latest["result_id"],
    )
    assert result_after_language_change["currentness"] == "current"
    assert result_after_language_change["dependency_fingerprint"] == result_before_language_change["dependency_fingerprint"]
    assert result_after_language_change["payload"] == result_before_language_change["payload"]
    with pytest.raises(StaleSource):
        select_room_advice_option(
            engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
            expected_result_version=1, option_id="option-a",
        )

    with engine.begin() as connection:
        connection.execute(update(hotels).where(hotels.c.hotel_id == "HTL-CITY01")
                           .values(knowledge_generation=hotels.c.knowledge_generation + 1))
    stale = get_room_advice_result(engine, session_id=session_id, hotel_id="HTL-CITY01")
    assert stale["currentness"] == "stale"
    assert stale["selection"] is None
    with pytest.raises(StaleSource):
        select_room_advice_option(
            engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
            expected_result_version=1, option_id="option-a",
        )
    with engine.connect() as connection:
        assert connection.scalar(select(room_advice_results.c.payload).where(
            room_advice_results.c.result_id == saved["result_id"],
        )) == payload


def test_open_locale_presentation_persists_without_changing_checked_result(engine) -> None:
    session_id, snapshot, hotel, source_refs = _scope(engine)
    legacy_advice = RoomAdviceResult(
        status="ready", brief_version=0, source_generation=snapshot.generation,
        source_refs=tuple(source_refs), options=({
            "option_id": "option-a", "assignments": [{"member_id": "adult-1", "room_index": 0}],
            "checks": [{"code": "party_fit", "status": "pass"}],
            "cost": {"total": 1000000, "currency": "VND"},
            "rooms": [{"room_index": 0, "room_type_id": "CITY-STD"}],
            "rationale": [{"claim_code": "party_fit", "fact_ids": [source_refs[0]["fact_ids"][0]],
                           "text": "This arrangement fits.", "locale": "en", "locale_fallback": False}],
        },), questions=({
            "field": "room_requirements.budget_strength", "reason": "Is this budget a hard limit or a target?",
            "locale": "en", "locale_fallback": False,
        },), explanation_inputs={"unknowns": ["rate_basis"]},
    )
    payload = asdict(legacy_advice)
    payload.pop("presentation_locale")
    payload.pop("presentation_labels")
    saved = save_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=f"s7-{uuid.uuid4()}",
        payload=payload, brief_version=0, source_generation=snapshot.generation,
        config_version=hotel["config_version"], source_refs=source_refs, expected_state_version=0,
    )
    preference = commit_language_preference(
        engine, session_id=session_id, hotel_id="HTL-CITY01", language_tag="fr",
        source="explicit", expected_revision=0,
    )
    localized = asdict(HospitalityRoomAdvice.relocalize(
        legacy_advice, "fr", {
            "claim.party_fit": "Cette configuration convient au groupe confirmé.",
            "question.budget_strength": "Ce budget est-il une limite stricte ou un objectif ?",
        },
    ))
    updated = update_room_advice_presentation(
        engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
        expected_result_version=saved["result_version"], expected_payload=payload,
        payload=localized, expected_language_revision=preference["revision"],
    )
    persisted = get_room_advice_result(engine, session_id=session_id, hotel_id="HTL-CITY01")
    localized_json = json.loads(json.dumps(localized))
    assert persisted["payload"] == localized_json
    assert persisted["result_version"] == saved["result_version"]
    assert persisted["dependency_fingerprint"] == saved["dependency_fingerprint"]
    assert updated["result_id"] == saved["result_id"]
    assert persisted["payload"]["questions"][0]["presentation_key"] == "question.budget_strength"
    assert persisted["payload"]["questions"][0]["reason"] == "Ce budget est-il une limite stricte ou un objectif ?"

    selected = select_room_advice_option(
        engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
        expected_result_version=saved["result_version"], option_id="option-a",
    )
    assert selected["option_id"] == "option-a"
    assert get_room_advice_result(engine, session_id=session_id, hotel_id="HTL-CITY01")["payload"] == localized_json

    forged = json.loads(json.dumps(localized))
    forged["options"][0]["cost"]["total"] += 1
    with pytest.raises(ValueError, match="checked decision content"):
        update_room_advice_presentation(
            engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
            expected_result_version=saved["result_version"], expected_payload=localized,
            payload=forged, expected_language_revision=preference["revision"],
        )


def test_accessibility_question_presentation_key_survives_open_locale_cas(engine) -> None:
    session_id, snapshot, hotel, source_refs = _scope(engine)
    advice = RoomAdviceResult(
        status="needs_clarification", brief_version=0, source_generation=snapshot.generation,
        source_refs=tuple(source_refs), questions=({
            "field": "room_requirements.hard_accessibility_needs",
        },), explanation_inputs={
            "unknowns": ["no checked room candidate"], "known_hard_accessibility_needs": True,
        },
    )
    english = asdict(HospitalityRoomAdvice.relocalize(advice, "en"))
    assert english["questions"][0]["presentation_key"] == "question.accessibility_confirmation"
    saved = save_room_advice_result(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=f"s7-{uuid.uuid4()}",
        payload=english, brief_version=0, source_generation=snapshot.generation,
        config_version=hotel["config_version"], source_refs=source_refs, expected_state_version=0,
    )
    preference = commit_language_preference(
        engine, session_id=session_id, hotel_id="HTL-CITY01", language_tag="fr",
        source="explicit", expected_revision=0,
    )
    french = asdict(HospitalityRoomAdvice.relocalize(
        advice, "fr", {
            "question.accessibility_confirmation": (
                "Votre besoin est noté, mais aucune option vérifiée ne le confirme. "
                "Veuillez demander confirmation à l'hôtel."
            ),
        },
    ))
    updated = update_room_advice_presentation(
        engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
        expected_result_version=saved["result_version"], expected_payload=english,
        payload=french, expected_language_revision=preference["revision"],
    )
    persisted = get_room_advice_result(engine, session_id=session_id, hotel_id="HTL-CITY01")
    assert updated["result_id"] == saved["result_id"]
    assert persisted["payload"]["questions"][0]["presentation_key"] == "question.accessibility_confirmation"
    assert persisted["payload"]["questions"][0]["reason"] == french["questions"][0]["reason"]
    assert persisted["result_version"] == saved["result_version"]

    forged_key = json.loads(json.dumps(french))
    forged_key["questions"][0]["presentation_key"] = "question.forged_accessibility"
    with pytest.raises(ValueError, match="invalid presentation key"):
        update_room_advice_presentation(
            engine, session_id=session_id, hotel_id="HTL-CITY01", result_id=saved["result_id"],
            expected_result_version=saved["result_version"], expected_payload=french,
            payload=forged_key, expected_language_revision=preference["revision"],
        )


def test_config_change_after_generation_pin_rejects_commit(engine) -> None:
    session_id, snapshot, hotel, source_refs = _scope(engine)
    pinned_config_version = hotel["config_version"]
    with engine.begin() as connection:
        connection.execute(update(hotels).where(hotels.c.hotel_id == "HTL-CITY01")
                           .values(config_version="changed-during-provider-call"))

    try:
        with pytest.raises(StaleSource, match="dependencies changed"):
            save_room_advice_result(
                engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=f"s7-{uuid.uuid4()}",
                payload={"status": "ready", "availability": "unknown", "options": [],
                         "questions": [], "explanation_inputs": {}},
                brief_version=0, source_generation=snapshot.generation,
                config_version=pinned_config_version, source_refs=source_refs, expected_state_version=0,
            )
    finally:
        with engine.begin() as connection:
            connection.execute(update(hotels).where(hotels.c.hotel_id == "HTL-CITY01")
                               .values(config_version=pinned_config_version))


def test_messages_runs_committed_room_advice_and_persists_result(engine) -> None:
    provider = RoomAdviceProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-seven-room-advice-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    response = client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": str(uuid.uuid4()), "question": "Please recommend a room for my stay."},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(provider.calls) == 2
    assert body["room_advice"]["status"] == "needs_clarification"
    assert body["room_advice"]["availability"] == "unknown"
    assert body["room_advice"]["currentness"] == "current"
    assert body["room_advice"]["result_version"] == 1
    assert body["room_advice"]["questions"][0]["field"] == "party.adults"
    persisted = get_room_advice_result(
        engine, session_id=session["session_id"], hotel_id="HTL-CITY01",
    )
    assert persisted is not None
    assert persisted["payload"]["questions"][0]["field"] == "party.adults"


@pytest.mark.parametrize(("mixed", "expected_calls"), [(False, 1), (True, 2)])
def test_messages_routes_booking_request_to_trusted_channel(engine, mixed: bool, expected_calls: int) -> None:
    provider = BookingIntentProvider(mixed=mixed)
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-seven-booking-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    response = client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": str(uuid.uuid4()), "question": "How do I book a room?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["booking_request"] == {"requested": True}
    assert session["hotel"]["booking_channel"]["destination_url"] == "https://booking.example/hotels/harbor-city-demo"
    assert all("booking.example" not in str(call) for call in provider.calls)
    assert len(provider.calls) == expected_calls
    assert body["trace"]["calls"] == len(provider.calls)


def test_pure_booking_response_omission_preserves_selected_current_advice(engine) -> None:
    provider = AdviceThenBookingProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-seven-booking-preserves-advice-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}"
    advised = client.post(f"{endpoint}/messages", headers=headers, json={
        "request_id": str(uuid.uuid4()),
        "question": "Two adults, we can share a queen bed, check in 2026-11-01 and check out 2026-11-04. Recommend a room.",
    })
    assert advised.status_code == 200, advised.text
    challenge = advised.json()
    assert challenge["confirmation_required"] is True
    assert len(provider.calls) == 1
    confirmed = _confirm(client, session, challenge, str(uuid.uuid4()))
    assert confirmed.status_code == 200, confirmed.text
    advice = confirmed.json()["room_advice"]
    assert len(provider.calls) == 2
    assert advice["currentness"] == "current" and advice["options"]
    selected = client.post(
        f"{endpoint}/room-advice/{advice['result_id']}/selection", headers=headers,
        json={"result_version": advice["result_version"], "option_id": advice["options"][0]["option_id"]},
    )
    assert selected.status_code == 200, selected.text
    selected_option_id = selected.json()["option_id"]
    before = client.get(f"{endpoint}/room-advice", headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["currentness"] == "current"
    before_result_id = before.json()["result_id"]
    before_version = before.json()["result_version"]
    assert before.json()["selection"]["option_id"] == selected_option_id

    provider.booking_mode = True
    call_count_before_booking = len(provider.calls)
    booking = client.post(f"{endpoint}/messages", headers=headers, json={
        "request_id": str(uuid.uuid4()), "question": "How do I book a room?",
    })
    assert booking.status_code == 200, booking.text
    body = booking.json()
    assert body["booking_request"] == {"requested": True}
    assert "room_advice" not in body
    assert body["trace"]["calls"] == 1
    assert len(provider.calls) == call_count_before_booking + 1
    after = client.get(f"{endpoint}/room-advice", headers=headers)
    assert after.status_code == 200, after.text
    assert after.json()["currentness"] == "current"
    assert (after.json()["result_id"], after.json()["result_version"]) == (before_result_id, before_version)
    assert after.json()["selection"]["option_id"] == selected_option_id


def test_messages_commits_two_adult_room_advice_selects_and_recalculates(engine) -> None:
    provider = LanguageOnlyRoomAdviceProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-seven-room-advice-happy-test-signing-secret"),
        validation_diagnostics=True,
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}/messages"
    first_request_id = str(uuid.uuid4())
    first_question = "Two adults, we can share a queen bed, check in 2026-11-01 and check out 2026-11-04. Recommend a room."
    first_response = client.post(endpoint, headers=headers, json={
        "request_id": first_request_id, "question": first_question,
    })
    assert first_response.status_code == 200, first_response.text
    challenge = first_response.json()
    assert challenge["confirmation_required"] is True
    assert len(provider.calls) == 1, "reviewing a brief edit must stop before M2 and room advice"
    confirm_id = str(uuid.uuid4())
    confirmed = client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations", headers=headers,
        json={"request_id": confirm_id, "confirmation_token": challenge["brief_confirmation"]["token"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    first = confirmed.json()
    advice = first["room_advice"]
    assert len(provider.calls) == 2, "confirmation continues with a bounded committed-answer/room-advice turn"
    assert advice["status"] == "ready", advice.get("explanation_inputs")
    assert advice["availability"] == "unknown"
    assert advice["currentness"] == "current"
    assert advice["options"][0]["rooms"][0]["room_type_id"] == "CITY-STD"
    assert advice["options"][0]["cost"]["total"] == 5_400_000
    assert advice["options"][0]["cost"]["currency"] == "VND"
    freshness_endpoint = f"/v1/guest/sessions/{session['session_id']}/freshness"
    initial_freshness = client.post(freshness_endpoint, headers=headers, json={"request_id": confirm_id})
    assert initial_freshness.status_code == 200, initial_freshness.text
    assert initial_freshness.json() == {"status": "current", "answer_eligibility": "current",
                                        "room_advice_currentness": "current"}
    with engine.connect() as connection:
        initial_config_version = connection.execute(
            select(hotels.c.config_version).where(hotels.c.hotel_id == "HTL-CITY01"),
        ).scalar_one()
    with engine.begin() as connection:
        connection.execute(update(hotels).where(hotels.c.hotel_id == "HTL-CITY01")
                           .values(config_version="s7-freshness-config-change"))
    try:
        config_freshness = client.post(
            freshness_endpoint, headers=headers, json={"request_id": confirm_id},
        )
        assert config_freshness.status_code == 200, config_freshness.text
        assert config_freshness.json()["status"] == "stale"
        assert config_freshness.json()["room_advice_currentness"] == "stale"
    finally:
        with engine.begin() as connection:
            connection.execute(update(hotels).where(hotels.c.hotel_id == "HTL-CITY01")
                               .values(config_version=initial_config_version))


    call_two_brief = provider.calls[1]["committed_guest_brief"]
    assert call_two_brief["party"]["adults"] == 2
    assert call_two_brief["dates"] == {
        "check_in": "2026-11-01", "check_out": "2026-11-04", "nights": 3,
    }
    result_id = advice["result_id"]
    option_id = advice["options"][0]["option_id"]
    selection = client.post(
        f"/v1/guest/sessions/{session['session_id']}/room-advice/{result_id}/selection",
        headers=headers, json={"result_version": advice["result_version"], "option_id": option_id},
    )
    assert selection.status_code == 200, selection.text
    assert selection.json()["option_id"] == option_id
    selected_read = client.get(
        f"/v1/guest/sessions/{session['session_id']}/room-advice", headers=headers,
    )
    assert selected_read.status_code == 200, selected_read.text
    assert selected_read.json()["selection"]["option_id"] == option_id

    language_only = client.post(endpoint, headers=headers, json={
        "request_id": str(uuid.uuid4()),
        "question": "Please show the same room suggestion in French.",
    })
    assert language_only.status_code == 200, language_only.text
    relocalized = language_only.json()["room_advice"]
    assert len(provider.calls) == 4, provider.calls
    assert relocalized["result_id"] == result_id
    assert relocalized["result_version"] == advice["result_version"]
    assert relocalized["options"][0]["rooms"] == advice["options"][0]["rooms"]
    assert relocalized["options"][0]["assignments"] == advice["options"][0]["assignments"]
    assert relocalized["options"][0]["checks"] == advice["options"][0]["checks"]
    assert relocalized["options"][0]["cost"] == advice["options"][0]["cost"]
    assert relocalized["options"][0]["rationale"][0]["fact_ids"] == advice["options"][0]["rationale"][0]["fact_ids"]
    assert relocalized["selection"]["option_id"] == option_id
    assert relocalized["options"][0]["rationale"][0]["locale"] == "fr"
    assert language_only.json()["trace"]["calls"] == len(provider.calls) - 2

    latest_read = client.get(
        f"/v1/guest/sessions/{session['session_id']}/room-advice", headers=headers,
    )
    assert latest_read.status_code == 200, latest_read.text
    assert latest_read.json()["options"][0]["rationale"][0]["text"] == (
        "Estimation indicative du tarif pour le séjour : 5400000 VND."
    )
    assert latest_read.json()["result_version"] == advice["result_version"]
    assert latest_read.json()["options"][0]["cost"] == advice["options"][0]["cost"]

    replay = client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations", headers=headers,
        json={"request_id": confirm_id, "confirmation_token": challenge["brief_confirmation"]["token"]},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["room_advice"]["result_id"] == result_id
    assert replay.json()["room_advice"]["options"][0]["rationale"][0]["locale"] == "fr"
    assert len(provider.calls) == 4

    source_ref = advice["source_refs"][0]
    source_id = source_ref.get("source_id") or source_ref["source"]["source_id"]
    with engine.begin() as connection:
        connection.execute(update(knowledge_sources).where(
            knowledge_sources.c.hotel_id == "HTL-CITY01",
            knowledge_sources.c.source_id == source_id,
        ).values(lifecycle_status="revoked"))
    try:
        stale_replay = client.post(
            f"/v1/guest/sessions/{session['session_id']}/brief-confirmations", headers=headers,
            json={"request_id": confirm_id, "confirmation_token": challenge["brief_confirmation"]["token"]},
        )
        assert stale_replay.status_code == 200, stale_replay.text
        assert stale_replay.json()["room_advice"]["currentness"] == "stale"
        assert stale_replay.json()["room_advice"]["selection"] is None
        assert stale_replay.json()["answer_eligibility"] == "stale"
        source_freshness = client.post(
            freshness_endpoint, headers=headers, json={"request_id": confirm_id},
        )
        assert source_freshness.status_code == 200, source_freshness.text
        assert source_freshness.json()["room_advice_currentness"] == "stale"
        assert source_freshness.json()["status"] == "stale"
        assert len(provider.calls) == 4
    finally:
        with engine.begin() as connection:
            connection.execute(update(knowledge_sources).where(
                knowledge_sources.c.hotel_id == "HTL-CITY01",
                knowledge_sources.c.source_id == source_id,
            ).values(lifecycle_status="approved"))

    second_question = "Add one more night; checkout is 2026-11-05. Recheck rooms."
    second_prepared = client.post(endpoint, headers=headers, json={
        "request_id": str(uuid.uuid4()), "question": second_question,
    })
    assert second_prepared.status_code == 200, second_prepared.text
    assert second_prepared.json()["confirmation_required"] is True
    second_confirm_id = str(uuid.uuid4())
    second = client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations", headers=headers,
        json={"request_id": second_confirm_id,
              "confirmation_token": second_prepared.json()["brief_confirmation"]["token"]},
    )
    assert second.status_code == 200, second.text
    updated_advice = second.json()["room_advice"]
    assert len(provider.calls) == 6
    assert updated_advice["brief_version"] == advice["brief_version"] + 1
    assert updated_advice["options"][0]["cost"]["total"] == 7_200_000
    assert updated_advice["currentness"] == "current"
    superseded_freshness = client.post(
        freshness_endpoint, headers=headers, json={"request_id": confirm_id},
    )
    assert superseded_freshness.status_code == 200, superseded_freshness.text
    assert superseded_freshness.json()["room_advice_currentness"] == "stale"
    assert superseded_freshness.json()["status"] == "stale"
    old_result = get_room_advice_result(
        engine, session_id=session["session_id"], hotel_id="HTL-CITY01", result_id=result_id,
    )
    assert old_result["currentness"] == "stale"
    assert old_result["selection"] is None


def test_pine_accessibility_clear_age_update_reaches_french_persisted_advice(engine) -> None:
    provider = PineAgeAndAccessibilityProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-seven-pine-clear-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "pine-ridge-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}/messages"

    first_question = (
        "I am one adult with my seven-year-old; I am the guardian and we may share a bed. "
        "Check in 2026-11-10, check out 2026-11-12. "
        "We require step-free entry and wheelchair-accessible bathroom. Please recommend a room."
    )
    first = client.post(endpoint, headers=headers, json={
        "request_id": str(uuid.uuid4()), "question": first_question,
    })
    assert first.status_code == 200, first.text
    first_challenge = first.json()
    assert first_challenge["confirmation_required"] is True
    assert first_challenge["trace"]["calls"] == 1
    assert first_challenge["trace"]["preparation_calls"] == 1
    assert first_challenge["trace"]["provider_request_ids"]
    first_confirm_id = str(uuid.uuid4())
    first_confirm = client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations", headers=headers,
        json={"request_id": first_confirm_id,
              "confirmation_token": first_challenge["brief_confirmation"]["token"]},
    )
    assert first_confirm.status_code == 200, first_confirm.text
    assert first_confirm.json()["trace"]["calls"] == 2
    assert first_confirm.json()["trace"]["preparation_calls"] == 1
    assert first_confirm.json()["room_advice"]["status"] == "needs_clarification"
    saved = get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-RETREAT03")
    child_id = saved.data["party"]["children"][0]["member_id"]
    provider.child_id = child_id
    assert saved.data["party"]["children"][0]["age"] == 7
    assert saved.data["room_requirements"]["hard_accessibility_needs"] == [
        "step-free entry", "wheelchair-accessible bathroom",
    ]

    second_question = (
        "Please change my saved child's age to 8 and remove the step-free entry and wheelchair "
        "bathroom requirements. Keep the same guardian and dates. Recommend a room in French."
    )
    second = client.post(endpoint, headers=headers, json={
        "request_id": str(uuid.uuid4()), "question": second_question,
    })
    assert second.status_code == 200, second.text
    second_challenge = second.json()
    assert second_challenge["confirmation_required"] is True
    second_confirm = client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations", headers=headers,
        json={"request_id": str(uuid.uuid4()),
              "confirmation_token": second_challenge["brief_confirmation"]["token"]},
    )
    assert second_confirm.status_code == 200, second_confirm.text
    response = second_confirm.json()
    advice = response["room_advice"]
    assert advice["status"] in {"ready", "partial"}, advice.get("explanation_inputs")
    assert advice["options"][0]["rooms"][0]["room_type_id"] == "PINE-LOFT"
    assert advice["options"][0]["cost"]["nightly_subtotal"] == 2_200_000
    assert any(item["amount"] == 4_400_000 and item["status"] == "known"
               for item in advice["options"][0]["cost"]["breakdown"])
    assert advice["options"][0]["cost"]["total"] is None
    assert advice["options"][0]["cost"]["status"] == "incomplete"
    assert advice["options"][0]["rationale"][0]["locale"] == "fr", response.get("language_preference")
    assert advice["options"][0]["rationale"][0]["locale_fallback"] is False
    assert "Cette configuration" in advice["options"][0]["rationale"][0]["text"]

    def enum_values(node):
        if isinstance(node, dict):
            if "enum" in node:
                yield node["enum"]
            for child in node.values():
                yield from enum_values(child)
        elif isinstance(node, list):
            for child in node:
                yield from enum_values(child)

    context_clear_enums = [values for values in enum_values(provider.schemas[2] or {})
                           if "hard_accessibility_needs" in values]
    assert context_clear_enums == [["hard_accessibility_needs"]]
    current = get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-RETREAT03")
    assert current.data["party"]["children"][0]["member_id"] == child_id
    assert current.data["party"]["children"][0]["age"] == 8
    assert current.data["party"]["guardians"][child_id] == "adult-1"
    assert (current.data.get("room_requirements") or {}).get("hard_accessibility_needs") is None

    persisted = get_room_advice_result(
        engine, session_id=session["session_id"], hotel_id="HTL-RETREAT03",
        result_id=advice["result_id"],
    )
    assert persisted["currentness"] == "current"
    assert persisted["payload"]["options"][0]["cost"] == advice["options"][0]["cost"]
    assert persisted["payload"]["options"][0]["rationale"][0]["locale"] == "fr"
    assert len(provider.calls) == 4


def test_unknown_new_child_sharing_id_fails_as_model_output_without_brief_mutation(engine) -> None:
    provider = UnknownChildSharingProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-seven-unknown-child-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    request_id = str(uuid.uuid4())
    question = "I am one adult and guardian. Our seven-year-old may share my bed."
    response = client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": request_id, "question": question},
    )

    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "invalid_model_output"
    assert provider.calls
    assert provider.schemas[0] is not None
    patch = provider.schemas[0]["properties"]["response"]["properties"]["guest_patch"]
    operations = patch["anyOf"][0]["properties"]["ops"]["items"]["anyOf"]
    operations = [variant for item in operations for variant in item.get("anyOf", (item,))]
    sharing = next(item for item in operations
                   if item["properties"]["op"].get("enum") == ["set_bed_sharing"])
    assert "child-1" not in sharing["properties"]["member_ids"]["items"]["enum"]

    brief = get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-CITY01")
    assert brief.brief_version == 0
    assert brief.data["party"].get("children", []) == []
    assert get_guest_brief_receipt(
        engine, session_id=session["session_id"], hotel_id="HTL-CITY01", receipt_id=request_id,
    ) is None


def test_messages_preserves_grounded_faq_with_room_advice_in_two_provider_calls(engine) -> None:
    provider = MixedHotelAnswerRoomAdviceProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-seven-mixed-room-advice-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    response = client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={
            "request_id": str(uuid.uuid4()),
            "question": "What is the hotel name? Two adults, we can share a queen bed, "
                        "check in 2026-11-01 and check out 2026-11-04. Recommend a room.",
        },
    )
    assert response.status_code == 200, response.text
    challenge = response.json()
    assert challenge["confirmation_required"] is True
    assert challenge["trace"]["calls"] == challenge["trace"]["preparation_calls"] == 1
    confirmed = _confirm(client, session, challenge, str(uuid.uuid4()))
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert len(provider.calls) == body["trace"]["calls"] == 2
    assert body["answer"] == "The hotel is Harbor City Demo [F-HTL-CITY01-001]."
    assert [item["fact_id"] for item in body["evidence"]] == ["F-HTL-CITY01-001"]
    advice = body["room_advice"]
    assert advice["status"] == "ready"
    assert advice["options"][0]["rooms"][0]["room_type_id"] == "CITY-STD"
    assert advice["options"][0]["cost"]["total"] == 5_400_000
    assert advice["source_refs"]
