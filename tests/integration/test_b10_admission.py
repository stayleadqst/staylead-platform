"""Sprint 11 B10 durable guest admission and raw-body limits."""

from __future__ import annotations

import asyncio
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, Thread, current_thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, text, update
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import RawRequestBodyLimitMiddleware, create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence import store as store_module
from staylead_platform.infrastructure.persistence.store import (
    ProviderCallLimitExceeded,
    QuotaExceeded,
    RequestInProgress,
    apply_migrations,
    consume_provider_slot,
    create_session,
    fail_request,
    request_payload_hash,
    requests,
    reserve_request,
    schema_version,
    schema_versions,
)
from staylead_platform.platform.contracts.admission import GuestAdmissionLimits

TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to the isolated Sprint 11 A PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    apply_migrations(database)
    yield database
    database.dispose()


def _new_session(engine, hotel_id: str) -> str:
    session_id = str(uuid.uuid4())
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=1))
    return session_id


def test_turn_and_provider_reservations_are_durable_and_idempotent(engine) -> None:
    hotel_id, session_id = f"ADMIT-{uuid.uuid4().hex[:12]}", None
    session_id = _new_session(engine, hotel_id)
    request_id, question, owner = str(uuid.uuid4()), "How late is breakfast?", str(uuid.uuid4())
    limits = GuestAdmissionLimits(turns_per_session=2, turns_per_hotel=4)
    lease_until = datetime.now(UTC) + timedelta(seconds=45)
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        question=question, limits=limits, lease_owner=owner, lease_until=lease_until,
    ) is None
    payload_hash = request_payload_hash(question)
    assert consume_provider_slot(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        payload_hash=payload_hash, lease_owner=owner, limits=limits,
    ) == 1
    assert consume_provider_slot(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        payload_hash=payload_hash, lease_owner=owner, limits=limits,
    ) == 2
    with pytest.raises(ProviderCallLimitExceeded) as denied:
        consume_provider_slot(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            payload_hash=payload_hash, lease_owner=owner, limits=limits,
        )
    assert denied.value.code == "provider_call_limit"
    with engine.begin() as connection:
        row = connection.execute(select(requests).where(requests.c.request_id == request_id)).mappings().one()
    assert row["provider_calls"] == 2
    assert row["lease_owner"] == owner
    assert row["lease_expires_at"] is not None
    child_request_id = str(uuid.uuid4())
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=child_request_id,
        question="internal continuation", limits=None,
    ) is None
    with engine.begin() as connection:
        child = connection.execute(select(requests).where(
            requests.c.request_id == child_request_id,
        )).mappings().one()
    assert child["lease_owner"] is None
    assert child["lease_expires_at"] is None
    with pytest.raises(QuotaExceeded) as in_flight:
        reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=str(uuid.uuid4()),
            question="Another request", limits=limits, lease_owner=str(uuid.uuid4()),
            lease_until=datetime.now(UTC) + timedelta(seconds=45),
        )
    assert in_flight.value.scope == "session_in_flight"
    # Same-ID replay does not create a second turn or reset the durable provider counter.
    with pytest.raises(RequestInProgress):
        reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            question=question, limits=limits, lease_owner=str(uuid.uuid4()),
            lease_until=datetime.now(UTC) + timedelta(seconds=45),
        )
    with engine.begin() as connection:
        assert connection.scalar(select(requests.c.provider_calls).where(
            requests.c.request_id == request_id,
        )) == 2


def test_session_turn_quota_counts_failures_and_uses_half_open_window(engine) -> None:
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_id = _new_session(engine, hotel_id)
    limits = GuestAdmissionLimits(turns_per_session=1, turns_per_hotel=10)
    request_id = str(uuid.uuid4())
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        question="first", limits=limits, lease_owner=str(uuid.uuid4()),
        lease_until=datetime.now(UTC) + timedelta(seconds=45),
    ) is None
    fail_request(
        engine, session_id=session_id, request_id=request_id, code="test_failure",
        trace={"schema_version": 1, "outcome": "error", "failure_stage": "provider",
               "failure_code": "provider_timeout", "elapsed_ms": 81,
               "answer_schema_version": 2, "limits_version": "limits-v1",
               "provider_timeout_ms": 25_000, "turn_timeout_ms": 45_000,
               "max_output_tokens": 700, "context_chars": 1_234,
               "events": [{"stage": "provider", "status": "error", "code": "provider_timeout",
                           "prompt": "must not persist"}],
               "question": "must not persist", "secret": "must not persist"},
    )
    with engine.begin() as connection:
        failure_row = connection.execute(select(requests).where(
            requests.c.request_id == request_id,
        )).mappings().one()
    assert failure_row["response"]["trace"]["failure_code"] == "provider_timeout"
    assert failure_row["response"]["trace"]["answer_schema_version"] == 2
    assert failure_row["response"]["trace"]["limits_version"] == "limits-v1"
    assert failure_row["response"]["trace"]["provider_timeout_ms"] == 25_000
    assert failure_row["response"]["trace"]["turn_timeout_ms"] == 45_000
    assert failure_row["response"]["trace"]["max_output_tokens"] == 700
    assert failure_row["response"]["trace"]["context_chars"] == 1_234
    assert "question" not in failure_row["response"]["trace"]
    assert "secret" not in failure_row["response"]["trace"]
    assert "prompt" not in failure_row["response"]["trace"]["events"][0]
    with pytest.raises(QuotaExceeded) as denied:
        reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=str(uuid.uuid4()),
            question="second", limits=limits, lease_owner=str(uuid.uuid4()),
            lease_until=datetime.now(UTC) + timedelta(seconds=45),
        )
    assert denied.value.scope == "session_turns"


