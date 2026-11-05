"""B15 API-to-processor checks against a fresh isolated PostgreSQL database.

The offline provider emits controlled raw model-shaped claims. It never chooses
or reports verifier verdicts; the production B15 guard under test does that.
The companion local-browser run exercises the same factory through Next.js.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, inspect, select

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations,
    get_active_snapshot,
    get_room_advice_result,
    hotels,
    knowledge_facts,
    knowledge_media,
    knowledge_sources,
    replace_source_snapshot,
    requests,
    transition_source,
)
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import (
    import_fixture_pack,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    Usage,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "hospitality" / "knowledge-v1"
TEST_DSN = os.environ.get("B15_TEST_DATABASE_URL", "")
_API_DSN = os.environ.get("B15_BROWSER_DATABASE_URL", "")
_HOTEL = "HTL-CITY01"
_PARKING_ID = "F-HTL-CITY01-046"
_DEPOSIT_ID = "F-HTL-CITY01-013"
_WIFI_ID = "F-HTL-CITY01-021"
_TEST_DATABASE_NAMES = {
    "staylead_s20_b15_test",
    "staylead_s20_b15_test_r2",
    "staylead_s20_b15_test_r3",
    "staylead_s20_b15_test_r4",
}
_BROWSER_DATABASE_NAMES = {"staylead_s20_b15_browser", "staylead_s20_b15_browser_r2"}


def _require_private_dsn(value: str, allowed_names: set[str]) -> None:
    parsed = urlsplit(value.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path.removeprefix("/") not in allowed_names:
        raise RuntimeError("B15 requires a named private local PostgreSQL database.")


class OfflineB15Provider:
    """Returns deterministic raw claims that the application must actually check."""

    def __init__(self) -> None:
        self.calls = 0
        self.inputs: list[dict[str, object]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append({**payload, "instructions": request.instructions})
        question = str(payload.get("question", ""))
        folded = question.casefold()
        wants_edit = "change my party" in folded or "set my party" in folded
        if "candidate_index" in payload:
            candidates = payload.get("candidate_index", [])
            fact_ids = [str(item["fact_id"]) for item in candidates
                        if item.get("fact_id") in {_PARKING_ID, _DEPOSIT_ID, _WIFI_ID}]
            output: dict[str, object] = {
                "fact_ids": fact_ids,
                "turn_intents": ["hotel_information", "guest_edit"] if wants_edit else ["hotel_information"],
            }
            if wants_edit:
                output["guest_patch"] = {"ops": [{
                    "op": "set_adults", "count": 2, "current_turn_quote": "two adults",
                }]}
        else:
            facts = payload.get("facts", [])
            fact_ids = [str(item["fact_id"]) for item in facts
                        if item.get("fact_id") in {_PARKING_ID, _DEPOSIT_ID, _WIFI_ID}]
            parking = _PARKING_ID in fact_ids
            if _DEPOSIT_ID in fact_ids and "unconditionally refundable" in folded:
                claims = ([{
                    "text": "The deposit is 500000 VND per room per stay and is unconditionally refundable",
                    "fact_ids": [_DEPOSIT_ID],
                }])
                unknowns = []
            elif "wi-fi" in folded or "wifi" in folded:
                claims = ([{"text": "Wi-Fi is free in guest areas", "fact_ids": [_WIFI_ID]}]
                          if _WIFI_ID in fact_ids else [])
                unknowns = [] if claims else ["Wi-Fi details are not in the current records."]
            elif "underground" in folded:
                claims = ([{"text": "Parking is underground", "fact_ids": [_PARKING_ID]}]
                          if parking else [])
                unknowns: list[str] = [] if parking else ["Parking details are not in the current records."]
            elif "free" in folded:
                claims = ([
                    {"text": "Parking is free", "fact_ids": [_PARKING_ID]},
                    {"text": "The parking area is covered", "fact_ids": [_PARKING_ID]},
                ] if parking else [])
                unknowns = [] if parking else ["Parking details are not in the current records."]
            else:
                claims = ([{
                    "text": "Parking is covered and costs 100000 VND per vehicle per night",
                    "fact_ids": [_PARKING_ID],
                }] if parking else [])
                unknowns = [] if parking else ["Parking details are not in the current records."]
            output = {
                "supported_claims": claims,
                "unknowns": unknowns,
                "conflicts": [],
                "turn_intents": ["hotel_information", "guest_edit"] if wants_edit else ["hotel_information"],
            }
        return GenerationResult(
            text=json.dumps(output, ensure_ascii=False),
            provider="offline-b15-consumer", deployment="private-test-only", model="controlled-stub",
            request_id=f"b15-offline-{self.calls}",
            usage=Usage(input_tokens=5, output_tokens=7, total_tokens=12),
        )


class Round4ConsumerProvider:
    """Controlled raw claims for Q1-Q4 consumer regressions; no verifier verdicts."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.calls = 0
        self.inputs: list[dict[str, object]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append({**payload, "instructions": request.instructions})
        question = str(payload.get("question", payload.get("current_question", "")))
        if "candidate_index" in payload:
            candidates = payload.get("candidate_index", [])
            wanted_ids = {
                "m4_q1": {_PARKING_ID, _DEPOSIT_ID},
                "m4_projection": {_PARKING_ID},
                "m4_wrong_amount": {_PARKING_ID},
                "m3_wrong_amount": {_PARKING_ID},
                "m3_accessibility": {"F-HTL-CITY01-069"},
                "m3_edit_currentness": {_PARKING_ID},
            }.get(self.scenario, {_WIFI_ID})
            selected = [str(item["fact_id"]) for item in candidates
                        if isinstance(item, dict) and item.get("fact_id") in wanted_ids]
            wants_edit = "change my party" in question.casefold() or "set my party" in question.casefold()
            if self.scenario == "m4_projection" and wants_edit:
                intents = ["hotel_information", "guest_edit", "room_advice"]
            elif self.scenario.startswith("m4_"):
                intents = ["hotel_information", "room_advice"]
            elif self.scenario == "m3_edit_currentness" and wants_edit:
                intents = ["hotel_information", "guest_edit"]
            else:
                intents = ["hotel_information"]
            response: dict[str, object] = {
                "fact_ids": selected,
                "turn_intents": intents,
            }
            if self.scenario == "m3_edit_currentness" and wants_edit:
                response["guest_patch"] = {"ops": [{
                    "op": "set_adults", "count": 2, "current_turn_quote": "two adults",
                }]}
                response["explicit_language_tag"] = None
                response["inferred_language_tag"] = None
            if self.scenario == "m4_projection" and wants_edit:
                response["guest_patch"] = {"ops": [
                    {"op": "set_dates", "check_in": "2026-11-10", "check_out": "2026-11-11",
                     "current_turn_quote": "check in 2026-11-10 and check out 2026-11-11"},
                    {"op": "set_adults", "count": 2, "current_turn_quote": "two adults"},
                ]}
        elif "hotel_information_facts" in payload:
            selected_ids = {str(item["fact_id"]) for item in payload["hotel_information_facts"]}
            claims: list[dict[str, object]] = []
            if self.scenario == "m4_q1" and {_PARKING_ID, _DEPOSIT_ID} <= selected_ids:
                claims = [{
                    "text": "Parking is covered. The deposit is unconditionally refundable.",
                    "fact_ids": [_PARKING_ID, _DEPOSIT_ID],
                }]
            elif self.scenario == "m4_projection" and _PARKING_ID in selected_ids:
                claims = [{"text": "Parking is free.", "fact_ids": [_PARKING_ID]}]
            elif self.scenario == "m4_wrong_amount" and _PARKING_ID in selected_ids:
                claims = [
                    {"text": "Parking costs 120000 VND per vehicle per night.", "fact_ids": [_PARKING_ID]},
                    {"text": "The parking area is covered.", "fact_ids": [_PARKING_ID]},
                ]
            hotel_answer = {
                "supported_claims": claims,
                "unknowns": [] if claims else ["The current records do not confirm this detail."],
                "conflicts": [],
            }
            room_facts = payload.get("guest_facts", [])
            twin_room = next((item for item in room_facts if item.get("field") == "room_type"
                              and item.get("value", {}).get("room_type_id") == "CITY-TWN"), None)
            twin_rate = next((item for item in room_facts if item.get("field") == "reference_rate"
                              and item.get("value", {}).get("room_type_id") == "CITY-TWN"), None)
            brief = payload.get("committed_guest_brief", {})
            adults = int((brief.get("party") or {}).get("adults") or 0)
            dates = brief.get("dates") or {}
            options: list[dict[str, object]] = []
            questions: list[dict[str, str]] = [{"field": "party.adults"}]
            if twin_room and twin_rate and adults == 2 and dates.get("check_in"):
                options = [{
                    "option_id": f"b15-round4-twin-{self.calls}",
                    "rooms": [{"room_index": 0, "room_type_id": "CITY-TWN"}],
                    "assignments": [
                        {"member_id": f"adult-{index + 1}", "room_index": 0,
                         "bed_index": index, "bed_type": "single"}
                        for index in range(adults)
                    ],
                    "rationale": [{"claim_code": "reference_price", "fact_ids": [twin_rate["fact_id"]]}],
                }]
                questions = []
            response = {
                "options": options,
                "questions": questions,
                "hotel_answer": hotel_answer,
            }
        else:
            facts = payload.get("facts", [])
            available = {str(item["fact_id"]) for item in facts
                         if isinstance(item, dict) and item.get("fact_id")}
            if self.scenario == "m3_wrong_amount" and _PARKING_ID in available:
                claims = [
                    {"text": "Parking costs 120000 VND per vehicle per night.", "fact_ids": [_PARKING_ID]},
                    {"text": "The parking area is covered.", "fact_ids": [_PARKING_ID]},
                ]
            elif self.scenario == "m3_accessibility" and "F-HTL-CITY01-069" in available:
                claims = [{
                    "text": "Accessible rooms are definitely available.",
                    "fact_ids": ["F-HTL-CITY01-069"],
                }]
            elif self.scenario == "m3_edit_currentness" and _PARKING_ID in available:
                claims = ([
                    {"text": "Parking is free.", "fact_ids": [_PARKING_ID]},
                    {"text": "The parking area is covered.", "fact_ids": [_PARKING_ID]},
                ] if "free" in question.casefold() else [{
                    "text": "Parking is covered.", "fact_ids": [_PARKING_ID],
                }])
            elif _WIFI_ID in available:
                claims = [{"text": "Wi-Fi is free in guest areas.", "fact_ids": [_WIFI_ID]}]
            else:
                claims = []
            response = {
                "supported_claims": claims,
                "unknowns": [] if claims else ["Current records do not confirm these details."],
                "conflicts": [],
            }
            preparation_enabled = payload.get("guest_brief_patch_enabled") is True
            if preparation_enabled:
                wants_edit = "change my party" in question.casefold() or "set my party" in question.casefold()
                response.update({
                    "turn_intents": ["hotel_information", "guest_edit"] if wants_edit else ["hotel_information"],
                    "guest_patch": ({"ops": [{
                        "op": "set_adults", "count": 2, "current_turn_quote": "two adults",
                    }]} if wants_edit else None),
                    "explicit_language_tag": None,
                    "inferred_language_tag": None,
                    "guest_claims": [],
                    "guest_clarification": None,
                    "conversational_acknowledgement": None,
                    "guest_brief_refs": [],
                    "label_bundle": {},
                })
        return GenerationResult(
            text=json.dumps(response, ensure_ascii=False),
            provider="offline-b15-round4", deployment="private-test-only", model="controlled-stub",
            request_id=f"b15-round4-{self.calls}",
            usage=Usage(input_tokens=5, output_tokens=7, total_tokens=12),
        )


def _settings(dsn: str, secret: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=dsn,
        ai_provider="disabled",
        session_signing_secret=SecretStr(secret),
    )


def create_b15_test_app():
    """Uvicorn factory for the owned browser harness; import only on an empty DB."""
    if os.environ.get("B15_TEST_ONLY") != "1" or not _API_DSN:
        raise RuntimeError("Set B15_TEST_ONLY=1 and B15_BROWSER_DATABASE_URL for the private B15 app.")
    _require_private_dsn(_API_DSN, _BROWSER_DATABASE_NAMES)
    secret = os.environ.get("B15_SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("B15_SESSION_SECRET must be an ephemeral local test signing key.")
    engine = create_database_engine(_API_DSN)
    apply_migrations(engine)
    with engine.connect() as connection:
        hotel_exists = connection.execute(select(hotels.c.hotel_id).where(hotels.c.hotel_id == _HOTEL)).first()
    if hotel_exists is None:
        with engine.connect() as connection:
            hotel_count = connection.scalar(select(func.count()).select_from(hotels))
        if hotel_count:
            raise RuntimeError("Refusing to seed a non-empty B15 browser database without Harbor City Demo.")
        if os.environ.get("B15_IMPORT_FIXTURE_ONCE") != "1":
            raise RuntimeError("Refusing to seed a B15 browser database without explicit one-time bootstrap flag.")
        import_fixture_pack(engine, FIXTURE_ROOT)
    scenario = os.environ.get("B15_BROWSER_SCENARIO", "")
    provider = Round4ConsumerProvider(scenario) if scenario else OfflineB15Provider()
    return create_app(_settings(_API_DSN, secret), engine=engine, provider=provider)


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set B15_TEST_DATABASE_URL to a fresh isolated Sprint 20 PostgreSQL database.")
    _require_private_dsn(TEST_DSN, _TEST_DATABASE_NAMES)
    database = create_database_engine(TEST_DSN)
    if inspect(database).get_table_names():
        raise RuntimeError("B15 test database is not fresh; refusing to migrate or reseed it.")
    apply_migrations(database)
    import_fixture_pack(database, FIXTURE_ROOT)
    yield database
    database.dispose()


def _client(engine, provider: OfflineB15Provider):
    client = TestClient(create_app(
        _settings(TEST_DSN, "b15-test-only-session-signing-secret"),
        engine=engine,
        provider=provider,
    ))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    return client, opened.json()


def _post(client: TestClient, session: dict[str, object], question: str, *, request_id: str | None = None):
    return client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages",
        json={"request_id": request_id or str(uuid4()), "question": question},
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )


def _confirm(
    client: TestClient, session: dict[str, object], challenge: dict[str, object],
    request_id: str | None = None,
):
    body = challenge["brief_confirmation"]
    return client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": request_id or str(uuid4()), "confirmation_token": body["token"]},
    )


