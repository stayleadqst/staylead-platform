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
                {"op": "set_dates", "check_in": "2026-12-10", "check_out": "2026-12-13"},
                {"op": "set_adults", "count": 2},
                {"op": "add_child", "age": None},
            ]
            if "candidate_index" in payload:
                candidates = payload.get("candidate_index", [])
                value: dict[str, Any] = {
                    "fact_ids": [item["fact_id"] for item in candidates[:1]],
                    "guest_patch": {"ops": operations},
                    "explicit_language_tag": "vi",
                    "inferred_language_tag": None,
                }
            else:
                value = {
                    "supported_claims": [], "unknowns": [], "conflicts": [],
                    "guest_patch": {"ops": operations}, "guest_claims": [],
                    "guest_brief_refs": [], "explicit_language_tag": "vi",
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

    response = client.post(endpoint, headers=headers, json=body)
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

    replay = client.post(endpoint, headers=headers, json=body)
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