def test_hotel_in_flight_limit_is_serialized_across_sessions(engine) -> None:
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_ids = [_new_session(engine, hotel_id) for _ in range(5)]
    barrier = Barrier(len(session_ids))
    limits = GuestAdmissionLimits(turns_per_hotel=20, in_flight_per_hotel=4)

    def reserve(index: int) -> str:
        barrier.wait()
        try:
            result = reserve_request(
                engine, session_id=session_ids[index], hotel_id=hotel_id,
                request_id=str(uuid.uuid4()), question=f"question {index}", limits=limits,
                lease_owner=str(uuid.uuid4()), lease_until=datetime.now(UTC) + timedelta(seconds=45),
            )
            assert result is None
            return "accepted"
        except QuotaExceeded as exc:
            return exc.scope

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(reserve, range(5)))
    assert results.count("accepted") == 4
    assert results.count("hotel_in_flight") == 1


def test_same_session_concurrent_admissions_allow_only_one_in_flight(engine) -> None:
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_id = _new_session(engine, hotel_id)
    barrier = Barrier(2)
    limits = GuestAdmissionLimits()

    def reserve(index: int) -> str:
        barrier.wait()
        try:
            reserve_request(
                engine, session_id=session_id, hotel_id=hotel_id, request_id=str(uuid.uuid4()),
                question=f"same-session {index}", limits=limits, lease_owner=str(uuid.uuid4()),
                lease_until=datetime.now(UTC) + timedelta(seconds=45),
            )
            return "accepted"
        except QuotaExceeded as exc:
            return exc.scope

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert results.count("accepted") == 1
    assert results.count("session_in_flight") == 1


def test_quota_clock_is_sampled_after_admission_serialization_locks(engine, monkeypatch) -> None:
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_id = _new_session(engine, hotel_id)
    limits = GuestAdmissionLimits(turns_per_session=1, turns_per_hotel=10)
    first_clock_sampled = Event()
    resume_first = Event()
    second_advisory_attempt = Event()
    original_utcnow = store_module.utcnow
    sampled_once = False

    def pause_first_clock_sample():
        nonlocal sampled_once
        value = original_utcnow()
        if current_thread().name == "admission-clock-first" and not sampled_once:
            sampled_once = True
            first_clock_sampled.set()
            if not resume_first.wait(timeout=5):
                raise TimeoutError("test did not release first admission clock")
        return value

    def observe_second_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
        if (current_thread().name == "admission-clock-second"
                and "pg_advisory_xact_lock" in statement):
            second_advisory_attempt.set()

    monkeypatch.setattr(store_module, "utcnow", pause_first_clock_sample)
    event.listen(engine, "before_cursor_execute", observe_second_lock)
    results: dict[str, str] = {}

    def reserve(label: str) -> None:
        request_id = str(uuid.uuid4())
        try:
            reserve_request(
                engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
                question=f"serialized admission {label}", limits=limits,
                lease_owner=str(uuid.uuid4()), lease_until=datetime.now(UTC) + timedelta(seconds=45),
            )
            results[label] = "accepted"
            fail_request(engine, session_id=session_id, request_id=request_id, code="test_finished")
        except QuotaExceeded as exc:
            results[label] = exc.scope

    first = Thread(target=reserve, args=("first",), name="admission-clock-first")
    second = Thread(target=reserve, args=("second",), name="admission-clock-second")
    first.start()
    try:
        assert first_clock_sampled.wait(timeout=3)
        second.start()
        assert second_advisory_attempt.wait(timeout=3)
    finally:
        resume_first.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
        event.remove(engine, "before_cursor_execute", observe_second_lock)

    assert not first.is_alive()
    assert not second.is_alive()
    assert results == {"first": "accepted", "second": "session_turns"}