def _assert_provider_call_bound(
    engine, provider: OfflineB15Provider | Round4ConsumerProvider,
    calls_before: int, response_body: dict[str, object],
) -> None:
    execution = response_body["trace"]["execution"]
    provider_events = [event for event in execution["events"] if event.get("stage") == "provider"]
    observed = provider.calls - calls_before
    assert observed <= 2
    assert len(provider_events) == observed
    with engine.connect() as connection:
        persisted = connection.execute(
            select(requests.c.provider_calls).where(requests.c.request_id == execution["request_id"])
        ).scalar_one()
    assert persisted == observed


def _provider_fact_ids(provider: OfflineB15Provider) -> set[str]:
    return {
        str(item["fact_id"])
        for payload in provider.inputs
        for item in payload.get("facts", [])
        if isinstance(item, dict) and item.get("fact_id")
    }


def test_plain_faq_and_mixed_faq_keep_only_supported_claims(engine) -> None:
    provider = OfflineB15Provider()
    client, session = _client(engine, provider)

    calls_before = provider.calls
    ordinary = _post(client, session, "Is parking covered and what does it cost?")
    assert ordinary.status_code == 200, ordinary.text
    valid = ordinary.json()
    assert "covered" in valid["answer"].casefold()
    assert "100000 VND" in valid["answer"]
    assert _PARKING_ID in {item["fact_id"] for item in valid["evidence"]}
    _assert_provider_call_bound(engine, provider, calls_before, valid)

    calls_before = provider.calls
    underground = _post(client, session, "Is the parking underground?")
    assert underground.status_code == 200, underground.text
    unknown = underground.json()
    assert "Parking is underground" not in unknown["answer"]
    assert unknown["unknowns"]
    _assert_provider_call_bound(engine, provider, calls_before, unknown)

    calls_before = provider.calls
    refund_question = _post(client, session, "Is the deposit unconditionally refundable?")
    assert refund_question.status_code == 200, refund_question.text
    refund_answer = refund_question.json()
    assert "unconditionally refundable" not in refund_answer["answer"].casefold()
    assert refund_answer["unknowns"]
    _assert_provider_call_bound(engine, provider, calls_before, refund_answer)

    mixed_question = "Please change my party to two adults, and is parking free?"
    calls_before = provider.calls
    proposal = _post(client, session, mixed_question)
    assert proposal.status_code == 200, proposal.text
    challenge = proposal.json()
    assert challenge["confirmation_required"] is True
    assert challenge["guest_brief"]["brief_version"] == 0
    _assert_provider_call_bound(engine, provider, calls_before, challenge)
    calls_before = provider.calls
    confirmed = _confirm(client, session, challenge)
    assert confirmed.status_code == 200, confirmed.text
    mixed = confirmed.json()
    assert mixed["guest_brief"]["brief_version"] == 1
    assert "Parking is free" not in mixed["answer"]
    assert "covered" in mixed["answer"].casefold()
    assert mixed["unknowns"]
    _assert_provider_call_bound(engine, provider, calls_before, mixed)


