"""PostgreSQL-backed Sprint 1 contracts; model calls are always faked here."""

import asyncio
import json
import os
import shutil
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import StatementError

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies.guest_chat import GuestChatError
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.knowledge_repository import (
    PostgresKnowledgeFactRepository,
)
from staylead_platform.infrastructure.persistence.store import (
    VersionConflict,
    apply_migrations,
    complete_request,
    create_session,
    facts_for_hotel,
    fail_request,
    get_hotel,
    get_session,
    recent_messages,
    requests,
    reserve_request,
    schema_version,
)
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import (
    import_fixture_pack,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    Usage,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1"
TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to a dedicated PostgreSQL test database.")
    database = create_database_engine(TEST_DSN)
    apply_migrations(database)
    import_fixture_pack(database, FIXTURE_ROOT)
    yield database
    database.dispose()


class FakeProvider:
    def __init__(self):
        self.calls = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        if "Select only fact IDs" in request.instructions:
            index = json.loads(request.input_text)["candidate_index"]
            eligible = [item["fact_id"] for item in index]
            result = {
                "fact_ids": eligible[:4], "turn_intents": ["hotel_information"],
                "guest_patch_authorizations": [],
            }
        else:
            facts = json.loads(request.input_text)["facts"]
            if facts:
                fact_id = facts[0]["fact_id"]
                result = {
                    "supported_claims": [{"text": f"The available record is [{fact_id}].", "fact_ids": [fact_id]}],
                    "unknowns": [], "conflicts": [],
                }
            else:
                result = {"supported_claims": [], "unknowns": ["This detail is not in the available records."], "conflicts": []}
            result["turn_intents"] = ["hotel_information"]
            result["guest_patch_authorizations"] = []
        return GenerationResult(
            text=json.dumps(result), provider="fake", deployment="test", model="offline-fake",
            request_id=f"fake-{self.calls}", usage=Usage(input_tokens=5, output_tokens=5, total_tokens=10),
        )


def settings_for(database_url: str, *, ai_turn_timeout_seconds: float = 45.0) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        ai_provider="disabled",
        session_signing_secret=SecretStr("offline-test-signing-secret"),
        ai_turn_timeout_seconds=ai_turn_timeout_seconds,
    )


def test_explicit_migration_fixture_bootstrap_and_hotel_scoped_provenance(engine) -> None:
    assert schema_version(engine) == 7
    cities = facts_for_hotel(engine, "HTL-CITY01")
    beach = facts_for_hotel(engine, "HTL-BEACH02")
    assert len(cities) == 115
    assert len(beach) == 114
    assert sum(item["field"] in {"room_type", "reference_rate"} for item in cities) == 6
    assert sum(item["field"] in {"room_type", "reference_rate"} for item in beach) == 6
    assert all(item["hotel_id"] == "HTL-CITY01" for item in cities)
    assert all(item["provenance"]["source_id"].startswith("SRC-HTL-CITY01") for item in cities)
    assert all(item["fact_id"] != "F-HTL-CITY01-004" for item in cities)
    assert get_hotel(engine, "HTL-CITY01")["public_config"]["synthetic"] is True


def test_fact_validity_is_intersected_with_each_referenced_source(engine, tmp_path, monkeypatch) -> None:
    fixture_copy = tmp_path / "knowledge-v1"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    today = datetime.now(UTC).date()

    sources_path = fixture_copy / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    source = next(item for item in sources if item["source_id"] == "SRC-HTL-CITY01-FOOD")
    source["valid_from"] = today.isoformat()
    source["valid_to"] = today.isoformat()
    sources_path.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")

    # The authored fact spans a wider interval; its stored serving interval must
    # be narrowed to the source interval without changing its provenance refs.
    import_fixture_pack(engine, fixture_copy)
    stored = next(fact for fact in facts_for_hotel(engine, "HTL-CITY01")
                  if fact["fact_id"] == "F-HTL-CITY01-040")
    assert (stored["valid_from"], stored["valid_to"]) == (today.isoformat(), today.isoformat())
    assert stored["source_refs"][0]["source_id"] == "SRC-HTL-CITY01-FOOD"
    assert stored["source_refs"][0]["version"] == "1.0"

    import staylead_platform.infrastructure.persistence.knowledge_repository as repository_module

    class ShiftedDateTime(datetime):
        day_offset = 0

        @classmethod
        def now(cls, tz=None):
            instant = datetime.now(UTC) + timedelta(days=cls.day_offset)
            return instant if tz is None else instant.astimezone(tz)

    monkeypatch.setattr(repository_module, "datetime", ShiftedDateTime)
    repository = PostgresKnowledgeFactRepository(engine)
    assert any(fact.fact_id == "F-HTL-CITY01-040" for fact in repository.list_guest_facts("HTL-CITY01"))
    ShiftedDateTime.day_offset = -1
    assert all(fact.fact_id != "F-HTL-CITY01-040" for fact in repository.list_guest_facts("HTL-CITY01"))
    ShiftedDateTime.day_offset = 1
    assert all(fact.fact_id != "F-HTL-CITY01-040" for fact in repository.list_guest_facts("HTL-CITY01"))

    # Keep this shared test DB on the canonical fixture for later integration tests.
    import_fixture_pack(engine, FIXTURE_ROOT)