def test_default_session_and_property_turn_limits_and_property_isolation(engine) -> None:
    limits = GuestAdmissionLimits()
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_id = _new_session(engine, hotel_id)
    for index in range(12):
        request_id = str(uuid.uuid4())
        assert reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            question=f"session turn {index}", limits=limits, lease_owner=str(uuid.uuid4()),
            lease_until=datetime.now(UTC) + timedelta(seconds=45),
        ) is None
        fail_request(engine, session_id=session_id, request_id=request_id, code="completed_test_turn")
    with pytest.raises(QuotaExceeded) as session_denied:
        reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=str(uuid.uuid4()),
            question="session turn thirteen", limits=limits, lease_owner=str(uuid.uuid4()),
            lease_until=datetime.now(UTC) + timedelta(seconds=45),
        )
    assert session_denied.value.scope == "session_turns"

    property_hotel = f"ADMIT-{uuid.uuid4().hex[:12]}"
    for index in range(120):
        property_session = _new_session(engine, property_hotel)
        request_id = str(uuid.uuid4())
        assert reserve_request(
            engine, session_id=property_session, hotel_id=property_hotel, request_id=request_id,
            question=f"property turn {index}", limits=limits, lease_owner=str(uuid.uuid4()),
            lease_until=datetime.now(UTC) + timedelta(seconds=45),
        ) is None
        fail_request(engine, session_id=property_session, request_id=request_id, code="completed_test_turn")
    property_session = _new_session(engine, property_hotel)
    with pytest.raises(QuotaExceeded) as property_denied:
        reserve_request(
            engine, session_id=property_session, hotel_id=property_hotel,
            request_id=str(uuid.uuid4()), question="property turn 121", limits=limits,
            lease_owner=str(uuid.uuid4()), lease_until=datetime.now(UTC) + timedelta(seconds=45),
        )
    assert property_denied.value.scope == "hotel_turns"

    other_hotel = f"ADMIT-{uuid.uuid4().hex[:12]}"
    other_session = _new_session(engine, other_hotel)
    assert reserve_request(
        engine, session_id=other_session, hotel_id=other_hotel, request_id=str(uuid.uuid4()),
        question="isolated property", limits=limits, lease_owner=str(uuid.uuid4()),
        lease_until=datetime.now(UTC) + timedelta(seconds=45),
    ) is None


def test_window_boundary_and_expired_lease_fencing(engine) -> None:
    limits = GuestAdmissionLimits(turns_per_session=1, turns_per_hotel=10)
    base = datetime.now(UTC)
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_id = _new_session(engine, hotel_id)
    old_id = str(uuid.uuid4())
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=old_id,
        question="at boundary", limits=limits, lease_owner=str(uuid.uuid4()),
        lease_until=base + timedelta(seconds=45), now=base - timedelta(seconds=600),
    ) is None
    fail_request(engine, session_id=session_id, request_id=old_id, code="test_failure")
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=str(uuid.uuid4()),
        question="exactly 600 seconds later", limits=limits, lease_owner=str(uuid.uuid4()),
        lease_until=base + timedelta(seconds=45), now=base,
    ) is None

    near_session = _new_session(engine, hotel_id)
    near_id = str(uuid.uuid4())
    assert reserve_request(
        engine, session_id=near_session, hotel_id=hotel_id, request_id=near_id,
        question="inside window", limits=GuestAdmissionLimits(turns_per_session=1, turns_per_hotel=10),
        lease_owner=str(uuid.uuid4()), lease_until=base + timedelta(seconds=45),
        now=base - timedelta(seconds=599, microseconds=999_000),
    ) is None
    fail_request(engine, session_id=near_session, request_id=near_id, code="test_failure")
    with pytest.raises(QuotaExceeded) as inside:
        reserve_request(
            engine, session_id=near_session, hotel_id=hotel_id, request_id=str(uuid.uuid4()),
            question="still inside", limits=GuestAdmissionLimits(turns_per_session=1, turns_per_hotel=10),
            lease_owner=str(uuid.uuid4()), lease_until=base + timedelta(seconds=45), now=base,
        )
    assert inside.value.scope == "session_turns"

    scoped_hotel = f"ADMIT-{uuid.uuid4().hex[:12]}"
    expiring_session = _new_session(engine, scoped_hotel)
    lease_limits = GuestAdmissionLimits(turns_per_session=12, turns_per_hotel=10)
    request_id, owner, question = str(uuid.uuid4()), str(uuid.uuid4()), "expired lease"
    assert reserve_request(
        engine, session_id=expiring_session, hotel_id=scoped_hotel, request_id=request_id,
        question=question, limits=lease_limits, lease_owner=owner,
        lease_until=base + timedelta(seconds=45),
    ) is None
    with engine.begin() as connection:
        connection.execute(update(requests).where(requests.c.request_id == request_id).values(
            lease_expires_at=base - timedelta(seconds=1),
        ))
    with pytest.raises(ProviderCallLimitExceeded) as expired:
        consume_provider_slot(
            engine, session_id=expiring_session, hotel_id=scoped_hotel, request_id=request_id,
            payload_hash=request_payload_hash(question), lease_owner=owner,
        )
    assert expired.value.code == "turn_lease_expired"
    assert reserve_request(
        engine, session_id=expiring_session, hotel_id=scoped_hotel, request_id=str(uuid.uuid4()),
        question="after expired lease", limits=lease_limits, lease_owner=str(uuid.uuid4()),
        lease_until=datetime.now(UTC) + timedelta(seconds=45),
    ) is None