def test_ordinary_wifi_faq_keeps_grounded_positive_outside_parking_and_deposit(engine) -> None:
    provider = OfflineB15Provider()
    client, session = _client(engine, provider)

    calls_before = provider.calls
    response = _post(client, session, "Is Wi-Fi free in guest areas?")
    assert response.status_code == 200, response.text
    assert _WIFI_ID in _provider_fact_ids(provider), "the offline answer request must receive the existing F021 source fact"
    answer = response.json()
    assert "free" in answer["answer"].casefold()
    assert _WIFI_ID in {item["fact_id"] for item in answer["evidence"]}
    _assert_provider_call_bound(engine, provider, calls_before, answer)


def _round4_fact_ids_in_source_refs(source_refs: list[dict[str, object]]) -> set[str]:
    fact_ids: set[str] = set()
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        fact_ids.update(str(item) for item in ref.get("fact_ids", ()) if item)
        fact_id = ref.get("fact_id")
        if fact_id:
            fact_ids.add(str(fact_id))
    return fact_ids


def _round4_source_versions(source_refs: list[dict[str, object]], fact_id: str) -> set[str]:
    versions: set[str] = set()
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        if fact_id not in {str(item) for item in ref.get("fact_ids", ())} and ref.get("fact_id") != fact_id:
            continue
        source = ref.get("source") if isinstance(ref.get("source"), dict) else ref
        version = source.get("source_version", source.get("version"))
        if version is not None:
            versions.add(str(version))
    return versions


