"""Offline HTTP/PostgreSQL observations for B10 trace and call controls."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import staylead_platform.composition.dependencies.guest_chat as guest_chat_composition
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations,
    get_guest_brief,
    requests,
)
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import (
    import_fixture_pack,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1"
TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")


class OfflineB10Provider:
    """Deterministic schema-aware provider; every call is observable and offline."""

    def __init__(self) -> None:
        self.calls = 0
        self.inputs: list[dict[str, Any]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append({"instructions": request.instructions, **payload})
        question = payload.get("question", "")
        patch_enabled = payload.get("guest_brief_patch_enabled") is True
        operations = []
        if patch_enabled and "set my dates" in question.lower():
            operations = [
                {"op": "set_dates", "check_in": "2027-05-10", "check_out": "2027-05-13",
                 "current_turn_quote": "May 10 through May 13, 2027"},
                {"op": "set_adults", "count": 2, "current_turn_quote": "two adults"},
                {"op": "add_child", "age": 9, "current_turn_quote": "one child age 9"},
            ]
        if "candidate_index" in payload:
            candidates = payload.get("candidate_index", [])
            breakfast_fact = next((item for item in candidates if item.get("fact_id") == "F-HTL-CITY01-040"), None)
            result: dict[str, Any] = {
                "fact_ids": [(breakfast_fact or candidates[0])["fact_id"]] if candidates else [],
                "turn_intents": ["hotel_information", "guest_edit"] if operations else ["hotel_information"],
            }
            if operations:
                result["guest_patch"] = {"ops": operations}
        else:
            facts = payload.get("facts", [])
            breakfast_fact = next((item for item in facts if item.get("fact_id") == "F-HTL-CITY01-040"), None)
            selected_fact = breakfast_fact or (facts[0] if facts else None)
            result = {
                "supported_claims": ([{
                    "text": "Breakfast buffet at Ben Gio, floor 1, 06:30-09:30.",
                    "fact_ids": [selected_fact["fact_id"]],
                }] if selected_fact else []),
                "unknowns": [] if selected_fact else ["That detail is not in the available hotel records."],
                "conflicts": [],
            }
            if patch_enabled:
                result["turn_intents"] = ["hotel_information"]
        return GenerationResult(
            text=json.dumps(result), provider="fake", deployment="b10-offline", model="deterministic",
            request_id=f"offline-{self.calls}", usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


def create_b10_test_app() -> tuple[Any, Any, OfflineB10Provider]:
    """Build an opt-in browser app only against the dedicated local B10 browser DB."""
    if os.environ.get("B10_TEST_ONLY") != "1":
        raise RuntimeError("Set B10_TEST_ONLY=1 to create the B10 offline test app.")
    dsn = os.environ.get("B10_TEST_DATABASE_URL", "")
    parsed_dsn = urlsplit(dsn)
    if parsed_dsn.hostname not in {"127.0.0.1", "localhost"} or parsed_dsn.port != 55441 \
            or parsed_dsn.path != "/staylead_s11_browser":
        raise RuntimeError("B10_TEST_DATABASE_URL must target local staylead_s11_browser on port 55441.")
    secret = os.environ.get("B10_TEST_SIGNING_SECRET")
    if not secret:
        raise RuntimeError("Set an ephemeral B10_TEST_SIGNING_SECRET for the offline browser test app.")
    engine = create_database_engine(dsn)
    apply_migrations(engine)
    import_fixture_pack(engine, FIXTURE_ROOT)
    settings = Settings(
        _env_file=None, environment="test", database_url=dsn, ai_provider="disabled",
        session_signing_secret=SecretStr(secret),
    )
    provider = OfflineB10Provider()
    return create_app(settings, engine=engine, provider=provider), engine, provider


def create_b10_browser_app() -> Any:
    """Uvicorn factory surface for CUA; environment guards stay centralized above."""
    app, _engine, _provider = create_b10_test_app()
    return app


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to the isolated Sprint 11 B10 PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    apply_migrations(database)
    import_fixture_pack(database, FIXTURE_ROOT)
    yield database
    database.dispose()


def _client(engine, provider: OfflineB10Provider) -> tuple[TestClient, dict[str, Any]]:
    settings = Settings(
        _env_file=None, environment="test", database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("b10-offline-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201, opened.text
    return client, opened.json()


def _post(client: TestClient, session: dict[str, Any], body: dict[str, str]):
    return client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages", json=body,
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )


def test_simple_and_mixed_turn_emit_offline_trace_observations(engine) -> None:
    provider = OfflineB10Provider()
    client, session = _client(engine, provider)
    calls_before_simple = provider.calls
    simple = _post(client, session, {"request_id": str(uuid.uuid4()), "question": "What are the breakfast hours?"})
    assert simple.status_code == 200, simple.text
    simple_json = simple.json()
    simple_provider_calls = provider.calls - calls_before_simple
    assert simple_provider_calls == 2
    assert any(item["fact_id"] == "F-HTL-CITY01-040" for item in simple_json["evidence"])
    assert "06:30" in simple_json["answer"] and "09:30" in simple_json["answer"]
    assert simple_json["trace"]["execution"]["schema_version"] == 1
    assert simple_json["trace"]["execution"]["answer_schema_version"] == "hospitality-grounded-v2"
    assert simple_json["trace"]["execution"]["outcome"] == "ok"
    assert simple_json["trace"]["execution"]["elapsed_ms"] >= 0
    assert simple_json["trace"]["execution"]["events"]

    mixed_started = time.monotonic()
    challenge_id = str(uuid.uuid4())
    calls_before_preparation = provider.calls
    mixed_question = (
        "Please set my dates to May 10 through May 13, 2027 for two adults and one child age 9. "
        "Also, what are the breakfast hours?"
    )
    challenge = _post(client, session, {"request_id": challenge_id, "question": mixed_question})
    assert challenge.status_code == 200, challenge.text
    challenge_json = challenge.json()
    assert challenge_json["confirmation_required"] is True
    assert challenge_json["guest_brief"]["brief_version"] == 0
    preparation_execution = challenge_json["trace"]["execution"]
    preparation_provider_calls = provider.calls - calls_before_preparation
    assert preparation_provider_calls == 1
    assert preparation_execution["outcome"] == "ok"
    assert sum(event.get("calls", 0) for event in preparation_execution["events"]
               if event["stage"] == "provider") == 1

    confirm_id = str(uuid.uuid4())
    calls_before_confirmation = provider.calls
    confirmation = client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": confirm_id, "confirmation_token": challenge_json["brief_confirmation"]["token"]},
    )
    assert confirmation.status_code == 200, confirmation.text
    confirmed = confirmation.json()
    confirmation_provider_calls = provider.calls - calls_before_confirmation
    assert confirmation_provider_calls == 1
    assert confirmed["guest_brief"]["brief_version"] == 1
    assert confirmed["evidence"], "the mixed turn must retain FAQ evidence after applying authoritative brief edit"
    assert any(item["fact_id"] == "F-HTL-CITY01-040" for item in confirmed["evidence"])
    assert "06:30" in confirmed["answer"] and "09:30" in confirmed["answer"]
    execution = confirmed["trace"]["execution"]
    assert execution["schema_version"] == 1
    assert execution["outcome"] == "ok"
    assert sum(event.get("calls", 0) for event in execution["events"] if event["stage"] == "provider") <= 2
    assert any(event.get("input_tokens") == 3 for event in execution["events"] if event["stage"] == "provider")
    assert execution["elapsed_ms"] >= 0
    assert get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-CITY01").brief_version == 1
    workflow_elapsed_ms = int((time.monotonic() - mixed_started) * 1000)

    print(json.dumps({
        "benchmark": "offline-b10-http-postgres",
        "provider": "deterministic-fake",
        "simple": {"expected": "200 grounded FAQ", "observed": simple.status_code,
                   "elapsed_ms": simple_json["trace"]["execution"]["elapsed_ms"],
                   "provider_calls": simple_provider_calls,
                   "source_usage": [event for event in simple_json["trace"]["execution"]["events"]
                                    if event["stage"] == "provider"],
                   "trace": simple_json["trace"]["execution"]},
        "mixed": {"expected": "brief version 1 and sourced FAQ after confirmation",
                  "workflow_elapsed_ms": workflow_elapsed_ms,
                  "preparation_request_id": challenge_id,
                  "preparation_elapsed_ms": preparation_execution["elapsed_ms"],
                  "preparation_provider_calls": preparation_provider_calls,
                  "confirmation_request_id": confirm_id,
                  "confirmation_elapsed_ms": execution["elapsed_ms"],
                  "confirmation_provider_calls": confirmation_provider_calls,
                  "per_request_call_cap": 2,
                  "observed": {"status": confirmation.status_code,
                               "brief_version": confirmed["guest_brief"]["brief_version"],
                               "has_evidence": bool(confirmed["evidence"])},
                  "preparation_trace": preparation_execution,
                  "confirmation_trace": execution},
    }, sort_keys=True))


def test_retrieval_failure_returns_safe_bounded_trace(engine, monkeypatch) -> None:
    provider = OfflineB10Provider()
    client, session = _client(engine, provider)
    retriever = client.app.state.guest_chat._orchestrator._retriever

    def fail_retrieval(*_args, **_kwargs):
        raise RuntimeError("private retrieval payload must not escape")

    monkeypatch.setattr(retriever, "retrieve", fail_retrieval)
    response = _post(client, session, {
        "request_id": str(uuid.uuid4()), "question": "What are the breakfast hours?",
    })
    assert response.status_code == 500, response.text
    assert "private retrieval payload" not in response.text
    trace = response.json()["trace"]["execution"]
    assert trace["outcome"] == "error"
    assert trace["failure_stage"] == "retrieval"
    assert trace["schema_version"] == 1
    assert len(trace["events"]) <= 20
    assert provider.calls == 0


def test_invalid_model_output_trace_names_response_failure_stage(engine) -> None:
    class InvalidOutputProvider(OfflineB10Provider):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls += 1
            return GenerationResult(
                text="{}", provider="fake", deployment="invalid", model="invalid",
                request_id=f"invalid-{self.calls}", usage=Usage(1, 1, 2),
            )

    provider = InvalidOutputProvider()
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())
    response = _post(client, session, {"request_id": request_id, "question": "What are the breakfast hours?"})
    assert response.status_code == 502
    execution = response.json()["trace"]["execution"]
    assert execution["outcome"] == "error"
    assert execution["failure_stage"] == "response"
    assert execution["failure_code"] == "invalid_model_output"


def test_final_storage_failure_overwrites_optimistic_success_trace(engine, monkeypatch) -> None:
    provider = OfflineB10Provider()
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())

    def fail_completion(*_args, **_kwargs):
        raise RuntimeError("controlled completion failure")

    monkeypatch.setattr(guest_chat_composition, "complete_request", fail_completion)
    response = _post(client, session, {"request_id": request_id, "question": "What are the breakfast hours?"})
    assert response.status_code == 500
    response_execution = response.json()["trace"]["execution"]
    assert response_execution["outcome"] == "error"
    assert response_execution["failure_stage"] == "response"
    with engine.begin() as connection:
        row = connection.execute(select(requests).where(requests.c.request_id == request_id)).mappings().one()
    assert row["status"] == "error"
    assert row["response"]["trace"]["outcome"] == "error"
    assert row["response"]["trace"]["failure_stage"] == "response"


def test_confirmation_answer_failure_trace_survives_on_parent_and_replay(engine) -> None:
    class FailConfirmationAnswerProvider(OfflineB10Provider):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            if self.calls >= 1:
                self.calls += 1
                raise ProviderError("controlled_failure", "The offline answer failed.")
            return await super().generate(request)

    provider = FailConfirmationAnswerProvider()
    client, session = _client(engine, provider)
    challenge = _post(client, session, {
        "request_id": str(uuid.uuid4()),
        "question": (
            "Please set my dates to May 10 through May 13, 2027 for two adults and one child age 9. "
            "Also, what are the breakfast hours?"
        ),
    })
    assert challenge.status_code == 200, challenge.text
    original = challenge.json()
    request_id = str(uuid.uuid4())
    url = f"/v1/guest/sessions/{session['session_id']}/brief-confirmations"
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    payload = {"request_id": request_id, "confirmation_token": original["brief_confirmation"]["token"]}
    failed = client.post(url, headers=headers, json=payload)
    assert failed.status_code == 502, failed.text
    body = failed.json()
    assert body["status"] == "partial_success"
    assert body["guest_brief"]["brief_version"] == 1
    assert body["brief_receipt"]["answer_status"] == "failed"
    execution = body["trace"]["execution"]
    assert execution["request_id"] == request_id
    assert execution["outcome"] == "error"
    assert execution["failure_stage"] == "provider"
    assert execution["failure_code"] == "controlled_failure"
    assert body["preparation_trace"]["execution"]["outcome"] == "ok"
    with engine.begin() as connection:
        parent = connection.execute(select(requests).where(requests.c.request_id == request_id)).mappings().one()
    assert parent["status"] == "completed"
    assert parent["provider_calls"] == 1
    assert parent["response"]["trace"]["execution"]["failure_code"] == "controlled_failure"
    calls_after_failure = provider.calls
    replay = client.post(url, headers=headers, json=payload)
    assert replay.status_code == 200
    assert replay.json()["trace"]["execution"]["failure_code"] == "controlled_failure"
    assert provider.calls == calls_after_failure


def test_confirmation_reservation_obeys_one_absolute_turn_deadline(engine) -> None:
    provider = OfflineB10Provider()
    client, session = _client(engine, provider)
    challenge = _post(client, session, {
        "request_id": str(uuid.uuid4()),
        "question": (
            "Please set my dates to May 10 through May 13, 2027 for two adults and one child age 9. "
            "Also, what are the breakfast hours?"
        ),
    })
    assert challenge.status_code == 200, challenge.text
    client.app.state.guest_chat._settings.ai_turn_timeout_seconds = 1.0

    advisory_ready = threading.Event()
    session_ready = threading.Event()
    release_locks = threading.Event()

    def hold_admission_lock() -> None:
        with engine.begin() as connection:
            connection.execute(text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
            ), {"key": "staylead:guest-admission:hotel:HTL-CITY01"})
            advisory_ready.set()
            release_locks.wait(timeout=3)
            time.sleep(0.35)

    def hold_session_lock() -> None:
        with engine.begin() as connection:
            connection.execute(text(
                "SELECT session_id FROM guest_sessions WHERE session_id = :session_id FOR UPDATE"
            ), {"session_id": session["session_id"]})
            session_ready.set()
            release_locks.wait(timeout=3)
            time.sleep(1.25)

    advisory_holder = threading.Thread(target=hold_admission_lock, daemon=True)
    session_holder = threading.Thread(target=hold_session_lock, daemon=True)
    advisory_holder.start()
    session_holder.start()
    assert advisory_ready.wait(timeout=2)
    assert session_ready.wait(timeout=2)
    release_locks.set()
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    response = client.post(
        f"/v1/guest/sessions/{session['session_id']}/brief-confirmations",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": request_id, "confirmation_token": challenge.json()["brief_confirmation"]["token"]},
    )
    elapsed = time.monotonic() - started
    advisory_holder.join(timeout=3)
    session_holder.join(timeout=3)
    assert response.status_code == 504, response.text
    assert response.json()["error"]["code"] == "provider_timeout"
    assert elapsed < 1.5, f"confirmation exceeded its 1-second deadline: {elapsed:.3f}s"
    assert provider.calls == 1, "expired admission must not dispatch a provider request"
