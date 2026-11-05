"""Offline producer-to-consumer checks for Sprint 6 language preference metadata."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import apply_migrations
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import (
    import_fixture_pack,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    Usage,
)

TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1"


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to an isolated Sprint 6 PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    apply_migrations(database)
    import_fixture_pack(database, FIXTURE_ROOT)
    yield database
    database.dispose()


def _confirm(client: TestClient, session: dict[str, Any], challenge: dict[str, Any], request_id: str):
    return client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": request_id,
              "confirmation_token": challenge["brief_confirmation"]["token"]},
    )


class LanguageProvider:
    def __init__(self) -> None:
        self.inputs: list[dict[str, Any]] = []
        self.calls = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append({**payload, "instructions": request.instructions})
        question = payload.get("question", "").lower()
        tag = "fr" if "french" in question else "ja" if "japanese" in question else None
        if "candidate_index" in payload:
            candidates = payload.get("candidate_index", [])
            value: dict[str, Any] = {
                "fact_ids": [item["fact_id"] for item in candidates[:1]],
                "turn_intents": ["hotel_information"],
                "explicit_language_tag": tag,
                "inferred_language_tag": None,
            }
        else:
            label_keys = payload.get("missing_label_keys", [])
            if tag and payload.get("preferred_language_tag") != tag:
                label_keys = payload.get("label_bundle_keys", label_keys)
            value = {
                "supported_claims": [],
                "unknowns": ["Je ne peux pas confirmer." if tag == "fr" else "確認できません。"],
                "conflicts": [],
                "turn_intents": ["hotel_information"],
                "guest_claims": [],
                "guest_brief_refs": [],
                "explicit_language_tag": tag,
                "inferred_language_tag": None,
                "label_bundle": {key: f"label-{key}" for key in label_keys},
            }
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="fake", deployment="s6-test",
            model="offline-fake", request_id=f"s6-{self.calls}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


class SafePortionProvider:
    """Offline fixture for persisted committed-answer safe-portion behavior."""

    def __init__(self) -> None:
        self.inputs: list[dict[str, Any]] = []
        self.calls = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append({**payload, "instructions": request.instructions})
        if payload.get("guest_brief_patch_enabled") is True:
            operations = [
                {"op": "set_dates", "check_in": "2026-12-10", "check_out": "2026-12-13",
                 "current_turn_quote": "stay from December 10 to 13"},
                {"op": "set_adults", "count": 2, "current_turn_quote": "two adults"},
                {"op": "add_child", "age": None, "current_turn_quote": "one child"},
            ]
            if "candidate_index" in payload:
                candidates = payload.get("candidate_index", [])
                value: dict[str, Any] = {
                    "fact_ids": [item["fact_id"] for item in candidates[:1]],
                    "guest_patch": {"ops": operations},
                    "turn_intents": ["guest_edit", "guest_state"],
                    "explicit_language_tag": "vi",
                    "inferred_language_tag": None,
                }
            else:
                value = {
                    "supported_claims": [], "unknowns": [], "conflicts": [],
                    "guest_patch": {"ops": operations}, "guest_claims": [],
                    "guest_brief_refs": [], "explicit_language_tag": "vi",
                    "turn_intents": ["guest_edit", "guest_state"],
                    "inferred_language_tag": None,
                }
        else:
            value = {
                "supported_claims": [],
                "unknowns": ["Độ tuổi của trẻ là bao nhiêu?"],
                "conflicts": [],
                "guest_claims": [
                    {"text": "Tôi sẽ lưu trú từ 2026-12-10 đến 2026-12-13.",
                     "refs": ["dates.check_in", "dates.check_out"]},
                    {"text": "Có 2 người lớn và 1 trẻ em.", "refs": ["party.adults"]},
                ],
                "guest_brief_refs": ["dates.check_in", "dates.check_out"],
                "explicit_language_tag": None,
                "inferred_language_tag": None,
            }
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="fake", deployment="s6-safe-portion",
            model="offline-fake", request_id=f"safe-portion-{self.calls}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


class JapaneseTimezoneProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.inputs: list[dict[str, Any]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append({**payload, "instructions": request.instructions})
        if "candidate_index" in payload:
            fact_ids = [
                item["fact_id"] for item in payload.get("candidate_index", [])
                if item.get("fact_id") == "F-HTL-CITY01-040"
            ]
            value: dict[str, Any] = {
                "fact_ids": fact_ids,
                "turn_intents": ["hotel_information"],
                "explicit_language_tag": "ja",
                "inferred_language_tag": None,
            }
        else:
            fact_ids = [
                item["fact_id"] for item in payload.get("facts", [])
                if item.get("fact_id") == "F-HTL-CITY01-040"
            ]
            value = {
                "supported_claims": ([{
                    "text": "朝食は06:30～09:30に提供されます。",
                    "fact_ids": fact_ids,
                }] if fact_ids else []),
                "unknowns": [] if fact_ids else ["朝食の時間は確認できません。"],
                "conflicts": [],
                "guest_claims": [],
                "guest_brief_refs": [],
                "explicit_language_tag": "ja" if payload.get("guest_brief_patch_enabled") else None,
                "inferred_language_tag": None,
            }
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="fake", deployment="s6-timezone",
            model="offline-fake", request_id=f"japanese-timezone-{self.calls}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


class ClarificationAcknowledgementProvider:
    """Offline fixture for bounded clarification, scope, acknowledgement, and replay."""

    def __init__(self) -> None:
        self.calls = 0
        self.inputs: list[dict[str, Any]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        question = payload.get("question", "")
        self.inputs.append({**payload, "instructions": request.instructions})
        if "candidate_index" in payload:
            if "12/13" in question:
                value: dict[str, Any] = {
                    "fact_ids": [], "explicit_language_tag": "hi", "inferred_language_tag": None,
                    "turn_intents": ["guest_edit", "guest_state"],
                    "guest_patch": {"ops": [{
                        "op": "set_dates", "check_in": "2026-12-10",
                        "current_turn_quote": "चेक-इन 2026-12-10",
                    }, {
                        "op": "set_adults", "count": 2, "current_turn_quote": "2 वयस्क",
                    }, {
                        "op": "add_child", "age": 7, "current_turn_quote": "7 वर्ष का बच्चा",
                    }, {
                        "op": "clarify", "field": "dates.check_out",
                        "reason": "Confirm which checkout date the guest means.",
                        "current_turn_quote": "12/13 दिसंबर",
                    }]},
                }
            elif "2026-12-15" in question:
                value = {
                    "fact_ids": [],
                    "turn_intents": ["guest_edit", "guest_state"],
                    "explicit_language_tag": "ko" if "한국어" in question else None,
                    "inferred_language_tag": None,
                    "guest_patch": {"ops": [{
                        "op": "set_dates", "check_out": "2026-12-15",
                        "current_turn_quote": "चेक-आउट तारीख 2026-12-15",
                    }]},
                }
            else:
                value = {"fact_ids": [], "turn_intents": ["courtesy"],
                         "explicit_language_tag": None, "inferred_language_tag": None}
        elif payload.get("guest_brief_patch_enabled") is False:
            missing = payload.get("missing_label_keys", [])
            if "12/13" in question:
                value = {
                    "supported_claims": [], "unknowns": [], "conflicts": [],
                    "guest_clarification": {
                        "field": "dates.check_out", "options": ["12", "13"],
                        "text": "कृपया 12 या 13 में से सही चेक-आउट तारीख बताएं।",
                    },
                    "guest_claims": [], "guest_brief_refs": [],
                    "explicit_language_tag": None, "inferred_language_tag": None,
                    "label_bundle": {key: f"label-{key}" for key in missing},
                }
            elif "2026-12-15" in question:
                value = {
                    "supported_claims": [], "unknowns": [], "conflicts": [],
                    "guest_claims": [{
                        "text": "चेक-आउट 2026-12-15 है।", "refs": ["dates.check_out"],
                    }],
                    "guest_brief_refs": [], "explicit_language_tag": None,
                    "inferred_language_tag": None,
                    "label_bundle": {key: f"label-{key}" for key in missing},
                }
            else:
                value = {
                    "supported_claims": [], "unknowns": [], "conflicts": [],
                    "guest_claims": [], "guest_brief_refs": [],
                    "conversational_acknowledgement": {
                        "intent": "thanks_acknowledged", "text": "कोई बात नहीं।",
                    },
                    "explicit_language_tag": None, "inferred_language_tag": None,
                    "label_bundle": {key: f"label-{key}" for key in missing},
                }
        else:
            raise AssertionError("Unexpected preparation answer request")
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="fake", deployment="s6-channels",
            model="offline-fake", request_id=f"s6-channels-{self.calls}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


def test_preference_survives_restart_replay_and_old_answer_stays_historical(engine) -> None:
    provider = LanguageProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-six-language-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    assert session["language_preference"] == {"language_tag": "und", "source": "fallback", "revision": 0}
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}/messages"

    first_id = str(uuid.uuid4())
    first_response = client.post(endpoint, headers=headers, json={
        "request_id": first_id, "question": "Please answer in French.",
    })
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    assert first["language_preference"] == {"language_tag": "fr", "source": "explicit", "revision": 1}
    assert first["presentation"]["language_tag"] == "fr"
    assert first["presentation"]["direction"] == "ltr"
    assert first["presentation"]["labels_fallback"] is False
    assert first["answer_eligibility"] == "current"
    assert first["guest_brief"]["brief_version"] == 0

    replay = client.post(endpoint, headers=headers, json={
        "request_id": first_id, "question": "Please answer in French.",
    })
    assert replay.status_code == 200, replay.text
    assert replay.json()["presentation"]["language_tag"] == "fr"

    switched_id = str(uuid.uuid4())
    switched = client.post(endpoint, headers=headers, json={
        "request_id": switched_id, "question": "Please answer in Japanese.",
    })
    assert switched.status_code == 200, switched.text
    assert switched.json()["language_preference"] == {
        "language_tag": "ja", "source": "explicit", "revision": 2,
    }

    historical = client.post(endpoint, headers=headers, json={
        "request_id": first_id, "question": "Please answer in French.",
    })
    assert historical.status_code == 200, historical.text
    assert historical.json()["presentation"]["language_tag"] == "fr"
    assert historical.json()["language_preference"]["language_tag"] == "ja"
    assert historical.json()["answer_eligibility"] == "stale"
    assert historical.json()["guest_brief"]["brief_version"] == 0

    restarted_client = TestClient(create_app(settings, engine=engine, provider=provider))
    continued = restarted_client.post(endpoint, headers=headers, json={
        "request_id": str(uuid.uuid4()), "question": "ok?",
    })
    assert continued.status_code == 200, continued.text
    current = continued.json()
    assert current["language_preference"]["language_tag"] == "ja"
    assert current["presentation"]["language_tag"] == "ja"
    assert current["guest_brief"]["brief_version"] == 0
    assert any(item.get("preferred_language_tag") == "ja" for item in provider.inputs)


def test_committed_safe_portion_trace_and_answer_persist_across_same_id_replay(engine) -> None:
    provider = SafePortionProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-six-safe-portion-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}/messages"
    request_id = str(uuid.uuid4())
    body = {
        "request_id": request_id,
        "question": "Please answer in Vietnamese and save my stay from December 10 to 13 for two adults and one child.",
    }

    prepared = client.post(endpoint, headers=headers, json=body)
    assert prepared.status_code == 200, prepared.text
    challenge = prepared.json()
    assert challenge["status"] == "confirmation_required"
    assert challenge["trace"]["calls"] == challenge["trace"]["preparation_calls"] == 1
    confirmation_request_id = str(uuid.uuid4())
    response = _confirm(client, session, challenge, confirmation_request_id)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert result["trace"]["calls"] == 2
    assert result["trace"]["guest_claims_rejected"] == 1
    assert result["trace"]["answer_validation"] == "safe_portion"
    assert result["answer"] == (
        "Tôi sẽ lưu trú từ 2026-12-10 đến 2026-12-13.\n"
        "Độ tuổi của trẻ là bao nhiêu?"
    )
    assert result["guest_claims"] == [{
        "text": "Tôi sẽ lưu trú từ 2026-12-10 đến 2026-12-13.",
        "refs": ["dates.check_in", "dates.check_out"],
    }]
    assert result["guest_brief"]["brief_version"] == 1
    assert result["guest_brief"]["dates"] == {
        "check_in": "2026-12-10", "check_out": "2026-12-13", "nights": 3,
    }
    assert result["guest_brief"]["party"]["adults"] == 2
    assert len(result["guest_brief"]["party"]["children"]) == 1
    assert result["guest_brief"]["party"]["children"][0]["age"] is None
    assert result["language_preference"] == {"language_tag": "vi", "source": "explicit", "revision": 1}
    assert result["brief_receipt"]["answer_status"] == "completed"
    assert provider.calls == 2

    replay = _confirm(client, session, challenge, confirmation_request_id)
    assert replay.status_code == 200, replay.text
    replayed = replay.json()
    assert replayed["answer"] == result["answer"]
    assert replayed["guest_claims"] == result["guest_claims"]
    assert replayed["trace"]["guest_claims_rejected"] == 1
    assert replayed["trace"]["answer_validation"] == "safe_portion"
    assert replayed["guest_brief"]["brief_version"] == 1
    assert replayed["language_preference"]["language_tag"] == "vi"
    assert replayed["brief_receipt"]["answer_status"] == "completed"
    assert provider.calls == 2, "same-ID replay must use persisted answer and trace without another model call"


def test_japanese_time_answer_gets_cited_hotel_timezone_through_composition(engine) -> None:
    provider = JapaneseTimezoneProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-six-japanese-timezone-test-signing-secret"),
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
            "question": "Please answer in Japanese: what time is breakfast?",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["language_preference"] == {"language_tag": "ja", "source": "explicit", "revision": 1}
    assert result["presentation"]["language_tag"] == "ja"
    assert result["answer_eligibility"] == "current"
    assert result["guest_brief"]["brief_version"] == 0
    assert result["answer"] == (
        "朝食は06:30～09:30に提供されます。 (Asia/Ho_Chi_Minh) [F-HTL-CITY01-040]"
    )
    assert result["answer"].endswith("[F-HTL-CITY01-040]")
    assert any(item["fact_id"] == "F-HTL-CITY01-040" for item in result["evidence"])
    assert provider.calls <= 2
    assert result["trace"]["calls"] <= 2


def test_checkout_clarification_and_thanks_survive_api_same_id_replay(engine) -> None:
    provider = ClarificationAcknowledgementProvider()
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-six-typed-clarification-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}/messages"

    first_body = {
        "request_id": str(uuid.uuid4()),
        "question": (
            "हिंदी में उत्तर दें। चेक-इन 2026-12-10 है, 2 वयस्क और 7 वर्ष का बच्चा है। "
            "मैं 12/13 दिसंबर को चेक-आउट करना चाहता हूँ।"
        ),
    }
    first = client.post(endpoint, headers=headers, json=first_body)
    assert first.status_code == 200, first.text
    first_challenge = first.json()
    assert first_challenge["confirmation_required"] is True
    first_confirmation_id = str(uuid.uuid4())
    first_confirmed = _confirm(client, session, first_challenge, first_confirmation_id)
    assert first_confirmed.status_code == 200, first_confirmed.text
    clarified = first_confirmed.json()
    assert clarified["language_preference"] == {"language_tag": "hi", "source": "explicit", "revision": 1}
    assert clarified["guest_brief"]["brief_version"] == 1
    assert clarified["guest_brief"]["dates"]["check_out"] is None
    assert clarified["guest_brief"]["pending_fields"] == ["dates.check_out"]
    assert clarified["answer"] == "कृपया 12 या 13 में से सही चेक-आउट तारीख बताएं।"
    assert clarified["unknowns"] == [clarified["answer"]]
    assert clarified["answer_eligibility"] == "current"
    assert clarified["brief_receipt"]["answer_status"] == "completed"
    assert clarified["trace"]["calls"] == 2
    assert provider.calls == 2

    second_body = {
        "request_id": str(uuid.uuid4()),
        "question": "चेक-आउट तारीख 2026-12-15 है।",
    }
    second = client.post(endpoint, headers=headers, json=second_body)
    assert second.status_code == 200, second.text
    second_challenge = second.json()
    assert second_challenge["confirmation_required"] is True
    second_confirmed = _confirm(client, session, second_challenge, str(uuid.uuid4()))
    assert second_confirmed.status_code == 200, second_confirmed.text
    resolved = second_confirmed.json()
    assert resolved["language_preference"] == {"language_tag": "hi", "source": "explicit", "revision": 1}
    assert resolved["guest_brief"]["brief_version"] == 2
    assert resolved["guest_brief"]["dates"] == {
        "check_in": "2026-12-10", "check_out": "2026-12-15", "nights": 5,
    }
    assert resolved["guest_brief"]["pending_fields"] == []
    assert resolved["guest_brief"]["party"]["children"][0]["age"] == 7
    assert resolved["answer"] == "चेक-आउट 2026-12-15 है।"
    assert resolved["trace"]["calls"] == 2
    assert provider.calls == 4

    third_body = {"request_id": str(uuid.uuid4()), "question": "OK, 고마워"}
    third = client.post(endpoint, headers=headers, json=third_body)
    assert third.status_code == 200, third.text
    thanked = third.json()
    assert thanked["language_preference"] == {"language_tag": "hi", "source": "explicit", "revision": 1}
    assert thanked["guest_brief"]["brief_version"] == 2
    assert thanked["answer"] == "कोई बात नहीं।"
    assert thanked["trace"]["calls"] == 2
    assert provider.calls == 6

    replay = client.post(endpoint, headers=headers, json=third_body)
    assert replay.status_code == 200, replay.text
    replayed = replay.json()
    assert replayed["answer"] == thanked["answer"]
    assert replayed["language_preference"] == thanked["language_preference"]
    assert replayed["guest_brief"]["brief_version"] == thanked["guest_brief"]["brief_version"]
    assert replayed["trace"]["calls"] == 2
    assert provider.calls == 6, "same-ID replay must return persisted acknowledgement without another model call"

    old_clarification = _confirm(client, session, first_challenge, first_confirmation_id)
    assert old_clarification.status_code == 200, old_clarification.text
    assert old_clarification.json()["answer_eligibility"] == "stale"
    assert provider.calls == 6, "replaying a stale clarification must not call the provider"