def _round4_mixed_turn(engine, client, session, question: str, provider: Round4ConsumerProvider):
    calls_before = provider.calls
    response = _post(client, session, question)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "room_advice" in body
    _assert_provider_call_bound(engine, provider, calls_before, body)
    return body


def test_round4_m3_typed_accessibility_unknown_keeps_wifi_positive(engine) -> None:
    provider = Round4ConsumerProvider("m3_accessibility")
    client, session = _client(engine, provider)

    calls_before = provider.calls
    accessibility = _post(client, session, "Are accessible rooms definitely available?")
    assert accessibility.status_code == 200, accessibility.text
    answer = accessibility.json()
    assert "definitely available" not in answer["answer"].casefold()
    assert answer["unknowns"]
    assert any(
        item.get("fact_id") == "F-HTL-CITY01-069"
        for payload in provider.inputs for item in payload.get("facts", [])
        if isinstance(item, dict)
    )
    _assert_provider_call_bound(engine, provider, calls_before, answer)

    provider.scenario = "wifi"
    calls_before = provider.calls
    wifi = _post(client, session, "Is Wi-Fi free in guest areas?")
    assert wifi.status_code == 200, wifi.text
    wifi_answer = wifi.json()
    assert "free" in wifi_answer["answer"].casefold()
    assert _WIFI_ID in {item["fact_id"] for item in wifi_answer["evidence"]}
    _assert_provider_call_bound(engine, provider, calls_before, wifi_answer)