def test_provider_call_count_survives_engine_recreation_and_fences_claims(engine) -> None:
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_id = _new_session(engine, hotel_id)
    request_id, question, owner = str(uuid.uuid4()), "persistent counter", str(uuid.uuid4())
    digest = request_payload_hash(question)
    lease_until = datetime.now(UTC) + timedelta(seconds=45)
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        question=question, limits=GuestAdmissionLimits(), lease_owner=owner, lease_until=lease_until,
    ) is None
    with pytest.raises(ProviderCallLimitExceeded):
        consume_provider_slot(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            payload_hash="0" * 64, lease_owner=owner,
        )
    with pytest.raises(ProviderCallLimitExceeded) as wrong_owner:
        consume_provider_slot(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            payload_hash=digest, lease_owner=str(uuid.uuid4()),
        )
    assert wrong_owner.value.code == "turn_lease_expired"
    with pytest.raises(ProviderCallLimitExceeded):
        consume_provider_slot(
            engine, session_id=str(uuid.uuid4()), hotel_id=hotel_id, request_id=request_id,
            payload_hash=digest, lease_owner=owner,
        )
    with pytest.raises(ProviderCallLimitExceeded):
        consume_provider_slot(
            engine, session_id=session_id, hotel_id=f"OTHER-{hotel_id}", request_id=request_id,
            payload_hash=digest, lease_owner=owner,
        )

    recreated = create_database_engine(TEST_DSN)
    try:
        assert consume_provider_slot(
            recreated, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            payload_hash=digest, lease_owner=owner,
        ) == 1
    finally:
        recreated.dispose()
    recreated_again = create_database_engine(TEST_DSN)
    try:
        assert consume_provider_slot(
            recreated_again, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            payload_hash=digest, lease_owner=owner,
        ) == 2
        with pytest.raises(ProviderCallLimitExceeded):
            consume_provider_slot(
                recreated_again, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
                payload_hash=digest, lease_owner=owner,
            )
    finally:
        recreated_again.dispose()


def test_raw_guest_body_limit_checks_content_length_and_stream_chunks() -> None:
    settings = Settings(environment="test", ai_provider="disabled")
    app = create_app(settings, engine=create_database_engine("sqlite://"))
    client = TestClient(app)
    over_declared = client.post(
        "/v1/guest/sessions/nope/messages", content=b"x" * 65_537,
        headers={"content-type": "application/json"},
    )
    assert over_declared.status_code == 413
    exact = client.post(
        "/v1/guest/sessions/nope/messages", content=b"x" * 65_536,
        headers={"content-type": "application/json"},
    )
    assert exact.status_code != 413

    dispatched = False

    async def downstream(_scope, _receive, _send):
        nonlocal dispatched
        dispatched = True

    middleware = RawRequestBodyLimitMiddleware(downstream, max_bytes=8)
    chunks = [
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"56789", "more_body": False},
    ]
    sent: list[dict[str, object]] = []

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(
        {"type": "http", "path": "/v1/guest/sessions/x/messages", "headers": []},
        receive, send,
    ))
    assert not dispatched
    assert sent[0]["status"] == 413


def test_schema_v7_upgrade_adds_admission_columns_without_losing_requests(engine) -> None:
    hotel_id = f"ADMIT-{uuid.uuid4().hex[:12]}"
    session_id = _new_session(engine, hotel_id)
    request_id = str(uuid.uuid4())
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        question="survive migration",
    ) is None
    with engine.begin() as connection:
        connection.execute(delete(schema_versions).where(schema_versions.c.version == 8))
        connection.execute(text("ALTER TABLE guest_requests DROP COLUMN provider_calls"))
        connection.execute(text("ALTER TABLE guest_requests DROP COLUMN lease_owner"))
        connection.execute(text("ALTER TABLE guest_requests DROP COLUMN lease_expires_at"))
    assert apply_migrations(engine) == 8
    with engine.begin() as connection:
        row = connection.execute(select(requests).where(
            requests.c.request_id == request_id,
        )).mappings().one()
    assert row["payload_hash"] == request_payload_hash("survive migration")
    assert row["provider_calls"] == 0
    assert row["lease_owner"] is None
    assert row["lease_expires_at"] is None
    assert schema_version(engine) == 8
