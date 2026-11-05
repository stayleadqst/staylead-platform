"""B11 guest-session retention contracts against isolated local PostgreSQL."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import and_, delete, event, func, insert, select, update
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    ProviderCallLimitExceeded,
    QuotaExceeded,
    ScopeError,
    apply_guest_brief_patch,
    apply_migrations,
    consume_provider_slot,
    create_session,
    delete_guest_session,
    get_hotel,
    guest_brief_receipts,
    guest_brief_source_utterances,
    guest_briefs,
    guest_language_preferences,
    hotels,
    messages,
    next_session_expiry,
    purge_expired_sessions,
    request_payload_hash,
    requests,
    reserve_request,
    room_advice_results,
    room_advice_selections,
    save_room_advice_result,
    sessions,
)
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import import_fixture_pack
from staylead_platform.platform.contracts.admission import GuestAdmissionLimits
from staylead_platform.platform.contracts.ai_provider import GenerationResult
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefContext,
    ValidatedGuestBriefPatch,
)
from staylead_platform.platform.guest_context.sessions.brief_confirmation import (
    issue_brief_confirmation,
)
from staylead_platform.platform.guest_context.sessions.retention import (
    SESSION_CONTENT_MAX_AGE,
    cleanup_delay_seconds,
)
from staylead_platform.platform.guest_context.sessions.signing import issue_token
from test_b10_trace_postgres import OfflineB10Provider

TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")
SIGNING_SECRET = "b11-offline-test-signing-secret"


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to the isolated Sprint 12 A PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    apply_migrations(database)
    yield database
    database.dispose()


def _token(session_id: str, hotel_id: str, expires_at: datetime) -> str:
    return issue_token(
        secret=SIGNING_SECRET, session_id=session_id, hotel_id=hotel_id,
        expires_at=int(expires_at.timestamp()),
    )


def _session(engine, hotel_id: str, *, expires_at: datetime | None = None) -> str:
    session_id = str(uuid.uuid4())
    create_session(engine, session_id, hotel_id, expires_at or datetime.now(UTC) + timedelta(hours=1))
    return session_id


def _cleanup(engine, hotel_id: str) -> None:
    with engine.begin() as connection:
        for table in (
            messages, guest_briefs, guest_language_preferences, guest_brief_source_utterances,
            guest_brief_receipts, room_advice_selections, room_advice_results, requests, sessions,
        ):
            connection.execute(delete(table).where(table.c.hotel_id == hotel_id))


def test_delete_erases_session_content_but_preserves_recent_property_quota(engine) -> None:
    hotel_id = f"B11-{uuid.uuid4().hex[:12]}"
    session_id = _session(engine, hotel_id)
    request_id = f"client-id-must-not-survive-{uuid.uuid4().hex}"
    limits = GuestAdmissionLimits(turns_per_hotel=1, turns_per_session=12)
    try:
        assert reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            question="Guest message must not survive delete.", limits=limits,
            lease_owner=str(uuid.uuid4()), lease_until=datetime.now(UTC) + timedelta(seconds=45),
        ) is None
        with engine.begin() as connection:
            connection.execute(update(requests).where(requests.c.request_id == request_id).values(
                status="completed", response={"answer": "private response", "trace": {"answer": "private"}},
            ))
            connection.execute(insert(messages).values(
                message_id=str(uuid.uuid4()), session_id=session_id, hotel_id=hotel_id,
                sequence=0, role="user", content="private transcript", created_at=datetime.now(UTC),
                evidence_bindings=[],
            ))
            connection.execute(insert(guest_briefs).values(
                session_id=session_id, hotel_id=hotel_id, brief_version=1,
                data={"party": {"adults": 2}}, pending_fields=[], updated_at=datetime.now(UTC),
            ))
            connection.execute(insert(guest_language_preferences).values(
                session_id=session_id, hotel_id=hotel_id, language_tag="en", source="explicit",
                revision=1, updated_at=datetime.now(UTC),
            ))
            source_id = str(uuid.uuid4())
            connection.execute(insert(guest_brief_source_utterances).values(
                source_utterance_id=source_id, session_id=session_id, hotel_id=hotel_id,
                request_id=request_id, content="private source utterance", fields=["party.adults"],
                created_at=datetime.now(UTC),
            ))
            connection.execute(insert(guest_brief_receipts).values(
                request_id=request_id, session_id=session_id, hotel_id=hotel_id,
                expected_brief_version=0, payload_hash="a" * 64, status="applied",
                brief_version_before=0, brief_version_after=1, applied_delta={"adults": 2},
                source_utterance_id=source_id, source_fields=["party.adults"],
                answer_status="completed", brief_version_used=1, brief_dependent=True,
                answer_payload={"answer": "private derived answer"}, created_at=datetime.now(UTC),
            ))
            result_id = str(uuid.uuid4())
            connection.execute(insert(room_advice_results).values(
                result_id=result_id, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
                result_version=1, session_state_version=1, brief_version=1, source_generation=1,
                config_version="test", policy_version=None, price_version=None,
                algorithm_version="test", dependency_fingerprint="b" * 64,
                source_refs=[{"private": "source ref"}], payload={"private": "advice result"},
                created_at=datetime.now(UTC),
            ))
            connection.execute(insert(room_advice_selections).values(
                session_id=session_id, hotel_id=hotel_id, result_id=result_id, result_version=1,
                option_id="option-private", updated_at=datetime.now(UTC),
            ))

        assert delete_guest_session(engine, session_id=session_id, hotel_id=hotel_id)
        with engine.begin() as connection:
            assert connection.scalar(select(sessions.c.session_id).where(
                sessions.c.session_id == session_id,
            )) is None
            for table in (
                messages, guest_briefs, guest_language_preferences, guest_brief_source_utterances,
                guest_brief_receipts, room_advice_selections, room_advice_results,
            ):
                assert connection.scalar(select(func.count()).select_from(table).where(
                    table.c.session_id == session_id,
                )) == 0
            retained = connection.execute(select(requests).where(
                requests.c.hotel_id == hotel_id,
            )).mappings().one()
            assert retained["request_id"] != request_id
            assert retained["session_id"] != session_id
            assert retained["payload_hash"] == __import__("hashlib").sha256(b"redacted").hexdigest()
            assert retained["response"] is None and retained["error_code"] is None
            assert retained["created_at"] < datetime.now(UTC)

        next_session = _session(engine, hotel_id)
        with pytest.raises(QuotaExceeded) as denied:
            reserve_request(
                engine, session_id=next_session, hotel_id=hotel_id, request_id=str(uuid.uuid4()),
                question="second request", limits=limits, lease_owner=str(uuid.uuid4()),
                lease_until=datetime.now(UTC) + timedelta(seconds=45),
            )
        assert denied.value.scope == "hotel_turns"
    finally:
        _cleanup(engine, hotel_id)


def test_expiry_purge_uses_clock_and_prunes_redacted_reservations_after_window(engine) -> None:
    hotel_id = f"B11-{uuid.uuid4().hex[:12]}"
    created_before = datetime.now(UTC)
    session_id = _session(engine, hotel_id, expires_at=created_before + timedelta(days=3))
    with engine.begin() as connection:
        row = connection.execute(select(sessions).where(sessions.c.session_id == session_id)).mappings().one()
        connection.execute(update(sessions).where(
            sessions.c.session_id == session_id,
        ).values(expires_at=row["created_at"] + timedelta(seconds=2)))
    assert row["expires_at"] == row["created_at"] + SESSION_CONTENT_MAX_AGE
    row = dict(row)
    row["expires_at"] = row["created_at"] + timedelta(seconds=2)
    assert next_session_expiry(engine, hotel_id=hotel_id) == row["expires_at"]
    assert cleanup_delay_seconds(
        now=row["expires_at"] - timedelta(milliseconds=250),
        next_expiry=next_session_expiry(engine, hotel_id=hotel_id),
        maintenance_interval_seconds=60,
    ) == pytest.approx(0.25)
    assert cleanup_delay_seconds(
        now=row["expires_at"], next_expiry=row["expires_at"],
        maintenance_interval_seconds=60,
    ) == 0
    request_id = str(uuid.uuid4())
    assert reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        question="will be redacted", limits=GuestAdmissionLimits(),
        lease_owner=str(uuid.uuid4()), lease_until=datetime.now(UTC) + timedelta(seconds=45),
    ) is None
    with engine.begin() as connection:
        connection.execute(insert(messages).values(
            message_id=str(uuid.uuid4()), session_id=session_id, hotel_id=hotel_id,
            sequence=0, role="user", content="expired transcript", created_at=datetime.now(UTC),
            evidence_bindings=[],
        ))

    assert purge_expired_sessions(engine, now=row["expires_at"] - timedelta(microseconds=1)) == 0
    after_expiry = row["expires_at"] + timedelta(microseconds=1)
    assert purge_expired_sessions(engine, now=after_expiry) == 1
    with engine.begin() as connection:
        assert connection.scalar(select(messages.c.message_id).where(
            messages.c.session_id == session_id,
        )) is None
        retained = connection.execute(select(requests).where(requests.c.hotel_id == hotel_id)).mappings().one()
        assert retained["response"] is None
    assert purge_expired_sessions(engine, now=after_expiry + timedelta(seconds=601)) == 0
    with engine.begin() as connection:
        assert connection.scalar(select(requests.c.request_id).where(
            requests.c.hotel_id == hotel_id,
        )) is None
        orphan_session_id = str(uuid.uuid4())
        connection.execute(insert(guest_language_preferences).values(
            session_id=orphan_session_id, hotel_id=hotel_id, language_tag="fr",
            source="explicit", revision=1, updated_at=datetime.now(UTC) - timedelta(days=8),
        ))
    orphan_cleanup_clock = datetime.now(UTC) + timedelta(days=8)
    # This integration database is shared across tests; the purge return value
    # counts every due session in its global batch, not just this fixture's rows.
    with engine.connect() as connection:
        due_session_count = connection.scalar(select(func.count()).select_from(sessions).where(
            sessions.c.expires_at <= orphan_cleanup_clock,
        ))
    expected_purged = min(int(due_session_count or 0), 100)
    assert purge_expired_sessions(engine, now=orphan_cleanup_clock) == expected_purged
    with engine.begin() as connection:
        assert connection.scalar(select(func.count()).select_from(guest_language_preferences).where(
            guest_language_preferences.c.session_id == orphan_session_id,
        )) == 0
    _cleanup(engine, hotel_id)


def test_room_selection_denies_when_hotel_lock_wait_crosses_expiry(engine) -> None:
    hotel_id = "HTL-CITY01"
    import_fixture_pack(
        engine, Path(__file__).resolve().parents[2] / "fixtures/hospitality/knowledge-v1",
    )
    hotel = get_hotel(engine, hotel_id)
    assert hotel is not None
    session_id = _session(engine, hotel_id)
    result = save_room_advice_result(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=f"expiry-{uuid.uuid4()}",
        payload={"options": [{"option_id": "synthetic-option"}]}, brief_version=0,
        source_generation=hotel["knowledge_generation"], config_version=hotel["config_version"],
        source_refs=[], expected_state_version=0,
    )
    token = _token(session_id, hotel_id, datetime.now(UTC) + timedelta(hours=1))
    expiry = datetime.now(UTC) + timedelta(seconds=2)
    with engine.begin() as connection:
        connection.execute(update(sessions).where(
            sessions.c.session_id == session_id,
        ).values(expires_at=expiry))

    blocker = engine.connect()
    blocker_tx = blocker.begin()
    blocker.execute(select(hotels).where(hotels.c.hotel_id == hotel_id).with_for_update())
    waiting_for_hotel = threading.Event()
    responses: list[Any] = []

    def before_cursor_execute(conn, cursor, statement, params, context, executemany):
        sql = statement.upper()
        if "FROM HOTELS" in sql and "FOR UPDATE" in sql:
            waiting_for_hotel.set()

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    settings = Settings(
        _env_file=None, environment="test", database_url=TEST_DSN or "", ai_provider="disabled",
        session_signing_secret=SecretStr(SIGNING_SECRET),
    )
    try:
        with TestClient(create_app(settings, engine=engine)) as client:
            headers = {"Authorization": f"Bearer {token}"}

            def choose() -> None:
                responses.append(client.post(
                    f"/v1/guest/sessions/{session_id}/room-advice/{result['result_id']}/selection",
                    headers=headers,
                    json={"result_version": result["result_version"], "option_id": "synthetic-option"},
                ))

            worker = threading.Thread(target=choose, daemon=True)
            worker.start()
            assert waiting_for_hotel.wait(3), "selection did not reach the held hotel lock"
            time.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.1)
            blocker_tx.commit()
            blocker.close()
            worker.join(5)
            assert not worker.is_alive(), "selection did not finish after releasing the hotel lock"
            assert responses and responses[0].status_code == 404
        with engine.begin() as connection:
            assert connection.scalar(select(room_advice_selections.c.session_id).where(
                room_advice_selections.c.session_id == session_id,
            )) is None
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
        if blocker_tx.is_active:
            blocker_tx.rollback()
        blocker.close()
        _cleanup(engine, hotel_id)


def test_room_result_commit_denies_when_hotel_lock_wait_crosses_expiry(engine) -> None:
    hotel_id = "HTL-CITY01"
    import_fixture_pack(
        engine, Path(__file__).resolve().parents[2] / "fixtures/hospitality/knowledge-v1",
    )
    hotel = get_hotel(engine, hotel_id)
    assert hotel is not None
    session_id = _session(engine, hotel_id)
    expiry = datetime.now(UTC) + timedelta(seconds=2)
    with engine.begin() as connection:
        connection.execute(update(sessions).where(
            sessions.c.session_id == session_id,
        ).values(expires_at=expiry))

    blocker = engine.connect()
    blocker_tx = blocker.begin()
    blocker.execute(select(hotels).where(hotels.c.hotel_id == hotel_id).with_for_update())
    waiting_for_hotel = threading.Event()
    errors: list[ScopeError] = []
    request_id = f"expiry-{uuid.uuid4()}"

    def before_cursor_execute(conn, cursor, statement, params, context, executemany):
        sql = statement.upper()
        if "FROM HOTELS" in sql and "FOR UPDATE" in sql:
            waiting_for_hotel.set()

    def save() -> None:
        try:
            save_room_advice_result(
                engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
                payload={"options": []}, brief_version=0,
                source_generation=hotel["knowledge_generation"], config_version=hotel["config_version"],
                source_refs=[], expected_state_version=0,
            )
        except ScopeError as exc:
            errors.append(exc)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    worker = threading.Thread(target=save, daemon=True)
    try:
        worker.start()
        assert waiting_for_hotel.wait(3), "result writer did not reach the held hotel lock"
        time.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.1)
        blocker_tx.commit()
        blocker.close()
        worker.join(5)
        assert not worker.is_alive(), "result writer did not finish after releasing the hotel lock"
        assert errors and "expired" in str(errors[0])
        with engine.begin() as connection:
            assert connection.scalar(select(room_advice_results.c.result_id).where(
                room_advice_results.c.request_id == request_id,
            )) is None
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
        if blocker_tx.is_active:
            blocker_tx.rollback()
        blocker.close()
        _cleanup(engine, hotel_id)


def test_guest_brief_commit_denies_when_brief_lock_wait_crosses_expiry(engine) -> None:
    hotel_id = f"B11-{uuid.uuid4().hex[:12]}"
    session_id = _session(engine, hotel_id)
    first_context = GuestBriefContext(
        session_id=session_id, hotel_id=hotel_id, request_id=f"brief-{uuid.uuid4()}",
        expected_brief_version=0, source_utterance_id=str(uuid.uuid4()), source_utterance="initial",
    )
    initial = ValidatedGuestBriefPatch(
        data={"dates": {"check_in": None, "check_out": None, "nights": None},
              "party": {"adults": 2, "children": []}},
        pending_fields=(), applied_delta={"party": {"adults": 2}}, status="applied",
        source_fields=(),
    )
    apply_guest_brief_patch(engine, context=first_context, mutation=initial, payload_hash="a" * 64)
    context = GuestBriefContext(
        session_id=session_id, hotel_id=hotel_id, request_id=f"brief-{uuid.uuid4()}",
        expected_brief_version=1, source_utterance_id=str(uuid.uuid4()), source_utterance="late update",
    )
    mutation = ValidatedGuestBriefPatch(
        data={**initial.data, "party": {"adults": 3, "children": []}},
        pending_fields=(), applied_delta={"party": {"adults": 3}}, status="applied",
        source_fields=("party.adults",),
    )
    expiry = datetime.now(UTC) + timedelta(seconds=2)
    with engine.begin() as connection:
        connection.execute(update(sessions).where(
            sessions.c.session_id == session_id,
        ).values(expires_at=expiry))

    blocker = engine.connect()
    blocker_tx = blocker.begin()
    blocker.execute(select(guest_briefs).where(and_(
        guest_briefs.c.session_id == session_id, guest_briefs.c.hotel_id == hotel_id,
    )).with_for_update())
    waiting_for_brief = threading.Event()
    errors: list[ScopeError] = []

    def before_cursor_execute(conn, cursor, statement, params, context, executemany):
        sql = statement.upper()
        if "FROM GUEST_BRIEFS" in sql and "FOR UPDATE" in sql:
            waiting_for_brief.set()

    def apply() -> None:
        try:
            apply_guest_brief_patch(
                engine, context=context, mutation=mutation, payload_hash="b" * 64,
            )
        except ScopeError as exc:
            errors.append(exc)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    worker = threading.Thread(target=apply, daemon=True)
    try:
        worker.start()
        assert waiting_for_brief.wait(3), "brief writer did not reach the held brief lock"
        time.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.1)
        blocker_tx.commit()
        blocker.close()
        worker.join(5)
        assert not worker.is_alive(), "brief writer did not finish after releasing the brief lock"
        assert errors and "expired" in str(errors[0])
        with engine.begin() as connection:
            version = connection.scalar(select(guest_briefs.c.brief_version).where(
                guest_briefs.c.session_id == session_id,
            ))
            assert version == 1
            assert connection.scalar(select(guest_brief_receipts.c.request_id).where(
                guest_brief_receipts.c.request_id == context.request_id,
            )) is None
            assert connection.scalar(select(guest_brief_source_utterances.c.source_utterance_id).where(
                guest_brief_source_utterances.c.request_id == context.request_id,
            )) is None
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
        if blocker_tx.is_active:
            blocker_tx.rollback()
        blocker.close()
        _cleanup(engine, hotel_id)


def test_expired_session_cannot_consume_provider_slot(engine) -> None:
    hotel_id = f"B11-{uuid.uuid4().hex[:12]}"
    session_id = _session(engine, hotel_id)
    request_id = str(uuid.uuid4())
    lease_owner = str(uuid.uuid4())
    try:
        assert reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            question="do not dispatch after expiry", limits=GuestAdmissionLimits(),
            lease_owner=lease_owner, lease_until=datetime.now(UTC) + timedelta(seconds=45),
        ) is None
        with engine.begin() as connection:
            connection.execute(update(sessions).where(
                sessions.c.session_id == session_id,
            ).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))

        with pytest.raises(ProviderCallLimitExceeded):
            consume_provider_slot(
                engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
                payload_hash=request_payload_hash("do not dispatch after expiry"),
                lease_owner=lease_owner,
            )
        with engine.begin() as connection:
            assert connection.scalar(select(requests.c.provider_calls).where(
                requests.c.request_id == request_id,
            )) == 0
    finally:
        _cleanup(engine, hotel_id)


def test_delete_during_inflight_offline_turn_prevents_late_content_commit(engine) -> None:
    class PausingOfflineProvider(OfflineB10Provider):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()

        async def generate(self, request):
            self.started.set()
            await asyncio.to_thread(self.release.wait, 5)
            result = await super().generate(request)
            payload = json.loads(result.text)
            payload["explicit_language_tag"] = "fr"
            payload["inferred_language_tag"] = None
            return GenerationResult(
                text=json.dumps(payload), provider=result.provider, deployment=result.deployment,
                model=result.model, request_id=result.request_id, usage=result.usage,
            )

    hotel_id = "HTL-CITY01"
    import_fixture_pack(
        engine, Path(__file__).resolve().parents[2] / "fixtures/hospitality/knowledge-v1",
    )
    provider = PausingOfflineProvider()
    settings = Settings(
        _env_file=None, environment="test", database_url=TEST_DSN or "", ai_provider="disabled",
        session_signing_secret=SecretStr(SIGNING_SECRET),
    )
    session_id = _session(engine, hotel_id)
    token = _token(session_id, hotel_id, datetime.now(UTC) + timedelta(hours=1))
    headers = {"Authorization": f"Bearer {token}"}
    request_id = f"inflight-{uuid.uuid4()}"
    response_holder: list[Any] = []
    try:
        with TestClient(create_app(settings, engine=engine, provider=provider)) as client:
            def send_turn() -> None:
                response_holder.append(client.post(
                    f"/v1/guest/sessions/{session_id}/messages", headers=headers,
                    json={"request_id": request_id,
                          "question": "Please answer in French. What are the breakfast hours?"},
                ))

            worker = threading.Thread(target=send_turn, daemon=True)
            worker.start()
            assert provider.started.wait(timeout=3), "offline provider did not reach its bounded pause"
            deleted = client.delete(f"/v1/guest/sessions/{session_id}", headers=headers)
            assert deleted.status_code == 204
            provider.release.set()
            worker.join(timeout=7)
            assert not worker.is_alive(), "in-flight HTTP request did not finish after provider release"
            assert response_holder and response_holder[0].status_code != 200
            assert provider.calls == 1
        with engine.begin() as connection:
            assert connection.scalar(select(sessions.c.session_id).where(
                sessions.c.session_id == session_id,
            )) is None
            assert connection.scalar(select(func.count()).select_from(messages).where(
                messages.c.session_id == session_id,
            )) == 0
            assert connection.scalar(select(func.count()).select_from(guest_language_preferences).where(
                guest_language_preferences.c.session_id == session_id,
            )) == 0
            assert connection.scalar(select(requests.c.request_id).where(
                requests.c.session_id == session_id,
            )) is None
    finally:
        provider.release.set()
        _cleanup(engine, hotel_id)


def test_concurrent_delete_and_expiry_cleanup_copy_recent_quota_once(engine) -> None:
    for compete_with_purge in (False, True):
        hotel_id = f"B11-{uuid.uuid4().hex[:12]}"
        session_id = _session(engine, hotel_id)
        request_id = str(uuid.uuid4())
        assert reserve_request(
            engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
            question="quota reservation", limits=GuestAdmissionLimits(),
            lease_owner=str(uuid.uuid4()), lease_until=datetime.now(UTC) + timedelta(seconds=45),
        ) is None
        if compete_with_purge:
            with engine.begin() as connection:
                connection.execute(update(sessions).where(
                    sessions.c.session_id == session_id,
                ).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))

        # If cleanup is not serialized before the redaction read, synchronize both
        # transactions after they have selected the same original quota row.
        read_barrier = threading.Barrier(2)
        recent_reads: list[int] = []

        def after_cursor_execute(
            conn, cursor, statement, params, context, executemany,
            recent_reads=recent_reads, read_barrier=read_barrier,
        ):
            if statement.lstrip().startswith("SELECT guest_requests.created_at"):
                recent_reads.append(threading.get_ident())
                try:
                    read_barrier.wait(timeout=0.5)
                except threading.BrokenBarrierError:
                    pass

        event.listen(engine, "after_cursor_execute", after_cursor_execute)
        results: list[Any] = []

        def delete_session(session_id=session_id, hotel_id=hotel_id, results=results) -> None:
            results.append(delete_guest_session(engine, session_id=session_id, hotel_id=hotel_id))

        def purge_sessions(results=results) -> None:
            results.append(purge_expired_sessions(engine, now=datetime.now(UTC)))

        workers = [threading.Thread(target=delete_session, daemon=True)]
        workers.append(threading.Thread(
            target=purge_sessions if compete_with_purge else delete_session, daemon=True,
        ))
        try:
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=5)
            assert all(not worker.is_alive() for worker in workers), "cleanup worker did not finish"
            assert len(results) == 2
            with engine.begin() as connection:
                assert connection.scalar(select(func.count()).select_from(sessions).where(
                    sessions.c.session_id == session_id,
                )) == 0
                assert connection.scalar(select(func.count()).select_from(requests).where(
                    requests.c.hotel_id == hotel_id,
                )) == 1
            assert len(recent_reads) == 1
        finally:
            event.remove(engine, "after_cursor_execute", after_cursor_execute)
            _cleanup(engine, hotel_id)


def test_delete_endpoint_accepts_expired_own_token_and_rejects_mismatch_without_write(engine) -> None:
    hotel_id = f"B11-{uuid.uuid4().hex[:12]}"
    session_id = _session(engine, hotel_id)
    other_session = _session(engine, hotel_id)
    now = datetime.now(UTC)
    expired_own_token = _token(session_id, hotel_id, now - timedelta(seconds=1))
    live_old_token = _token(session_id, hotel_id, now + timedelta(hours=1))
    other_token = _token(other_session, hotel_id, now + timedelta(hours=1))
    cross_property_token = _token(session_id, f"foreign-{hotel_id}", now + timedelta(hours=1))
    confirmation_token, _ = issue_brief_confirmation(
        secret=SIGNING_SECRET, session_id=session_id, hotel_id=hotel_id,
        request_id="original-confirmation", source_utterance_id="source-utterance",
        question="remember my dates", expected_brief_version=0,
        operations=(), turn_intents=(), authorized_targets=(), selected_fact_ids=(), changes=(),
        validated_patch=ValidatedGuestBriefPatch(
            data={}, pending_fields=(), applied_delta={}, status="applied", source_fields=(),
        ),
    )
    settings = Settings(
        _env_file=None, environment="test", database_url=TEST_DSN or "",
        session_signing_secret=SecretStr(SIGNING_SECRET),
    )
    try:
        with TestClient(create_app(settings, engine=engine)) as client:
            missing_auth = client.delete(f"/v1/guest/sessions/{session_id}")
            assert missing_auth.status_code == 401
            cross_property = client.delete(
                f"/v1/guest/sessions/{session_id}",
                headers={"Authorization": f"Bearer {cross_property_token}"},
            )
            assert cross_property.status_code == 403
            path_mismatch = client.delete(
                f"/v1/guest/sessions/{session_id}",
                headers={"Authorization": f"Bearer {other_token}"},
            )
            assert path_mismatch.status_code == 403
            with engine.begin() as connection:
                assert connection.scalar(select(sessions.c.session_id).where(
                    sessions.c.session_id == session_id,
                )) == session_id
            deleted = client.delete(
                f"/v1/guest/sessions/{session_id}",
                headers={"Authorization": f"Bearer {expired_own_token}"},
            )
            assert deleted.status_code == 204
            assert deleted.headers["cache-control"] == "no-store"
            repeated = client.delete(
                f"/v1/guest/sessions/{session_id}",
                headers={"Authorization": f"Bearer {expired_own_token}"},
            )
            assert repeated.status_code == 204
            mismatch = client.delete(
                f"/v1/guest/sessions/{session_id}",
                headers={"Authorization": f"Bearer {other_token}"},
            )
            assert mismatch.status_code == 403
            headers = {"Authorization": f"Bearer {live_old_token}"}
            old_token_reads = [
                client.post(f"/v1/guest/sessions/{session_id}/messages", headers=headers,
                            json={"request_id": "replay-after-delete", "question": "old content"}),
                client.post(f"/v1/guest/sessions/{session_id}/freshness", headers=headers,
                            json={"request_id": "freshness-after-delete"}),
                client.post(f"/v1/guest/sessions/{session_id}/brief-confirmations", headers=headers,
                            json={"request_id": "confirmation-after-delete",
                                  "confirmation_token": confirmation_token}),
                client.get(f"/v1/guest/sessions/{session_id}/room-advice", headers=headers),
                client.post(f"/v1/guest/sessions/{session_id}/room-advice/{uuid.uuid4()}/selection",
                            headers=headers, json={"result_version": 1, "option_id": "old"}),
                client.get(f"/v1/guest/sessions/{session_id}/media/OLD?generation=1&source_id=x"
                           "&source_version=x&source_hash=x&sha256=x", headers=headers),
            ]
            assert [response.status_code for response in old_token_reads] == [401] * len(old_token_reads)
        with engine.begin() as connection:
            assert connection.scalar(select(sessions.c.session_id).where(
                sessions.c.session_id == session_id,
            )) is None
            assert connection.scalar(select(sessions.c.session_id).where(
                sessions.c.session_id == other_session,
            )) == other_session
    finally:
        _cleanup(engine, hotel_id)