def test_round4_m3_unsupported_amount_keeps_covered_sibling(engine) -> None:
    provider = Round4ConsumerProvider("m3_wrong_amount")
    client, session = _client(engine, provider)

    calls_before = provider.calls
    response = _post(client, session, "What does parking cost, and is the area covered?")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "120000" not in body["answer"]
    assert "covered" in body["answer"].casefold()
    assert _PARKING_ID in {item["fact_id"] for item in body["evidence"]}
    _assert_provider_call_bound(engine, provider, calls_before, body)


def test_round5_m3_mixed_confirmation_answer_uses_prepared_turn_scope(engine) -> None:
    provider = Round4ConsumerProvider("m3_edit_currentness")
    client, session = _client(engine, provider)
    question = "Please change my party to two adults, and is parking free?"

    calls_before = provider.calls
    challenge_response = _post(client, session, question)
    assert challenge_response.status_code == 200, challenge_response.text
    challenge = challenge_response.json()
    assert challenge["confirmation_required"] is True
    assert challenge["guest_brief"]["brief_version"] == 0
    _assert_provider_call_bound(engine, provider, calls_before, challenge)

    calls_before = provider.calls
    confirmation = _confirm(client, session, challenge)
    assert confirmation.status_code == 200, confirmation.text
    body = confirmation.json()
    assert body["guest_brief"]["brief_version"] == 1
    assert body["guest_brief"]["party"]["adults"] == 2
    assert "Parking is free" not in body["answer"]
    assert "covered" in body["answer"].casefold()
    assert body["unknowns"]
    assert _PARKING_ID in {item["fact_id"] for item in body["evidence"]}
    _assert_provider_call_bound(engine, provider, calls_before, body)


