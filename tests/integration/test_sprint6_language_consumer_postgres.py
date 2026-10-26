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