def test_http_guest_session_scope_and_idempotent_response_retry(engine) -> None:
    provider = FakeProvider()
    client = TestClient(create_app(settings_for(TEST_DSN), engine=engine, provider=provider))
    city = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    beach = client.post("/v1/guest/sessions", json={"hotel_slug": "lagoon-family-demo"})
    assert city.status_code == beach.status_code == 201
    city_data, beach_data = city.json(), beach.json()
    assert city_data["hotel"]["hotel_id"] == "HTL-CITY01"
    assert city_data["hotel"]["synthetic"] is True
    assert "email" not in city_data["hotel"] and "phone" not in city_data["hotel"]

    request_id = str(uuid.uuid4())
    url = f"/v1/guest/sessions/{city_data['session_id']}/messages"
    headers = {"Authorization": f"Bearer {city_data['access_token']}"}
    body = {"request_id": request_id, "question": "When is breakfast and where can I park?"}
    first = client.post(url, json=body, headers=headers)
    calls = provider.calls
    replay = client.post(url, json=body, headers=headers)
    assert first.status_code == 200
    assert replay.json() == first.json()
    assert provider.calls == calls
    assert first.json()["trace"]["calls"] in (1, 2)
    assert first.json()["evidence"]

    mismatch = client.post(url, json={"request_id": request_id, "question": "changed payload"}, headers=headers)
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "idempotency_conflict"
    cross_session = client.post(
        f"/v1/guest/sessions/{beach_data['session_id']}/messages",
        json=body,
        headers={"Authorization": f"Bearer {beach_data['access_token']}"},
    )
    assert cross_session.status_code == 409
    assert cross_session.json()["error"]["code"] == "idempotency_conflict"

    wrong_path = client.post(
        f"/v1/guest/sessions/{beach_data['session_id']}/messages",
        json={"request_id": str(uuid.uuid4()), "question": "hello"},
        headers=headers,
    )
    assert wrong_path.status_code == 403
    assert client.post(url, json=body).status_code == 401


def test_turn_deadline_bounds_postgres_lock_wait_and_cleans_reservation(engine) -> None:
    provider = FakeProvider()
    client = TestClient(create_app(
        settings_for(TEST_DSN, ai_turn_timeout_seconds=1.0), engine=engine, provider=provider,
    ))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201
    session = opened.json()

    locked = threading.Event()
    release = threading.Event()

    def hold_session_lock() -> None:
        with engine.begin() as connection:
            connection.execute(text(
                "SELECT session_id FROM guest_sessions WHERE session_id = :session_id FOR UPDATE"
            ), {"session_id": session["session_id"]})
            locked.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_session_lock, daemon=True)
    holder.start()
    assert locked.wait(timeout=2)
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        response = client.post(
            f"/v1/guest/sessions/{session['session_id']}/messages",
            json={"request_id": request_id, "question": "Where is breakfast?"},
            headers={"Authorization": f"Bearer {session['access_token']}"},
        )
    finally:
        release.set()
        holder.join(timeout=2)
    elapsed = time.monotonic() - started

    assert response.status_code == 504
    assert elapsed < 1.8
    assert get_session(engine, session["session_id"])["state_version"] == 0
    assert recent_messages(engine, session["session_id"], "HTL-CITY01") == []
    with engine.connect() as connection:
        request = connection.execute(select(requests).where(
            requests.c.request_id == request_id,
        )).mappings().one()
    assert request["status"] == "error"
    time.sleep(0.05)
    assert get_session(engine, session["session_id"])["state_version"] == 0