def test_round4_m4_claim_binding_and_unsupported_amount_keep_only_verified_sibling(engine) -> None:
    provider = Round4ConsumerProvider("m4_q1")
    client, session = _client(engine, provider)
    compound = _round4_mixed_turn(
        engine, client, session,
        "Recommend a room, and tell me whether parking is covered and the deposit is refundable.",
        provider,
    )
    faq = compound["room_advice"]["hotel_answer"]
    covered = [claim for claim in faq["supported_claims"] if "covered" in claim["text"].casefold()]
    assert covered, faq
    assert all(claim["fact_ids"] == [_PARKING_ID] for claim in covered)
    assert "unconditionally refundable" not in " ".join(
        claim["text"] for claim in faq["supported_claims"]
    ).casefold()
    assert faq["unknowns"]
    aggregate_ids = _round4_fact_ids_in_source_refs(
        compound["room_advice"].get("source_refs", []),
    )
    if _DEPOSIT_ID in aggregate_ids:
        assert "deposit" in " ".join(faq["unknowns"]).casefold()

    provider.scenario = "m4_wrong_amount"
    mixed_amount = _round4_mixed_turn(
        engine, client, session,
        "Recommend a room, and tell me the parking price and whether the area is covered.",
        provider,
    )
    amount_faq = mixed_amount["room_advice"]["hotel_answer"]
    assert "120000" not in json.dumps(amount_faq, ensure_ascii=False)
    amount_covered = [claim for claim in amount_faq["supported_claims"]
                      if "covered" in claim["text"].casefold()]
    assert amount_covered, amount_faq
    assert all(claim["fact_ids"] == [_PARKING_ID] for claim in amount_covered)


