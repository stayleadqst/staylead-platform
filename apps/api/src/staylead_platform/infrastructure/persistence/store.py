"""PostgreSQL persistence for versioned hotel knowledge and anonymous guest sessions."""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import UTC, datetime
from threading import Event
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

metadata = MetaData()
CURRENT_SCHEMA_VERSION = 2
schema_versions = Table(
    "schema_versions", metadata,
    Column("version", Integer, primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)
hotels = Table(
    "hotels", metadata,
    Column("hotel_id", String(80), primary_key=True),
    Column("slug", String(120), nullable=False, unique=True),
    Column("config_version", String(80), nullable=False),
    Column("public_config", JSON, nullable=False),
    Column("synthetic", Boolean, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
knowledge_facts = Table(
    "knowledge_facts", metadata,
    Column("fact_id", String(120), primary_key=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("source_id", String(120), nullable=False),
    Column("source_version", String(80), nullable=False),
    Column("section", String(240), nullable=False),
    Column("fact_version", String(80), nullable=False),
    Column("status", String(40), nullable=False),
    Column("valid_from", String(20), nullable=False),
    Column("valid_to", String(20), nullable=False),
    Column("fact", JSON, nullable=False),
    Column("imported_at", DateTime(timezone=True), nullable=False),
)
sessions = Table(
    "guest_sessions", metadata,
    Column("session_id", String(36), primary_key=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("state_version", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
requests = Table(
    "guest_requests", metadata,
    Column("request_id", String(128), primary_key=True),
    Column("session_id", String(36), nullable=False, index=True),
    Column("hotel_id", String(80), nullable=False),
    Column("expected_version", Integer, nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("status", String(20), nullable=False),
    Column("response", JSON),
    Column("error_code", String(60)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
messages = Table(
    "guest_messages", metadata,
    Column("message_id", String(36), primary_key=True),
    Column("session_id", String(36), nullable=False, index=True),
    Column("hotel_id", String(80), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("role", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("session_id", "sequence", name="uq_guest_messages_sequence"),
)


class ScopeError(ValueError):
    pass


class VersionConflict(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


class RequestInProgress(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def set_transaction_timeout(connection: Any, timeout_seconds: float | None) -> None:
    """Bound PostgreSQL statements and lock waits to the caller's remaining turn time."""
    if timeout_seconds is None:
        return
    milliseconds = max(1, int(timeout_seconds * 1000))
    value = f"{milliseconds}ms"
    connection.execute(text("SELECT set_config('statement_timeout', :value, true)"), {"value": value})
    connection.execute(text("SELECT set_config('lock_timeout', :value, true)"), {"value": value})


def refresh_transaction_deadline(
    connection: Any, deadline_monotonic: float | None, cancellation_event: Event | None,
) -> None:
    if cancellation_event is not None and cancellation_event.is_set():
        raise TimeoutError("The guest turn was cancelled before commit.")
    if deadline_monotonic is not None:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The guest turn deadline expired before commit.")
        set_transaction_timeout(connection, remaining)


def apply_migrations(engine: Engine) -> int:
    """Explicit migration entry point. App construction/startup never calls this."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("StayLead migrations require PostgreSQL.")
    metadata.create_all(engine)
    with engine.begin() as connection:
        existing = connection.scalar(select(schema_versions.c.version).order_by(schema_versions.c.version.desc()).limit(1))
        if existing is None:
            connection.execute(insert(schema_versions).values(version=1, applied_at=utcnow()))
            existing = 1
        if existing > CURRENT_SCHEMA_VERSION:
            raise RuntimeError("Unsupported database schema version.")
        if existing < 2:
            columns = {column["name"] for column in inspect(connection).get_columns("guest_requests")}
            if "expected_version" not in columns:
                connection.execute(text(
                    "ALTER TABLE guest_requests ADD COLUMN expected_version INTEGER NOT NULL DEFAULT 0"
                ))
            connection.execute(insert(schema_versions).values(version=2, applied_at=utcnow()))
    return CURRENT_SCHEMA_VERSION


def schema_version(engine: Engine) -> int | None:
    with engine.connect() as connection:
        if not inspect(connection).has_table("schema_versions"):
            return None
        return connection.scalar(select(schema_versions.c.version).order_by(schema_versions.c.version.desc()).limit(1))


def save_bootstrap(
    engine: Engine,
    *,
    hotel_id: str,
    slug: str,
    config_version: str,
    public_config: dict[str, Any],
    synthetic: bool,
    facts: list[dict[str, Any]],
) -> int:
    now = utcnow()
    with engine.begin() as connection:
        connection.execute(
            hotels.delete().where(hotels.c.hotel_id == hotel_id)
        )
        connection.execute(
            insert(hotels).values(
                hotel_id=hotel_id, slug=slug, config_version=config_version,
                public_config=public_config, synthetic=synthetic, updated_at=now,
            )
        )
        connection.execute(knowledge_facts.delete().where(knowledge_facts.c.hotel_id == hotel_id))
        if facts:
            connection.execute(insert(knowledge_facts), facts)
    return len(facts)


def get_hotel_by_slug(engine: Engine, slug: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(select(hotels).where(hotels.c.slug == slug)).mappings().first()
    return dict(row) if row else None


def get_hotel(engine: Engine, hotel_id: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(select(hotels).where(hotels.c.hotel_id == hotel_id)).mappings().first()
    return dict(row) if row else None


def facts_for_hotel(engine: Engine, hotel_id: str, *, limit: int = 400) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(knowledge_facts)
            .where(and_(knowledge_facts.c.hotel_id == hotel_id, knowledge_facts.c.status.in_([
                "confirmed", "unknown", "needs_confirmation",
            ])))
            .limit(limit)
        ).mappings().all()
    return [dict(row["fact"]) | {"provenance": {
        "source_id": row["source_id"], "source_version": row["source_version"],
        "section": row["section"], "fact_version": row["fact_version"],
        "imported_at": row["imported_at"].isoformat(),
    }} for row in rows]


def create_session(engine: Engine, session_id: str, hotel_id: str, expires_at: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(insert(sessions).values(
            session_id=session_id, hotel_id=hotel_id, state_version=0,
            created_at=utcnow(), expires_at=expires_at,
        ))


def get_session(
    engine: Engine, session_id: str, *, timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        row = connection.execute(select(sessions).where(sessions.c.session_id == session_id)).mappings().first()
    return dict(row) if row else None


def recent_messages(
    engine: Engine, session_id: str, hotel_id: str, *, limit: int = 8,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        rows = connection.execute(
            select(messages.c.role, messages.c.content)
            .where(and_(messages.c.session_id == session_id, messages.c.hotel_id == hotel_id))
            .order_by(messages.c.sequence.desc()).limit(limit)
        ).all()
    return [{"role": row.role, "content": row.content} for row in reversed(rows)]


def reserve_request(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str, question: str,
    timeout_seconds: float | None = None,
    deadline_monotonic: float | None = None,
    cancellation_event: Event | None = None,
) -> dict[str, Any] | None:
    digest = hashlib.sha256(question.encode("utf-8")).hexdigest()
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        session_version = connection.scalar(select(sessions.c.state_version).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.expires_at > utcnow(),
        )))
        if session_version is None:
            raise ScopeError("session scope is invalid")
        inserted = connection.execute(pg_insert(requests).values(
            session_id=session_id, request_id=request_id, hotel_id=hotel_id,
            expected_version=session_version, payload_hash=digest,
            status="processing", created_at=utcnow(),
        ).on_conflict_do_nothing().returning(requests.c.request_id))
        # psycopg may report rowcount=-1 for INSERT ... RETURNING; use the
        # returned row to distinguish a fresh reservation from a replay.
        if inserted.scalar_one_or_none() is not None:
            if (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic
                    or cancellation_event is not None and cancellation_event.is_set()):
                raise TimeoutError("The guest turn expired before its reservation could commit.")
            return None
        row = connection.execute(select(requests).where(and_(
            requests.c.request_id == request_id,
        ))).mappings().first()
        if (not row or row["session_id"] != session_id or row["hotel_id"] != hotel_id
                or row["payload_hash"] != digest):
            raise IdempotencyConflict("request_id was already used with a different scope or payload")
        if row["status"] == "processing":
            raise RequestInProgress("request is still processing")
        if row["status"] == "error":
            raise RuntimeError(row["error_code"] or "request_failed")
        return dict(row["response"])


def complete_request(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str,
    question: str, answer: str, evidence: list[dict[str, Any]],
    response_fields: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    deadline_monotonic: float | None = None,
    cancellation_event: Event | None = None,
) -> dict[str, Any]:
    now = utcnow()
    result = {
        "request_id": request_id,
        "answer": answer,
        "evidence": evidence,
        "status": "completed",
    }
    result.update(response_fields or {})
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        hotel = connection.execute(select(hotels.c.config_version).where(
            hotels.c.hotel_id == hotel_id,
        )).scalar_one_or_none()
        if hotel is None:
            raise ScopeError("hotel scope is invalid")
        result["config_version"] = hotel
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        request = connection.execute(select(requests).where(and_(
            requests.c.session_id == session_id, requests.c.hotel_id == hotel_id,
            requests.c.request_id == request_id, requests.c.status == "processing",
        )).with_for_update()).mappings().first()
        if not request:
            raise ScopeError("request scope is invalid")
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        session = connection.execute(select(sessions).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.expires_at > now,
        )).with_for_update()).mappings().first()
        if not session:
            raise ScopeError("session scope is invalid")
        start = session["state_version"]
        if start != request["expected_version"]:
            raise VersionConflict("session state version changed")
        result["state_version"] = start + 1
        sequence = start * 2
        user_message_id = str(uuid.uuid5(uuid.UUID(session_id), str(sequence)))
        assistant_message_id = str(uuid.uuid5(uuid.UUID(session_id), str(sequence + 1)))
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        connection.execute(insert(messages), [
            {"message_id": user_message_id, "session_id": session_id,
             "hotel_id": hotel_id, "sequence": sequence, "role": "user",
             "content": question, "created_at": now},
            {"message_id": assistant_message_id, "session_id": session_id,
             "hotel_id": hotel_id, "sequence": sequence + 1, "role": "assistant",
             "content": answer, "created_at": now},
        ])
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        updated = connection.execute(update(sessions).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.state_version == start,
        )).values(state_version=start + 1))
        if updated.rowcount != 1:
            raise VersionConflict("session state version changed")
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id, requests.c.request_id == request_id,
            requests.c.hotel_id == hotel_id, requests.c.status == "processing",
        )).values(status="completed", response=result))
        if (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic
                or cancellation_event is not None and cancellation_event.is_set()):
            raise TimeoutError("The guest turn expired before its transaction could commit.")
    return result


def fail_request(
    engine: Engine, *, session_id: str, request_id: str, code: str,
    timeout_seconds: float | None = None,
) -> None:
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id, requests.c.request_id == request_id,
            requests.c.status == "processing",
        )).values(status="error", error_code=code))


def update_completed_response(engine: Engine, session_id: str, request_id: str, response: dict[str, Any]) -> None:
    with engine.begin() as connection:
        updated = connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id, requests.c.request_id == request_id,
            requests.c.status == "completed",
        )).values(response=response))
        if updated.rowcount != 1:
            raise ScopeError("completed request scope is invalid")


def export_snapshot(engine: Engine, hotel_id: str) -> dict[str, Any]:
    """Test helper that proves durable state can be read by a fresh repository handle."""
    return {"hotel": get_hotel(engine, hotel_id), "facts": facts_for_hotel(engine, hotel_id)}