def test_absolute_deadline_rolls_back_after_two_individually_short_lock_waits(engine) -> None:
    model_started = threading.Event()
    allow_model = threading.Event()

    class GatedProvider:
        calls = 0

        async def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls += 1
            if self.calls == 1:
                model_started.set()
                await asyncio.to_thread(allow_model.wait)
            if "Select only fact IDs" in request.instructions:
                candidate_index = json.loads(request.input_text)["candidate_index"]
                result = {
                    "fact_ids": [candidate_index[0]["fact_id"]],
                    "turn_intents": ["hotel_information"],
                    "guest_patch_authorizations": [],
                }
            else:
                facts = json.loads(request.input_text)["facts"]
                fact_id = facts[0]["fact_id"]
                result = {
                    "supported_claims": [{"text": "The available record covers breakfast.", "fact_ids": [fact_id]}],
                    "unknowns": [], "conflicts": [],
                }
            result["turn_intents"] = ["hotel_information"]
            result["guest_patch_authorizations"] = []
            return GenerationResult(
                text=json.dumps(result), provider="fake", deployment="test", model="offline-fake",
                request_id=f"gated-{self.calls}", usage=Usage(input_tokens=5, output_tokens=5, total_tokens=10),
            )

    provider = GatedProvider()
    application = create_app(
        settings_for(TEST_DSN, ai_turn_timeout_seconds=1.0), engine=engine, provider=provider,
    ).state.guest_chat
    opened = application.open_session("harbor-city-demo")
    request_id = str(uuid.uuid4())
    session_locked = threading.Event()
    release_session = threading.Event()
    request_locked = threading.Event()

    def hold_session_row() -> None:
        with engine.begin() as connection:
            connection.execute(text(
                "SELECT session_id FROM guest_sessions WHERE session_id = :session_id FOR UPDATE"
            ), {"session_id": opened["session_id"]})
            session_locked.set()
            release_session.wait(timeout=2)

    def hold_request_row() -> None:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                exists = connection.execute(select(requests.c.request_id).where(
                    requests.c.request_id == request_id,
                )).first()
            if exists:
                with engine.begin() as connection:
                    connection.execute(select(requests.c.request_id).where(
                        requests.c.request_id == request_id,
                    ).with_for_update()).first()
                    request_locked.set()
                    time.sleep(0.6)
                return
            time.sleep(0.01)

    session_holder = threading.Thread(target=hold_session_row, daemon=True)
    session_holder.start()
    assert session_locked.wait(timeout=2)
    result: dict[str, Any] = {}

    def send() -> None:
        try:
            result["response"] = asyncio.run(application.send_message(
                session_id=opened["session_id"], token=opened["access_token"],
                request_id=request_id, question="Where is breakfast?",
            ))
        except GuestChatError as exc:
            result["error"] = exc

    caller = threading.Thread(target=send, daemon=True)
    caller.start()
    request_holder = threading.Thread(target=hold_request_row, daemon=True)
    assert model_started.wait(timeout=2)
    request_holder.start()
    assert request_locked.wait(timeout=2)
    allow_model.set()
    caller.join(timeout=3)
    release_session.set()
    session_holder.join(timeout=2)
    request_holder.join(timeout=2)

    assert not caller.is_alive()
    assert result.get("error") is not None
    assert result["error"].status == 504
    assert get_session(engine, opened["session_id"])["state_version"] == 0
    assert recent_messages(engine, opened["session_id"], "HTL-CITY01") == []
    with engine.connect() as connection:
        request_row = connection.execute(select(requests).where(
            requests.c.request_id == request_id,
        )).mappings().one()
    assert request_row["status"] == "error"
    assert request_row["response"] is None


def test_cancelled_turn_marks_request_failed_and_keeps_session_unmodified(engine) -> None:
    started = asyncio.Event()

    class BlockingProvider:
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            started.set()
            await asyncio.Future()

    application = create_app(
        settings_for(TEST_DSN), engine=engine, provider=BlockingProvider(),
    ).state.guest_chat
    opened = application.open_session("harbor-city-demo")
    request_id = str(uuid.uuid4())

    async def cancel_inflight() -> None:
        task = asyncio.create_task(application.send_message(
            session_id=opened["session_id"], token=opened["access_token"],
            request_id=request_id, question="Where is breakfast?",
        ))
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_inflight())
    assert get_session(engine, opened["session_id"])["state_version"] == 0
    assert recent_messages(engine, opened["session_id"], "HTL-CITY01") == []
    with engine.connect() as connection:
        request = connection.execute(select(requests).where(
            requests.c.request_id == request_id,
        )).mappings().one()
    assert request["status"] == "error"