def test_round4_m4_projection_binding_currentness_replay_and_revoke(engine) -> None:
    provider = Round4ConsumerProvider("m4_projection")
    client, session = _client(engine, provider)
    challenge_id = str(uuid4())
    calls_before = provider.calls
    challenge_response = _post(
        client, session,
        "Please change my party to two adults, check in 2026-11-10 and check out 2026-11-11. "
        "Recommend a room, and is parking free?",
        request_id=challenge_id,
    )
    assert challenge_response.status_code == 200, challenge_response.text
    challenge = challenge_response.json()
    assert challenge["confirmation_required"] is True
    assert "room_advice" not in challenge
    _assert_provider_call_bound(engine, provider, calls_before, challenge)

    request_id = str(uuid4())
    calls_before = provider.calls
    confirmation = _confirm(client, session, challenge, request_id=request_id)
    assert confirmation.status_code == 200, confirmation.text
    body = confirmation.json()
    assert body["guest_brief"]["brief_version"] == 1
    _assert_provider_call_bound(engine, provider, calls_before, body)
    advice = body["room_advice"]
    faq = advice["hotel_answer"]
    assert not faq["supported_claims"]
    assert faq["unknowns"]
    assert "100000" in " ".join(faq["unknowns"])
    assert _PARKING_ID in _round4_fact_ids_in_source_refs(advice.get("source_refs", []))
    assert advice["options"]
    assert advice["options"][0]["rooms"][0]["room_type_id"] == "CITY-TWN"
    option_fact_ids = {
        fact_id
        for option in advice["options"]
        for rationale in option.get("rationale", [])
        for fact_id in rationale.get("fact_ids", [])
    }
    assert _PARKING_ID not in option_fact_ids

    freshness_url = f"/v1/guest/sessions/{session['session_id']}/freshness"
    auth = {"Authorization": f"Bearer {session['access_token']}"}
    current = client.post(freshness_url, json={"request_id": request_id}, headers=auth)
    assert current.status_code == 200, current.text
    assert current.json()["status"] == "current"
    persisted = get_room_advice_result(
        engine, session_id=session["session_id"], hotel_id=_HOTEL, result_id=advice["result_id"],
    )
    assert persisted is not None and persisted["currentness"] == "current"
    assert _PARKING_ID in _round4_fact_ids_in_source_refs(persisted["source_refs"])

    snapshot = get_active_snapshot(engine, _HOTEL)
    parking_source = next(item for item in snapshot.sources if item.source_id == "SRC-HTL-CITY01-TRANSPORT")
    versioned = replace_source_snapshot(
        engine, hotel_id=_HOTEL, source_id=parking_source.source_id,
        expected_generation=snapshot.generation, expected_version=parking_source.source_version,
        expected_source_hash=parking_source.source_hash, operation_id=f"b15-r4-version-{uuid4().hex}",
        pack=_replacement_pack(engine, parking_source.source_id, "2.0"),
    )
    assert versioned["status"] == "applied"
    stale = client.post(freshness_url, json={"request_id": request_id}, headers=auth)
    assert stale.status_code == 200, stale.text
    assert stale.json()["status"] == "stale"
    old_record = get_room_advice_result(
        engine, session_id=session["session_id"], hotel_id=_HOTEL, result_id=advice["result_id"],
    )
    assert old_record is not None and old_record["currentness"] == "stale"
    assert _PARKING_ID in _round4_fact_ids_in_source_refs(old_record["source_refs"])

    replay = _confirm(client, session, challenge, request_id=request_id)
    assert replay.status_code in {200, 409}, replay.text
    if replay.status_code == 200:
        replay_advice = replay.json().get("room_advice")
        assert replay_advice is None or replay_advice.get("currentness") == "stale"

    followup_id = str(uuid4())
    calls_before = provider.calls
    followup = _post(
        client, session, "Recommend a room, and what does parking cost?", request_id=followup_id,
    )
    assert followup.status_code == 200, followup.text
    followup_body = followup.json()
    followup_advice = followup_body["room_advice"]
    assert _PARKING_ID in _round4_fact_ids_in_source_refs(followup_advice.get("source_refs", []))
    assert "2.0" in _round4_source_versions(followup_advice.get("source_refs", []), _PARKING_ID)
    _assert_provider_call_bound(engine, provider, calls_before, followup_body)

    fresh_snapshot = get_active_snapshot(engine, _HOTEL)
    fresh_parking = next(item for item in fresh_snapshot.sources
                         if item.source_id == parking_source.source_id)
    revoked = transition_source(
        engine, hotel_id=_HOTEL, source_id=fresh_parking.source_id,
        expected_generation=fresh_snapshot.generation, expected_version=fresh_parking.source_version,
        expected_source_hash=fresh_parking.source_hash, operation_id=f"b15-r4-revoke-{uuid4().hex}",
        action="revoke",
    )
    assert revoked["lifecycle_status"] == "revoked"
    stale_followup = client.post(freshness_url, json={"request_id": followup_id}, headers=auth)
    assert stale_followup.status_code == 200, stale_followup.text
    assert stale_followup.json()["status"] == "stale"
    current_advice = client.get(
        f"/v1/guest/sessions/{session['session_id']}/room-advice", headers=auth,
    )
    assert current_advice.status_code == 200, current_advice.text
    assert current_advice.json()["currentness"] == "stale"

    after_revoke = _post(client, session, "Recommend a room, and is parking covered?")
    assert after_revoke.status_code == 200, after_revoke.text
    post_revoke_faq = after_revoke.json()["room_advice"]["hotel_answer"]
    assert _PARKING_ID not in _round4_fact_ids_in_source_refs(
        after_revoke.json()["room_advice"].get("source_refs", []),
    )
    assert _PARKING_ID not in json.dumps(post_revoke_faq, ensure_ascii=False)
    assert post_revoke_faq["unknowns"]
    replay_after_revoke = _post(
        client, session, "Recommend a room, and what does parking cost?", request_id=followup_id,
    )
    assert replay_after_revoke.status_code in {200, 409}, replay_after_revoke.text
    if replay_after_revoke.status_code == 200:
        replay_room = replay_after_revoke.json().get("room_advice")
        assert replay_room is None or replay_room.get("currentness") == "stale"


