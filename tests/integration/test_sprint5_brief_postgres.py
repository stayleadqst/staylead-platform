"""Sprint 5 brief persistence contracts on a dedicated PostgreSQL database."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    IdempotencyConflict,
    ScopeError,
    VersionConflict,
    apply_guest_brief_patch,
    apply_migrations,
    complete_partial_request,
    complete_request,
    create_session,
    fail_request,
    get_guest_brief,
    get_guest_brief_receipt,
    get_guest_brief_source_utterance,
    get_session,
    knowledge_sources,
    reserve_request,
    save_bootstrap,
    schema_version,
)
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefContext,
    ValidatedGuestBriefPatch,
)

TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to an isolated Sprint 5 PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    apply_migrations(database)
    yield database
    database.dispose()


def _context(session_id: str, hotel_id: str, request_id: str, version: int,
             source_id: str | None = None) -> GuestBriefContext:
    return GuestBriefContext(
        session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        expected_brief_version=version, source_utterance_id=source_id or str(uuid.uuid4()),
        source_utterance="Add one child, age 9, and check breakfast hours.",
    )


def test_brief_receipt_source_utterance_partial_failure_and_same_id_replay(engine) -> None:
    session_id, hotel_id, request_id = str(uuid.uuid4()), f"HTL-{uuid.uuid4().hex[:12]}", str(uuid.uuid4())
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    context = _context(session_id, hotel_id, request_id, 0)
    mutation = ValidatedGuestBriefPatch(
        data={"dates": {"check_in": "2027-05-10", "check_out": "2027-05-13", "nights": 3},
              "party": {"adults": 2, "children": [{"member_id": str(uuid.uuid4()), "age": 9}]}},
        pending_fields=(),
        applied_delta={"party": {"adults": 2, "children_added": [{"age": 9}]}},
        status="applied", source_fields=("dates.check_in", "dates.check_out", "party.adults", "party.children"),
    )
    reserved = reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        question=context.source_utterance,
    )
    assert reserved is None
    result = apply_guest_brief_patch(
        engine, context=context, mutation=mutation, payload_hash="a" * 64,
    )
    assert result.brief.brief_version == 1
    assert result.receipt.brief_version_after == 1
    source = get_guest_brief_source_utterance(
        engine, session_id=session_id, hotel_id=hotel_id, receipt_id=request_id,
    )
    assert source and source["content"] == context.source_utterance
    assert source["source_utterance_id"] == context.source_utterance_id

    partial = {
        "request_id": request_id, "status": "partial_success",
        "error": {"code": "provider_failure", "message": "The answer was not completed."},
        "guest_brief": {"brief_version": 1, "data": mutation.data, "pending_fields": []},
        "brief_receipt": {"request_id": request_id, "status": "applied",
                          "brief_version_before": 0, "brief_version_after": 1,
                          "applied_delta": mutation.applied_delta},
        "applied_delta": mutation.applied_delta, "answer_status": "failed",
        "brief_version_used": 1, "brief_dependent": True,
    }
    stored_partial = complete_partial_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        response=partial, brief_version_used=1,
    )
    assert stored_partial["guest_brief"]["dates"] == mutation.data["dates"]
    assert "data" not in stored_partial["guest_brief"]
    assert stored_partial["brief_receipt"]["source_refs"][0]["source_utterance_id"] == context.source_utterance_id
    replay = reserve_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        question=context.source_utterance,
    )
    assert replay["status"] == "partial_success"
    assert replay["answer_status"] == "failed"
    assert replay["applied_delta"] == mutation.applied_delta
    assert get_guest_brief(engine, session_id=session_id, hotel_id=hotel_id).brief_version == 1
    stored = get_guest_brief_receipt(
        engine, session_id=session_id, hotel_id=hotel_id, receipt_id=request_id,
    )
    assert stored and stored["receipt"].answer_status == "failed"

    same_request = apply_guest_brief_patch(
        engine, context=context, mutation=mutation, payload_hash="a" * 64,
    )
    assert same_request.replayed is True
    assert same_request.brief.brief_version == 1
    with pytest.raises(IdempotencyConflict):
        apply_guest_brief_patch(engine, context=context, mutation=mutation, payload_hash="b" * 64)


def test_same_id_replay_recovers_committed_receipt_after_lost_apply_ack(engine) -> None:
    session_id, hotel_id, request_id = str(uuid.uuid4()), f"HTL-{uuid.uuid4().hex[:12]}", str(uuid.uuid4())
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    context = _context(session_id, hotel_id, request_id, 0)
    assert reserve_request(engine, session_id=session_id, hotel_id=hotel_id,
                           request_id=request_id, question=context.source_utterance) is None
    mutation = ValidatedGuestBriefPatch(
        data={"dates": {"check_in": None, "check_out": None, "nights": None},
              "party": {"adults": 2, "children": []}},
        pending_fields=(), applied_delta={"party": {"adults": 2}},
        status="applied", source_fields=("party.adults",),
    )
    apply_guest_brief_patch(engine, context=context, mutation=mutation, payload_hash="e" * 64)
    # Simulate a lost commit acknowledgement followed by generic request cleanup.
    fail_request(engine, session_id=session_id, request_id=request_id,
                 code="brief_apply_outcome_unknown")
    replay = reserve_request(engine, session_id=session_id, hotel_id=hotel_id,
                             request_id=request_id, question=context.source_utterance)
    assert replay["status"] == "partial_success"
    assert replay["answer_status"] == "failed"
    assert replay["guest_brief"]["party"] == {"adults": 2, "children": []}
    assert replay["brief_receipt"]["source_refs"][0]["source_utterance_id"] == context.source_utterance_id
    assert get_guest_brief(engine, session_id=session_id, hotel_id=hotel_id).brief_version == 1


def test_unknown_apply_outcome_is_terminal_when_no_effect_is_durable(engine) -> None:
    no_receipt_session, hotel_id, no_receipt_id = (
        str(uuid.uuid4()), f"HTL-{uuid.uuid4().hex[:12]}", str(uuid.uuid4()),
    )
    create_session(engine, no_receipt_session, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    no_receipt_context = _context(no_receipt_session, hotel_id, no_receipt_id, 0)
    assert reserve_request(engine, session_id=no_receipt_session, hotel_id=hotel_id,
                           request_id=no_receipt_id, question=no_receipt_context.source_utterance) is None
    fail_request(engine, session_id=no_receipt_session, request_id=no_receipt_id,
                 code="brief_apply_outcome_unknown")
    with pytest.raises(RuntimeError, match="brief_apply_no_effect"):
        reserve_request(
            engine, session_id=no_receipt_session, hotel_id=hotel_id,
            request_id=no_receipt_id, question=no_receipt_context.source_utterance,
        )
    with pytest.raises(RuntimeError, match="brief_apply_no_effect"):
        reserve_request(
            engine, session_id=no_receipt_session, hotel_id=hotel_id,
            request_id=no_receipt_id, question=no_receipt_context.source_utterance,
        )

    unchanged_session, unchanged_id = str(uuid.uuid4()), str(uuid.uuid4())
    create_session(engine, unchanged_session, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    unchanged_context = _context(unchanged_session, hotel_id, unchanged_id, 0)
    assert reserve_request(engine, session_id=unchanged_session, hotel_id=hotel_id,
                           request_id=unchanged_id, question=unchanged_context.source_utterance) is None
    no_change = ValidatedGuestBriefPatch(
        data={"dates": {"check_in": None, "check_out": None, "nights": None},
              "party": {"adults": None, "children": []}},
        pending_fields=(), applied_delta={}, status="no_change", source_fields=(),
    )
    stored = apply_guest_brief_patch(
        engine, context=unchanged_context, mutation=no_change, payload_hash="g" * 64,
    )
    assert stored.receipt.brief_version_before == stored.receipt.brief_version_after == 0
    fail_request(engine, session_id=unchanged_session, request_id=unchanged_id,
                 code="brief_apply_outcome_unknown")
    with pytest.raises(RuntimeError, match="brief_apply_no_effect"):
        reserve_request(
            engine, session_id=unchanged_session, hotel_id=hotel_id,
            request_id=unchanged_id, question=unchanged_context.source_utterance,
        )


def test_brief_cas_scope_and_atomic_rollback_on_duplicate_source_id(engine) -> None:
    session_id, hotel_id = str(uuid.uuid4()), f"HTL-{uuid.uuid4().hex[:12]}"
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    context = _context(session_id, hotel_id, str(uuid.uuid4()), 0)
    mutation = ValidatedGuestBriefPatch(
        data={"dates": {"check_in": None, "check_out": None, "nights": None},
              "party": {"adults": 2, "children": []}},
        pending_fields=(), applied_delta={"party": {"adults": 2}},
        status="applied", source_fields=("party.adults",),
    )
    apply_guest_brief_patch(engine, context=context, mutation=mutation, payload_hash="c" * 64)
    other = _context(session_id, hotel_id, str(uuid.uuid4()), 1, context.source_utterance_id)
    changed_again = ValidatedGuestBriefPatch(
        data={**mutation.data, "party": {"adults": 3, "children": []}},
        pending_fields=(), applied_delta={"party": {"adults": 3}},
        status="applied", source_fields=("party.adults",),
    )
    with pytest.raises(IntegrityError):
        apply_guest_brief_patch(engine, context=other, mutation=changed_again, payload_hash="d" * 64)
    assert get_guest_brief(engine, session_id=session_id, hotel_id=hotel_id).brief_version == 1
    with pytest.raises(VersionConflict):
        apply_guest_brief_patch(
            engine, context=_context(session_id, hotel_id, str(uuid.uuid4()), 0),
            mutation=changed_again, payload_hash="e" * 64,
        )
    with pytest.raises(ScopeError):
        get_guest_brief(engine, session_id=session_id, hotel_id="HTL-WRONG")


def test_concurrent_brief_writes_have_one_cas_winner(engine) -> None:
    session_id, hotel_id = str(uuid.uuid4()), f"HTL-{uuid.uuid4().hex[:12]}"
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    barrier = Barrier(2)

    def write(adults: int) -> str:
        context = _context(session_id, hotel_id, str(uuid.uuid4()), 0)
        mutation = ValidatedGuestBriefPatch(
            data={"dates": {"check_in": None, "check_out": None, "nights": None},
                  "party": {"adults": adults, "children": []}},
            pending_fields=(), applied_delta={"party": {"adults": adults}},
            status="applied", source_fields=("party.adults",),
        )
        barrier.wait()
        try:
            apply_guest_brief_patch(engine, context=context, mutation=mutation,
                                    payload_hash=f"{adults:064d}")
            return "applied"
        except VersionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, (2, 3)))
    assert sorted(outcomes) == ["applied", "conflict"]
    assert get_guest_brief(engine, session_id=session_id, hotel_id=hotel_id).brief_version == 1


def test_deadline_cancellation_rolls_back_before_brief_commit(engine) -> None:
    session_id, hotel_id = str(uuid.uuid4()), f"HTL-{uuid.uuid4().hex[:12]}"
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    context = _context(session_id, hotel_id, str(uuid.uuid4()), 0)
    mutation = ValidatedGuestBriefPatch(
        data={"dates": {"check_in": None, "check_out": None, "nights": None},
              "party": {"adults": 2, "children": []}},
        pending_fields=(), applied_delta={"party": {"adults": 2}},
        status="applied", source_fields=("party.adults",),
    )
    cancelled = Event()
    cancelled.set()
    with pytest.raises(TimeoutError):
        apply_guest_brief_patch(
            engine, context=context, mutation=mutation, payload_hash="f" * 64,
            deadline_monotonic=10**12, cancellation_event=cancelled,
        )
    assert get_guest_brief(engine, session_id=session_id, hotel_id=hotel_id).brief_version == 0
    assert get_guest_brief_source_utterance(
        engine, session_id=session_id, hotel_id=hotel_id, receipt_id=context.request_id,
    ) is None


def test_completed_brief_dependent_replay_is_marked_stale_after_later_edit(engine) -> None:
    session_id, hotel_id = str(uuid.uuid4()), f"HTL-{uuid.uuid4().hex[:12]}"
    save_bootstrap(engine, hotel_id=hotel_id, slug=f"brief-{uuid.uuid4().hex[:12]}",
                   config_version="v1", public_config={}, synthetic=True, facts=[])
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    first_id = str(uuid.uuid4())
    original_question = "How many nights is this stay?"
    assert reserve_request(engine, session_id=session_id, hotel_id=hotel_id,
                           request_id=first_id, question=original_question) is None
    apply_guest_brief_patch(
        engine, context=GuestBriefContext(
            session_id=session_id, hotel_id=hotel_id, request_id=first_id,
            expected_brief_version=0, source_utterance_id=str(uuid.uuid4()),
            source_utterance=original_question,
        ),
        mutation=ValidatedGuestBriefPatch(
            data={"dates": {"check_in": "2027-05-10", "check_out": "2027-05-13", "nights": 3},
                  "party": {"adults": 2, "children": []}},
            pending_fields=(), applied_delta={"dates": {"check_in": "2027-05-10",
                                                           "check_out": "2027-05-13", "nights": 3}},
            status="applied", source_fields=("dates.check_in", "dates.check_out"),
        ), payload_hash="1" * 64,
    )
    completed = complete_request(
        engine, session_id=session_id, hotel_id=hotel_id, request_id=first_id,
        question=original_question, answer="This stay is 3 nights.", evidence=[],
        brief_version_used=1, brief_dependent=True,
    )
    assert completed["brief_receipt"]["answer_status"] == "completed"
    assert completed["guest_brief"]["brief_version"] == 1

    second_id = str(uuid.uuid4())
    second_question = "Change checkout to May 15, 2027."
    assert reserve_request(engine, session_id=session_id, hotel_id=hotel_id,
                           request_id=second_id, question=second_question) is None
    apply_guest_brief_patch(
        engine, context=GuestBriefContext(
            session_id=session_id, hotel_id=hotel_id, request_id=second_id,
            expected_brief_version=1, source_utterance_id=str(uuid.uuid4()),
            source_utterance=second_question,
        ),
        mutation=ValidatedGuestBriefPatch(
            data={"dates": {"check_in": "2027-05-10", "check_out": "2027-05-15", "nights": 5},
                  "party": {"adults": 2, "children": []}},
            pending_fields=(), applied_delta={"dates": {"check_out": "2027-05-15", "nights": 5}},
            status="applied", source_fields=("dates.check_out",),
        ), payload_hash="2" * 64,
    )
    replay = reserve_request(engine, session_id=session_id, hotel_id=hotel_id,
                             request_id=first_id, question=original_question)
    assert replay["brief_narrative_stale"] is True
    assert replay["brief_freshness"] == "stale"
    assert replay["brief_receipt"]["status"] == "applied"
    assert replay["brief_receipt"]["brief_version_after"] == 1
    assert replay["guest_brief"]["brief_version"] == 2


def test_schema_four_upgrade_preserves_existing_session_and_source(engine) -> None:
    hotel_id = f"HTL-{uuid.uuid4().hex[:12]}"
    session_id = str(uuid.uuid4())
    source_id = f"SRC-{uuid.uuid4().hex[:12]}"
    save_bootstrap(
        engine, hotel_id=hotel_id, slug=f"upgrade-{uuid.uuid4().hex[:12]}",
        config_version="v1", public_config={}, synthetic=True, facts=[],
        sources=[{
            "source_id": source_id, "version": "1", "scope": "guest",
            "guest_approved": True, "valid_from": "2026-01-01", "valid_to": "9999-12-31",
        }],
    )
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=2))
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE guest_brief_receipts")
        connection.exec_driver_sql("DROP TABLE guest_brief_source_utterances")
        connection.exec_driver_sql("DROP TABLE guest_briefs")
        connection.exec_driver_sql("DELETE FROM schema_versions WHERE version > 4")
    assert schema_version(engine) == 4
    assert apply_migrations(engine) == 7
    assert schema_version(engine) == 7
    assert get_guest_brief(engine, session_id=session_id, hotel_id=hotel_id).brief_version == 0
    assert get_session(engine, session_id)["hotel_id"] == hotel_id
    with engine.connect() as connection:
        assert connection.scalar(select(knowledge_sources.c.source_id).where(
            knowledge_sources.c.source_id == source_id,
        )) == source_id