def test_cancellation_signal_aborts_waiting_complete_transaction_before_commit(engine) -> None:
    session_id, request_id = str(uuid.uuid4()), str(uuid.uuid4())
    create_session(engine, session_id, "HTL-CITY01", datetime.now(UTC) + timedelta(hours=1))
    reserve_request(
        engine, session_id=session_id, hotel_id="HTL-CITY01",
        request_id=request_id, question="cancel before commit",
    )
    locked = threading.Event()
    release = threading.Event()
    cancelled = threading.Event()
    outcome: dict[str, BaseException] = {}

    def hold_session() -> None:
        with engine.begin() as connection:
            connection.execute(text(
                "SELECT session_id FROM guest_sessions WHERE session_id = :session_id FOR UPDATE"
            ), {"session_id": session_id})
            locked.set()
            release.wait(timeout=2)

    def complete() -> None:
        try:
            complete_request(
                engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=request_id,
                question="cancel before commit", answer="must roll back", evidence=[],
                timeout_seconds=2, deadline_monotonic=time.monotonic() + 3,
                cancellation_event=cancelled,
            )
        except TimeoutError as exc:
            outcome["error"] = exc

    holder = threading.Thread(target=hold_session, daemon=True)
    holder.start()
    assert locked.wait(timeout=2)
    worker = threading.Thread(target=complete, daemon=True)
    worker.start()
    waiting_deadline = time.monotonic() + 2
    waiting_for_session = False
    while time.monotonic() < waiting_deadline:
        with engine.connect() as connection:
            waiting_for_session = connection.scalar(text(
                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                "AND query LIKE '%guest_sessions%' AND state = 'active')"
            ))
        if waiting_for_session:
            break
        time.sleep(0.01)
    assert waiting_for_session
    cancelled.set()
    release.set()
    worker.join(timeout=2)
    holder.join(timeout=2)

    assert not worker.is_alive()
    assert isinstance(outcome.get("error"), TimeoutError)
    assert get_session(engine, session_id)["state_version"] == 0
    assert recent_messages(engine, session_id, "HTL-CITY01") == []
    fail_request(engine, session_id=session_id, request_id=request_id, code="request_cancelled")
    with engine.connect() as connection:
        request = connection.execute(select(requests).where(
            requests.c.request_id == request_id,
        )).mappings().one()
    assert request["status"] == "error"


def test_postgres_expected_version_atomicity_and_transaction_rollback(engine) -> None:
    session_id = str(uuid.uuid4())
    request_a, request_b = str(uuid.uuid4()), str(uuid.uuid4())
    create_session(engine, session_id, "HTL-CITY01", datetime.now(UTC) + timedelta(hours=1))
    assert reserve_request(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=request_a, question="one",
    ) is None
    assert reserve_request(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=request_b, question="two",
    ) is None
    complete_request(
        engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=request_a,
        question="one", answer="done", evidence=[],
    )
    with pytest.raises(VersionConflict):
        complete_request(
            engine, session_id=session_id, hotel_id="HTL-CITY01", request_id=request_b,
            question="two", answer="done", evidence=[],
        )
    session = get_session(engine, session_id)
    assert session["state_version"] == 1
    assert len(recent_messages(engine, session_id, "HTL-CITY01")) == 2

    rollback_session = str(uuid.uuid4())
    rollback_request = str(uuid.uuid4())
    create_session(engine, rollback_session, "HTL-CITY01", datetime.now(UTC) + timedelta(hours=1))
    reserve_request(
        engine, session_id=rollback_session, hotel_id="HTL-CITY01",
        request_id=rollback_request, question="rollback",
    )
    with pytest.raises((StatementError, TypeError)):
        complete_request(
            engine, session_id=rollback_session, hotel_id="HTL-CITY01", request_id=rollback_request,
            question="rollback", answer="will roll back", evidence=[],
            response_fields={"not_json_serializable": object()},
        )
    assert get_session(engine, rollback_session)["state_version"] == 0
    assert recent_messages(engine, rollback_session, "HTL-CITY01") == []