def _replacement_pack(engine, source_id: str, new_version: str) -> dict[str, object]:
    with engine.connect() as connection:
        hotel = connection.execute(select(hotels).where(hotels.c.hotel_id == _HOTEL)).mappings().one()
        source_row = connection.execute(select(knowledge_sources).where(
            knowledge_sources.c.hotel_id == _HOTEL,
            knowledge_sources.c.source_id == source_id,
        )).mappings().one()
        fact_rows = connection.execute(select(knowledge_facts).where(
            knowledge_facts.c.hotel_id == _HOTEL,
            knowledge_facts.c.source_id == source_id,
        )).mappings().all()
        media_rows = connection.execute(select(knowledge_media).where(
            knowledge_media.c.hotel_id == _HOTEL,
            knowledge_media.c.source_id == source_id,
        )).mappings().all()
    source = copy.deepcopy(source_row["source"])
    source["version"] = new_version
    facts = []
    for row in fact_rows:
        fact = copy.deepcopy(row["fact"])
        for ref in fact.get("source_refs", []):
            if ref.get("source_id") == source_id:
                ref["version"] = new_version
        facts.append(fact)
    media = []
    for row in media_rows:
        item = {key: row[key] for key in row if key not in {"hotel_id", "content"}}
        item["source_version"] = new_version
        item["content"] = row["content"]
        media.append(item)
    manifest = {"hotel": _HOTEL, "source_id": source_id, "version": new_version}
    return {
        "hotel": {
            "hotel_id": _HOTEL,
            "slug": hotel["slug"],
            "config_version": hotel["config_version"],
            "public_config": hotel["public_config"],
        },
        "sources": [source],
        "facts": facts,
        "media": media,
        "manifest": manifest,
        "canonical_hash": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
    }


def test_saved_answer_becomes_stale_after_source_version_and_revoke(engine) -> None:
    provider = OfflineB15Provider()
    client, session = _client(engine, provider)
    first_request_id = str(uuid4())
    calls_before = provider.calls
    first = _post(client, session, "Is parking covered?", request_id=first_request_id)
    assert first.status_code == 200, first.text
    first_answer = first.json()
    assert "covered" in first_answer["answer"].casefold()
    _assert_provider_call_bound(engine, provider, calls_before, first_answer)

    freshness_url = f"/v1/guest/sessions/{session['session_id']}/freshness"
    auth = {"Authorization": f"Bearer {session['access_token']}"}
    current = client.post(freshness_url, json={"request_id": first_request_id}, headers=auth)
    assert current.status_code == 200, current.text
    assert current.json()["status"] == "current"

    snapshot = get_active_snapshot(engine, _HOTEL)
    parking_source = next(item for item in snapshot.sources if item.source_id == "SRC-HTL-CITY01-TRANSPORT")
    versioned = replace_source_snapshot(
        engine,
        hotel_id=_HOTEL,
        source_id=parking_source.source_id,
        expected_generation=snapshot.generation,
        expected_version=parking_source.source_version,
        expected_source_hash=parking_source.source_hash,
        operation_id=f"b15-version-{uuid4().hex}",
        pack=_replacement_pack(engine, parking_source.source_id, "2.0"),
    )
    assert versioned["status"] == "applied"
    stale_after_version = client.post(freshness_url, json={"request_id": first_request_id}, headers=auth)
    assert stale_after_version.status_code == 200, stale_after_version.text
    assert stale_after_version.json()["status"] == "stale"

    continuation_id = str(uuid4())
    calls_before = provider.calls
    continuation = _post(client, session, "And is the parking covered?", request_id=continuation_id)
    assert continuation.status_code == 200, continuation.text
    continued = continuation.json()
    assert "covered" in continued["answer"].casefold()
    assert any(item.get("source_version") == "2.0" for item in continued["evidence"])
    _assert_provider_call_bound(engine, provider, calls_before, continued)

    fresh_snapshot = get_active_snapshot(engine, _HOTEL)
    fresh_source = next(item for item in fresh_snapshot.sources if item.source_id == parking_source.source_id)
    revoked = transition_source(
        engine,
        hotel_id=_HOTEL,
        source_id=fresh_source.source_id,
        expected_generation=fresh_snapshot.generation,
        expected_version=fresh_source.source_version,
        expected_source_hash=fresh_source.source_hash,
        operation_id=f"b15-revoke-{uuid4().hex}",
        action="revoke",
    )
    assert revoked["lifecycle_status"] == "revoked"
    stale_after_revoke = client.post(freshness_url, json={"request_id": continuation_id}, headers=auth)
    assert stale_after_revoke.status_code == 200, stale_after_revoke.text
    assert stale_after_revoke.json()["status"] == "stale"

    calls_before = provider.calls
    after_revoke = _post(client, session, "Is parking covered?")
    assert after_revoke.status_code == 200, after_revoke.text
    revoked_answer = after_revoke.json()
    assert "Parking is covered" not in revoked_answer["answer"]
    assert _PARKING_ID not in {item["fact_id"] for item in revoked_answer.get("evidence", [])}
    assert revoked_answer["unknowns"]
    _assert_provider_call_bound(engine, provider, calls_before, revoked_answer)
