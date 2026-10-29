"""PostgreSQL persistence for versioned hotel knowledge and anonymous guest sessions."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    delete,
    func,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from staylead_platform.platform.contracts.admission import GuestAdmissionLimits
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefContext,
    GuestBriefMutationResult,
    GuestBriefReceipt,
    GuestBriefSnapshot,
    GuestBriefSourceRef,
    ValidatedGuestBriefPatch,
)
from staylead_platform.platform.contracts.knowledge import (
    ActiveKnowledgeSnapshot,
    EvidenceBinding,
    FreshnessDecision,
    SourceVersionRef,
)
from staylead_platform.platform.guest_context.sessions.retention import (
    ADMISSION_RESERVATION_WINDOW,
    SESSION_CONTENT_MAX_AGE,
)

metadata = MetaData()
CURRENT_SCHEMA_VERSION = 8
ROOM_ADVICE_ALGORITHM_VERSION = "s7-room-advice-v1"
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
    Column("knowledge_generation", Integer, nullable=False, server_default="1"),
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
    Column("provider_calls", Integer, nullable=False, server_default="0"),
    Column("lease_owner", String(36)),
    Column("lease_expires_at", DateTime(timezone=True)),
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
    Column("evidence_bindings", JSON, nullable=False, server_default="[]"),
    UniqueConstraint("session_id", "sequence", name="uq_guest_messages_sequence"),
)
knowledge_packs = Table(
    "knowledge_packs", metadata,
    Column("hotel_id", String(80), primary_key=True),
    Column("pack_id", String(120), nullable=False),
    Column("pack_version", String(80), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("canonical_hash", String(64), nullable=False),
    Column("manifest", JSON, nullable=False),
    Column("imported_at", DateTime(timezone=True), nullable=False),
)
knowledge_sources = Table(
    "knowledge_sources", metadata,
    Column("source_id", String(120), primary_key=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("version", String(80), nullable=False),
    Column("scope", String(40), nullable=False),
    Column("guest_approved", Boolean, nullable=False),
    Column("valid_from", String(20), nullable=False),
    Column("valid_to", String(20), nullable=False),
    Column("source", JSON, nullable=False),
    Column("source_hash", String(64), nullable=False, server_default=""),
    Column("lifecycle_status", String(24), nullable=False, server_default="approved"),
    Column("last_success_at", DateTime(timezone=True)),
    Column("last_failure", Text),
)
knowledge_media = Table(
    "knowledge_media", metadata,
    Column("media_id", String(120), primary_key=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("source_id", String(120), nullable=False),
    Column("source_version", String(80), nullable=False),
    Column("fact_ids", JSON, nullable=False),
    Column("kind", String(20), nullable=False),
    Column("mime_type", String(80), nullable=False),
    Column("byte_size", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("caption", Text, nullable=False),
    Column("alt_text", Text, nullable=False),
    Column("start_seconds", Float),
    Column("end_seconds", Float),
    Column("duration_seconds", Float),
    Column("captions_media_id", String(120)),
    Column("guest_approved_whole_file", Boolean, nullable=False),
    Column("valid_from", String(20), nullable=False),
    Column("valid_to", String(20), nullable=False),
    Column("content", LargeBinary, nullable=False),
)
lifecycle_operations = Table(
    "knowledge_lifecycle_operations", metadata,
    Column("operation_id", String(128), primary_key=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("source_id", String(120), nullable=False),
    Column("operation_kind", String(24), nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("result", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
guest_briefs = Table(
    "guest_briefs", metadata,
    Column("session_id", String(36), primary_key=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("brief_version", Integer, nullable=False),
    Column("data", JSON, nullable=False),
    Column("pending_fields", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
guest_language_preferences = Table(
    "guest_language_preferences", metadata,
    Column("session_id", String(36), primary_key=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("language_tag", String(64), nullable=False),
    Column("source", String(16), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
guest_brief_source_utterances = Table(
    "guest_brief_source_utterances", metadata,
    Column("source_utterance_id", String(36), primary_key=True),
    Column("session_id", String(36), nullable=False, index=True),
    Column("hotel_id", String(80), nullable=False),
    Column("request_id", String(128), nullable=False),
    Column("content", Text, nullable=False),
    Column("fields", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
guest_brief_receipts = Table(
    "guest_brief_receipts", metadata,
    Column("request_id", String(128), primary_key=True),
    Column("session_id", String(36), nullable=False, index=True),
    Column("hotel_id", String(80), nullable=False),
    Column("expected_brief_version", Integer, nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("status", String(24), nullable=False),
    Column("brief_version_before", Integer, nullable=False),
    Column("brief_version_after", Integer, nullable=False),
    Column("applied_delta", JSON, nullable=False),
    Column("source_utterance_id", String(36), nullable=False),
    Column("source_fields", JSON, nullable=False),
    Column("answer_status", String(20), nullable=False),
    Column("brief_version_used", Integer),
    Column("brief_dependent", Boolean, nullable=False, server_default="true"),
    Column("answer_payload", JSON),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
room_advice_results = Table(
    "guest_room_advice_results", metadata,
    Column("result_id", String(36), primary_key=True),
    Column("session_id", String(36), nullable=False, index=True),
    Column("hotel_id", String(80), nullable=False, index=True),
    Column("request_id", String(128), nullable=False),
    Column("result_version", Integer, nullable=False),
    Column("session_state_version", Integer, nullable=False),
    Column("brief_version", Integer, nullable=False),
    Column("source_generation", Integer, nullable=False),
    Column("config_version", String(80), nullable=False),
    Column("policy_version", String(120)),
    Column("price_version", String(120)),
    Column("algorithm_version", String(80), nullable=False),
    Column("dependency_fingerprint", String(64), nullable=False),
    Column("source_refs", JSON, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("session_id", "request_id", name="uq_room_advice_session_request"),
    UniqueConstraint("session_id", "result_version", name="uq_room_advice_session_version"),
    UniqueConstraint("session_id", "session_state_version", name="uq_room_advice_session_state"),
)
room_advice_selections = Table(
    "guest_room_advice_selections", metadata,
    Column("session_id", String(36), primary_key=True),
    Column("hotel_id", String(80), nullable=False),
    Column("result_id", String(36), nullable=False),
    Column("result_version", Integer, nullable=False),
    Column("option_id", String(120), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class ScopeError(ValueError):
    pass


class VersionConflict(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


class RequestInProgress(ValueError):
    pass


class QuotaExceeded(ValueError):
    def __init__(self, scope: str, retry_after: int) -> None:
        super().__init__(f"Guest admission limit exceeded for {scope}.")
        self.scope = scope
        self.retry_after = max(1, int(retry_after))


class ProviderCallLimitExceeded(ValueError):
    def __init__(self, code: str = "provider_call_limit") -> None:
        super().__init__("The request has no provider calls remaining.")
        self.code = code


def request_payload_hash(question: str) -> str:
    """Return the durable idempotency digest used for a guest request."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


class StaleSource(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False, default=_canonical_hash_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_hash_default(item: Any) -> str:
    if isinstance(item, datetime):
        return item.astimezone(UTC).isoformat()
    if isinstance(item, bytes):
        return hashlib.sha256(item).hexdigest()
    raise TypeError(f"Unsupported canonical hash value: {type(item).__name__}")


def _source_snapshot_hash(source: dict[str, Any], facts: list[dict[str, Any]],
                          media: list[dict[str, Any]]) -> str:
    return _canonical_hash({
        "source": source,
        "facts": sorted(facts, key=lambda item: item["fact_id"]),
        "media": sorted(({
            key: value for key, value in item.items() if key != "content"
        } | {"content_sha256": hashlib.sha256(item["content"]).hexdigest()}
                         for item in media), key=lambda item: item["media_id"]),
    })


def _source_hash_from_connection(connection: Any, hotel_id: str, source_id: str) -> str:
    source = connection.execute(select(knowledge_sources.c.source).where(and_(
        knowledge_sources.c.hotel_id == hotel_id, knowledge_sources.c.source_id == source_id,
    ))).scalar_one()
    facts = [dict(row) | {"fact": row["fact"]} for row in connection.execute(
        select(knowledge_facts).where(and_(knowledge_facts.c.hotel_id == hotel_id,
                                           knowledge_facts.c.source_id == source_id))
    ).mappings()]
    media = [dict(row) for row in connection.execute(
        select(knowledge_media).where(and_(knowledge_media.c.hotel_id == hotel_id,
                                           knowledge_media.c.source_id == source_id))
    ).mappings()]
    return _source_snapshot_hash(source, facts, media)


def _current_hotel_lifecycle(connection: Any, hotel_id: str, now: datetime) -> dict[str, Any]:
    generation = connection.scalar(select(hotels.c.knowledge_generation).where(
        hotels.c.hotel_id == hotel_id,
    ))
    sources = connection.execute(select(knowledge_sources).where(
        knowledge_sources.c.hotel_id == hotel_id,
    ).order_by(knowledge_sources.c.source_id)).mappings().all()
    day = now.astimezone(UTC).date().isoformat()
    return {
        "generation": generation,
        "sources": [{
            "source_id": source["source_id"], "version": source["version"],
            "source_hash": source["source_hash"],
            "status": _reported_source_status(source, day),
            "guest_approved": source["guest_approved"],
            "valid_from": source["valid_from"], "valid_to": source["valid_to"],
            "last_success_at": source["last_success_at"].isoformat() if source["last_success_at"] else None,
            "last_failure": source["last_failure"],
        } for source in sources],
    }


def _effective_source_status(source: Any, today: str) -> str:
    status = source["lifecycle_status"]
    if status == "approved" and (not source["guest_approved"] or source["valid_from"] > today):
        return "not_yet_valid"
    if status == "approved" and source["valid_to"] < today:
        return "expired"
    return status


def _reported_source_status(source: Any, today: str) -> str:
    status = _effective_source_status(source, today)
    return "refresh_failed" if status == "approved" and source["last_failure"] else status


def _source_ref(row: Any, generation: int, today: str) -> SourceVersionRef:
    return SourceVersionRef(
        hotel_id=row["hotel_id"], source_id=row["source_id"], hotel_generation=generation,
        source_version=row["version"], source_hash=row["source_hash"],
        status=_reported_source_status(row, today), guest_approved=row["guest_approved"],
        valid_from=row["valid_from"], valid_to=row["valid_to"], last_failure=row["last_failure"],
        last_success_at=row["last_success_at"].isoformat() if row["last_success_at"] else None,
    )


def get_active_snapshot(
    engine: Engine, hotel_id: str, *, now: datetime | None = None,
    timeout_seconds: float | None = None,
) -> ActiveKnowledgeSnapshot | None:
    checked_at = (now or utcnow()).astimezone(UTC)
    today = checked_at.date().isoformat()
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        hotel = connection.execute(select(hotels.c.knowledge_generation).where(
            hotels.c.hotel_id == hotel_id,
        ).with_for_update(read=True)).first()
        if hotel is None:
            return None
        generation = hotel.knowledge_generation
        rows = connection.execute(select(knowledge_sources).where(
            knowledge_sources.c.hotel_id == hotel_id,
        ).order_by(knowledge_sources.c.source_id)).mappings().all()
        refs = tuple(_source_ref(row, generation, today) for row in rows)
    return ActiveKnowledgeSnapshot(hotel_id, generation, refs)


def _binding_from_value(value: EvidenceBinding | dict[str, Any]) -> EvidenceBinding:
    if isinstance(value, EvidenceBinding):
        return value
    source = value.get("source", value)
    ref = source if isinstance(source, SourceVersionRef) else SourceVersionRef(
        hotel_id=source["hotel_id"], source_id=source["source_id"],
        hotel_generation=int(source.get("hotel_generation", source.get("source_generation", 0))),
        source_version=source.get("source_version", source.get("version", "")),
        source_hash=source.get("source_hash", ""), status=source.get("status", "approved"),
        guest_approved=source.get("guest_approved", True),
        valid_from=source.get("valid_from", "0001-01-01"),
        valid_to=source.get("valid_to", "9999-12-31"),
        last_failure=source.get("last_failure"),
        last_success_at=source.get("last_success_at"),
    )
    return EvidenceBinding(ref, tuple(value.get("fact_ids", ())), tuple(value.get("media_ids", ())),
                           value.get("media_sha256"))


def _validate_evidence_on_connection(
    connection: Any, hotel_id: str, evidence: list[EvidenceBinding | dict[str, Any]], now: datetime,
) -> FreshnessDecision:
    checked_at = now.astimezone(UTC)
    today = checked_at.date().isoformat()
    refresh_failed = False
    for raw in evidence:
        binding = _binding_from_value(raw)
        ref = binding.source
        if ref.hotel_id != hotel_id:
            return FreshnessDecision("stale", False, checked_at, "hotel_scope_changed")
        row = connection.execute(select(knowledge_sources).where(and_(
            knowledge_sources.c.hotel_id == hotel_id,
            knowledge_sources.c.source_id == ref.source_id,
        ))).mappings().first()
        if row is None:
            return FreshnessDecision("deleted", False, checked_at, "source_unavailable")
        status = _effective_source_status(row, today)
        if status != "approved" or not row["guest_approved"]:
            return FreshnessDecision(status, False, checked_at, "source_not_eligible")
        refresh_failed = refresh_failed or bool(row["last_failure"])
        if row["version"] != ref.source_version or row["source_hash"] != ref.source_hash:
            return FreshnessDecision("stale", False, checked_at, "source_version_changed")
        if binding.fact_ids:
            count = connection.scalar(select(knowledge_facts.c.fact_id).where(and_(
                knowledge_facts.c.hotel_id == hotel_id,
                knowledge_facts.c.source_id == ref.source_id,
                knowledge_facts.c.source_version == ref.source_version,
                knowledge_facts.c.fact_id.in_(binding.fact_ids),
                knowledge_facts.c.status.in_(["confirmed", "unknown", "needs_confirmation"]),
                knowledge_facts.c.valid_from <= today, knowledge_facts.c.valid_to >= today,
            )).limit(1))
            found = set(connection.scalars(select(knowledge_facts.c.fact_id).where(and_(
                knowledge_facts.c.hotel_id == hotel_id,
                knowledge_facts.c.source_id == ref.source_id,
                knowledge_facts.c.source_version == ref.source_version,
                knowledge_facts.c.fact_id.in_(binding.fact_ids),
                knowledge_facts.c.status.in_(["confirmed", "unknown", "needs_confirmation"]),
                knowledge_facts.c.valid_from <= today, knowledge_facts.c.valid_to >= today,
            ))).all())
            if count is None or found != set(binding.fact_ids):
                return FreshnessDecision("stale", False, checked_at, "fact_evidence_changed")
        if binding.media_ids:
            media_rows = connection.execute(select(knowledge_media).where(and_(
                knowledge_media.c.hotel_id == hotel_id,
                knowledge_media.c.source_id == ref.source_id,
                knowledge_media.c.source_version == ref.source_version,
                knowledge_media.c.media_id.in_(binding.media_ids),
                knowledge_media.c.guest_approved_whole_file.is_(True),
                knowledge_media.c.valid_from <= today, knowledge_media.c.valid_to >= today,
            ))).mappings().all()
            found_media = {item["media_id"] for item in media_rows}
            expected_hashes = binding.media_sha256 or {}
            if found_media != set(binding.media_ids) or set(expected_hashes) != set(binding.media_ids):
                return FreshnessDecision("stale", False, checked_at, "media_evidence_changed")
            for item in media_rows:
                if (item["sha256"] != expected_hashes[item["media_id"]]
                        or hashlib.sha256(bytes(item["content"])).hexdigest() != item["sha256"]):
                    return FreshnessDecision("stale", False, checked_at, "media_hash_changed")
    return FreshnessDecision("refresh_failed" if refresh_failed else "current", True, checked_at,
                             "active_snapshot_retained" if refresh_failed else None)


def validate_evidence_current(
    engine: Engine, hotel_id: str, evidence: list[EvidenceBinding | dict[str, Any]], now: datetime,
    *, timeout_seconds: float | None = None,
) -> FreshnessDecision:
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        return _validate_evidence_on_connection(connection, hotel_id, evidence, now)


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
            existing = 2
        if existing < 3:
            # CREATE TABLE IF NOT EXISTS above creates the new pack/source/media tables.
            connection.execute(insert(schema_versions).values(version=3, applied_at=utcnow()))
            existing = 3
        if existing < 4:
            columns = {column["name"] for column in inspect(connection).get_columns("hotels")}
            if "knowledge_generation" not in columns:
                connection.execute(text(
                    "ALTER TABLE hotels ADD COLUMN knowledge_generation INTEGER NOT NULL DEFAULT 1"
                ))
            columns = {column["name"] for column in inspect(connection).get_columns("knowledge_sources")}
            for name, sql in (
                ("source_hash", "VARCHAR(64) NOT NULL DEFAULT ''"),
                ("lifecycle_status", "VARCHAR(24) NOT NULL DEFAULT 'approved'"),
                ("last_success_at", "TIMESTAMP WITH TIME ZONE"),
                ("last_failure", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE knowledge_sources ADD COLUMN {name} {sql}"))
            columns = {column["name"] for column in inspect(connection).get_columns("guest_messages")}
            if "evidence_bindings" not in columns:
                connection.execute(text(
                    "ALTER TABLE guest_messages ADD COLUMN evidence_bindings JSON NOT NULL DEFAULT '[]'"
                ))
            _backfill_legacy_sources(connection, utcnow())
            # Source identity hashes are backfilled without relying on optional PG extensions.
            for row in connection.execute(select(knowledge_sources).where(
                knowledge_sources.c.source_hash == "",
            )).mappings():
                connection.execute(update(knowledge_sources).where(
                    knowledge_sources.c.source_id == row["source_id"],
                ).values(source_hash=_source_hash_from_connection(
                    connection, row["hotel_id"], row["source_id"],
                )))
            _backfill_legacy_response_bindings(connection, utcnow())
            connection.execute(insert(schema_versions).values(version=4, applied_at=utcnow()))
            existing = 4
        if existing < 5:
            # New guest brief/source/receipt tables were created by metadata.create_all above.
            connection.execute(insert(schema_versions).values(version=5, applied_at=utcnow()))
            existing = 5
        if existing < 6:
            # metadata.create_all above creates the session-scoped presentation preference table.
            connection.execute(insert(schema_versions).values(version=6, applied_at=utcnow()))
            existing = 6
        if existing < 7:
            # metadata.create_all above creates immutable room advice snapshots and their selection pointer.
            connection.execute(insert(schema_versions).values(version=7, applied_at=utcnow()))
            existing = 7
        if existing < 8:
            columns = {column["name"] for column in inspect(connection).get_columns("guest_requests")}
            for name, sql in (
                ("provider_calls", "INTEGER NOT NULL DEFAULT 0"),
                ("lease_owner", "VARCHAR(36)"),
                ("lease_expires_at", "TIMESTAMP WITH TIME ZONE"),
            ):
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE guest_requests ADD COLUMN {name} {sql}"))
            connection.execute(insert(schema_versions).values(version=8, applied_at=utcnow()))
    return CURRENT_SCHEMA_VERSION


def _backfill_legacy_sources(connection: Any, imported_at: datetime) -> None:
    """Register schema-3 fixture facts only when stored provenance proves guest eligibility."""
    rows = connection.execute(select(knowledge_facts).order_by(
        knowledge_facts.c.hotel_id, knowledge_facts.c.source_id, knowledge_facts.c.fact_id,
    )).mappings().all()
    groups: dict[tuple[str, str], list[Any]] = {}
    for row in rows:
        groups.setdefault((row["hotel_id"], row["source_id"]), []).append(row)
    for (hotel_id, source_id), facts in groups.items():
        if connection.scalar(select(knowledge_sources.c.source_id).where(
            knowledge_sources.c.source_id == source_id,
        )) is not None:
            continue
        hotel = connection.execute(select(hotels.c.synthetic, hotels.c.public_config).where(
            hotels.c.hotel_id == hotel_id,
        )).first()
        trusted_bootstrap = bool(
            hotel and hotel.synthetic and hotel.public_config.get("source_pack") == "staylead-hospitality-knowledge-v1"
        )
        versions = {fact["source_version"] for fact in facts}
        refs_match = all(
            isinstance(fact["fact"], dict)
            and fact["fact"].get("hotel_id") == hotel_id
            and fact["fact"].get("approved") is True
            and fact["fact"].get("visibility") == "guest"
            and isinstance(fact["fact"].get("source_refs"), list)
            and len(fact["fact"].get("source_refs", [])) == 1
            and isinstance(fact["fact"]["source_refs"][0], dict)
            and fact["fact"]["source_refs"][0].get("source_id") == source_id
            and fact["fact"]["source_refs"][0].get("version") == fact["source_version"]
            and fact["status"] in {"confirmed", "unknown", "needs_confirmation"}
            for fact in facts
        )
        version = next(iter(versions)) if len(versions) == 1 else "legacy-needs-review"
        valid_from = max(fact["valid_from"] for fact in facts)
        valid_to = min(fact["valid_to"] for fact in facts)
        eligible = bool(trusted_bootstrap and refs_match and len(versions) == 1 and valid_from <= valid_to)
        source = {
            "source_id": source_id, "hotel_id": hotel_id, "version": version,
            "scope": "hotel-specific", "guest_approved": eligible,
            "valid_from": valid_from, "valid_to": valid_to,
            "legacy_backfill": True,
        }
        connection.execute(insert(knowledge_sources).values(
            source_id=source_id, hotel_id=hotel_id, version=version,
            scope="hotel-specific", guest_approved=eligible,
            valid_from=valid_from, valid_to=valid_to, source=source,
            source_hash="",
            lifecycle_status="approved" if eligible else "needs_review",
            last_success_at=imported_at if eligible else None,
            last_failure=None,
        ))


def _backfill_legacy_response_bindings(connection: Any, now: datetime) -> None:
    """Bind schema-3 completed responses and assistant history to persisted source revisions."""
    requests_to_backfill = connection.execute(select(
        requests.c.session_id, requests.c.request_id, requests.c.hotel_id,
        requests.c.expected_version, requests.c.response,
    ).where(and_(requests.c.status == "completed", requests.c.response.is_not(None)))).mappings().all()
    for request in requests_to_backfill:
        response = dict(request["response"])
        if "evidence_bindings" in response:
            continue
        groups: dict[str, dict[str, Any]] = {}
        fact_metadata: dict[str, dict[str, Any]] = {}
        media_metadata: dict[str, dict[str, Any]] = {}
        unresolved = False
        fact_ids = {item.get("fact_id") for item in response.get("evidence", [])
                    if isinstance(item, dict) and item.get("fact_id")}
        fact_rows = connection.execute(select(knowledge_facts).where(and_(
            knowledge_facts.c.hotel_id == request["hotel_id"],
            knowledge_facts.c.fact_id.in_(fact_ids or ["__no_fact__"]),
        ))).mappings().all()
        matched_fact_ids = {fact["fact_id"] for fact in fact_rows}
        unresolved = bool(fact_ids - matched_fact_ids)
        for fact in fact_rows:
            source = connection.execute(select(knowledge_sources).where(and_(
                knowledge_sources.c.hotel_id == request["hotel_id"],
                knowledge_sources.c.source_id == fact["source_id"],
                knowledge_sources.c.version == fact["source_version"],
            ))).mappings().first()
            if source is None:
                unresolved = True
                continue
            binding = groups.setdefault(source["source_id"], {
                "source": _serialized_source_ref(source, request["hotel_id"], connection, now),
                "fact_ids": [], "media_ids": [], "media_sha256": {},
            })
            binding["fact_ids"].append(fact["fact_id"])
            source_ref = binding["source"]
            fact_metadata[fact["fact_id"]] = {
                "source_id": source["source_id"], "source_version": source["version"],
                "source_hash": source["source_hash"],
                "source_generation": source_ref["hotel_generation"],
            }
        if "evidence" in response:
            response["evidence"] = [
                ({**item, **fact_metadata[item["fact_id"]]}
                 if isinstance(item, dict) and item.get("fact_id") in fact_metadata else item)
                for item in response["evidence"]
            ]
        media_ids = {item.get("media_id") for item in response.get("media", [])
                     if isinstance(item, dict) and item.get("media_id")}
        media_rows = connection.execute(select(knowledge_media).where(and_(
            knowledge_media.c.hotel_id == request["hotel_id"],
            knowledge_media.c.media_id.in_(media_ids or ["__no_media__"]),
        ))).mappings().all()
        matched_media_ids = {media["media_id"] for media in media_rows}
        unresolved = unresolved or bool(media_ids - matched_media_ids)
        for media in media_rows:
            source = connection.execute(select(knowledge_sources).where(and_(
                knowledge_sources.c.hotel_id == request["hotel_id"],
                knowledge_sources.c.source_id == media["source_id"],
                knowledge_sources.c.version == media["source_version"],
            ))).mappings().first()
            if source is None:
                unresolved = True
                continue
            binding = groups.setdefault(source["source_id"], {
                "source": _serialized_source_ref(source, request["hotel_id"], connection, now),
                "fact_ids": [], "media_ids": [], "media_sha256": {},
            })
            binding["media_ids"].append(media["media_id"])
            binding["media_sha256"][media["media_id"]] = media["sha256"]
            source_ref = binding["source"]
            media_metadata[media["media_id"]] = {
                "hotel_id": request["hotel_id"], "source_id": media["source_id"],
                "source_version": media["source_version"], "source_hash": source["source_hash"],
                "source_generation": source_ref["hotel_generation"], "sha256": media["sha256"],
            }
            captions_media_id = media.get("captions_media_id")
            if captions_media_id:
                captions_sha256 = connection.scalar(select(knowledge_media.c.sha256).where(and_(
                    knowledge_media.c.hotel_id == request["hotel_id"],
                    knowledge_media.c.media_id == captions_media_id,
                    knowledge_media.c.source_id == media["source_id"],
                    knowledge_media.c.source_version == media["source_version"],
                )))
                if captions_sha256:
                    media_metadata[media["media_id"]]["captions_sha256"] = captions_sha256
                    binding["media_ids"].append(captions_media_id)
                    binding["media_sha256"][captions_media_id] = captions_sha256
                else:
                    unresolved = True
        if "media" in response:
            response["media"] = [
                ({**item, **media_metadata[item["media_id"]]}
                 if isinstance(item, dict) and item.get("media_id") in media_metadata else item)
                for item in response["media"]
            ]
        bindings = list(groups.values())
        if unresolved:
            bindings.append({
                "source": {"hotel_id": request["hotel_id"], "source_id": "__legacy_unresolved__",
                           "hotel_generation": 0, "source_version": "", "source_hash": "",
                           "status": "unavailable", "guest_approved": False,
                           "valid_from": "0001-01-01", "valid_to": "9999-12-31"},
                "fact_ids": [], "media_ids": [], "media_sha256": {},
            })
        response["evidence_bindings"] = bindings
        connection.execute(update(requests).where(
            requests.c.request_id == request["request_id"],
        ).values(response=response))
        connection.execute(update(messages).where(and_(
            messages.c.session_id == request["session_id"],
            messages.c.hotel_id == request["hotel_id"],
            messages.c.sequence == request["expected_version"] * 2 + 1,
            messages.c.role == "assistant",
        )).values(evidence_bindings=bindings))


def _serialized_source_ref(source: Any, hotel_id: str, connection: Any, now: datetime) -> dict[str, Any]:
    generation = connection.scalar(select(hotels.c.knowledge_generation).where(
        hotels.c.hotel_id == hotel_id,
    )) or 1
    return {
        "hotel_id": hotel_id, "source_id": source["source_id"],
        "hotel_generation": generation, "source_version": source["version"],
        "source_hash": source["source_hash"],
        "status": _reported_source_status(source, now.astimezone(UTC).date().isoformat()),
        "guest_approved": source["guest_approved"],
        "valid_from": source["valid_from"], "valid_to": source["valid_to"],
        "last_failure": source["last_failure"],
        "last_success_at": source["last_success_at"].isoformat() if source["last_success_at"] else None,
    }


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
    sources: list[dict[str, Any]] | None = None,
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
        connection.execute(knowledge_sources.delete().where(knowledge_sources.c.hotel_id == hotel_id))
        if facts:
            connection.execute(insert(knowledge_facts), facts)
        facts_by_source = {
            source["source_id"]: [row["fact"] for row in facts if row["source_id"] == source["source_id"]]
            for source in sources or []
        }
        if sources:
            connection.execute(insert(knowledge_sources), [{
                "source_id": source["source_id"], "hotel_id": hotel_id,
                "version": source["version"], "scope": source["scope"],
                "guest_approved": source["guest_approved"],
                "valid_from": source["valid_from"], "valid_to": source["valid_to"],
                "source": source,
                "source_hash": _source_snapshot_hash(source, facts_by_source[source["source_id"]], []),
                "lifecycle_status": "approved", "last_success_at": now, "last_failure": None,
            } for source in sources])
    return len(facts)


def get_hotel_by_slug(engine: Engine, slug: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(select(hotels).where(hotels.c.slug == slug)).mappings().first()
    return dict(row) if row else None


def get_hotel_by_id(engine: Engine, hotel_id: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(select(hotels).where(hotels.c.hotel_id == hotel_id)).mappings().first()
    return dict(row) if row else None


def get_hotel(engine: Engine, hotel_id: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(select(hotels).where(hotels.c.hotel_id == hotel_id)).mappings().first()
    return dict(row) if row else None


def import_complete_pack(engine: Engine, pack: dict[str, Any]) -> dict[str, Any]:
    """Publish one already validated complete pack atomically and immutably."""
    hotel = pack["hotel"]
    now = utcnow()
    with engine.begin() as connection:
        existing = connection.execute(select(knowledge_packs).where(
            knowledge_packs.c.hotel_id == hotel["hotel_id"],
        )).mappings().first()
        by_slug = connection.execute(select(hotels.c.hotel_id).where(
            hotels.c.slug == hotel["slug"],
        )).scalar_one_or_none()
        if existing:
            if existing["canonical_hash"] == pack["canonical_hash"]:
                current = _current_hotel_lifecycle(connection, hotel["hotel_id"], now)
                return {"status": "noop", "hotel_id": hotel["hotel_id"],
                        "canonical_hash": pack["canonical_hash"], "receipt_hash": existing["canonical_hash"],
                        **current}
            raise ValueError("Hotel already has a different immutable knowledge pack.")
        if by_slug is not None:
            raise ValueError("Hotel slug is already registered.")
        # IDs are globally unique in the existing facts table. Detect every collision before inserts.
        fact_ids = [fact["fact_id"] for fact in pack["facts"]]
        if fact_ids and connection.scalar(select(knowledge_facts.c.fact_id).where(
            knowledge_facts.c.fact_id.in_(fact_ids),
        ).limit(1)) is not None:
            raise ValueError("A fact ID is already registered.")
        if connection.scalar(select(hotels.c.hotel_id).where(
            hotels.c.hotel_id == hotel["hotel_id"],
        )) is not None:
            raise ValueError("Hotel ID is already registered without this pack identity.")
        connection.execute(insert(hotels).values(
            hotel_id=hotel["hotel_id"], slug=hotel["slug"],
            config_version=hotel["config_version"], public_config=hotel["public_config"],
            synthetic=True, updated_at=now,
        ))
        connection.execute(insert(knowledge_packs).values(
            hotel_id=hotel["hotel_id"], pack_id=pack["pack_id"],
            pack_version=pack["pack_version"], schema_version=pack["schema_version"],
            canonical_hash=pack["canonical_hash"], manifest=pack["manifest"], imported_at=now,
        ))
        if pack["sources"]:
            facts_by_source = {source["source_id"]: [fact for fact in pack["facts"]
                                if fact["source_refs"][0]["source_id"] == source["source_id"]]
                               for source in pack["sources"]}
            media_by_source = {source["source_id"]: [item for item in pack["media"]
                                if item["source_id"] == source["source_id"]]
                               for source in pack["sources"]}
            connection.execute(insert(knowledge_sources), [{
                "source_id": s["source_id"], "hotel_id": hotel["hotel_id"],
                "version": s["version"], "scope": s["scope"],
                "guest_approved": s["guest_approved"], "valid_from": s["valid_from"],
                "valid_to": s["valid_to"], "source": s,
                "source_hash": _source_snapshot_hash(s, facts_by_source[s["source_id"]],
                                                     media_by_source[s["source_id"]]),
                "lifecycle_status": "approved",
                "last_success_at": now, "last_failure": None,
            } for s in pack["sources"]])
        if pack["facts"]:
            connection.execute(insert(knowledge_facts), [{
                "fact_id": f["fact_id"], "hotel_id": hotel["hotel_id"],
                "source_id": f["source_refs"][0]["source_id"],
                "source_version": f["source_refs"][0]["version"],
                "section": f.get("section", f["topic"]), "fact_version": f.get("fact_version", "1"),
                "status": f["status"], "valid_from": f["valid_from"], "valid_to": f["valid_to"],
                "fact": f, "imported_at": now,
            } for f in pack["facts"]])
        if pack["media"]:
            connection.execute(insert(knowledge_media), [{
                **{k: m.get(k) for k in ("media_id", "source_id", "source_version", "fact_ids", "kind", "mime_type", "byte_size", "sha256", "caption", "alt_text", "start_seconds", "end_seconds", "duration_seconds", "captions_media_id", "guest_approved_whole_file", "valid_from", "valid_to", "content")},
                "hotel_id": hotel["hotel_id"],
            } for m in pack["media"]])
    return {"status": "imported", "hotel_id": hotel["hotel_id"], "canonical_hash": pack["canonical_hash"]}


def _operation_replay(connection: Any, operation_id: str, hotel_id: str,
                      source_id: str, kind: str, payload_hash: str, now: datetime) -> dict[str, Any] | None:
    prior = connection.execute(select(lifecycle_operations).where(
        lifecycle_operations.c.operation_id == operation_id,
    )).mappings().first()
    if prior is None:
        return None
    if (prior["hotel_id"] != hotel_id or prior["source_id"] != source_id
            or prior["operation_kind"] != kind or prior["payload_hash"] != payload_hash):
        raise IdempotencyConflict("operation_id was already used with a different scope or payload")
    return {**prior["result"], "status": "noop", "current": _current_hotel_lifecycle(connection, hotel_id, now)}


def _validate_lifecycle_pack(pack: dict[str, Any], hotel_id: str, source_id: str,
                             hotel: Any) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    payload_hotel = pack["hotel"]
    if (payload_hotel["hotel_id"] != hotel_id or payload_hotel["slug"] != hotel["slug"]
            or payload_hotel["config_version"] != hotel["config_version"]
            or payload_hotel["public_config"] != hotel["public_config"]):
        raise ScopeError("replacement payload must preserve the authoritative hotel config")
    if len(pack["sources"]) != 1 or pack["sources"][0]["source_id"] != source_id:
        raise ScopeError("replacement must contain exactly the selected hotel source")
    source = pack["sources"][0]
    facts = pack["facts"]
    media = pack["media"]
    for fact in facts:
        refs = fact.get("source_refs", [])
        if len(refs) != 1 or refs[0].get("source_id") != source_id or refs[0].get("version") != source["version"]:
            raise ScopeError("replacement fact references a foreign source")
    for item in media:
        if item.get("source_id") != source_id or item.get("source_version") != source["version"]:
            raise ScopeError("replacement media references a foreign source")
        if set(item.get("fact_ids", [])) - {fact["fact_id"] for fact in facts}:
            raise ScopeError("replacement media references a missing or foreign fact")
    return source, facts, media


def replace_source_snapshot(
    engine: Engine, *, hotel_id: str, source_id: str, expected_generation: int,
    expected_version: str, expected_source_hash: str, operation_id: str,
    pack: dict[str, Any], now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically replace exactly one source snapshot using hotel and source CAS tokens."""
    timestamp = (now or utcnow()).astimezone(UTC)
    payload_hash = _canonical_hash({
        "hotel_id": hotel_id, "source_id": source_id, "expected_generation": expected_generation,
        "expected_version": expected_version, "expected_source_hash": expected_source_hash,
        "snapshot_hash": pack.get("canonical_hash") or _canonical_hash(pack["manifest"]),
    })
    if not operation_id or len(operation_id) > 128:
        raise ValueError("operation_id must contain 1–128 characters")
    with engine.begin() as connection:
        replay = _operation_replay(connection, operation_id, hotel_id, source_id,
                                   "refresh", payload_hash, timestamp)
        if replay is not None:
            return replay
        hotel = connection.execute(select(hotels).where(
            hotels.c.hotel_id == hotel_id,
        ).with_for_update()).mappings().first()
        if hotel is None:
            raise ScopeError("hotel scope is invalid")
        replay = _operation_replay(connection, operation_id, hotel_id, source_id,
                                   "refresh", payload_hash, timestamp)
        if replay is not None:
            return replay
        source, facts, media = _validate_lifecycle_pack(pack, hotel_id, source_id, hotel)
        current = connection.execute(select(knowledge_sources).where(and_(
            knowledge_sources.c.hotel_id == hotel_id,
            knowledge_sources.c.source_id == source_id,
        )).with_for_update()).mappings().first()
        if current is None:
            raise ScopeError("selected source does not exist")
        if (hotel["knowledge_generation"] != expected_generation
                or current["version"] != expected_version
                or current["source_hash"] != expected_source_hash):
            raise VersionConflict("selected source or hotel generation changed")
        fact_ids = [fact["fact_id"] for fact in facts]
        media_ids = [item["media_id"] for item in media]
        collisions = connection.execute(select(knowledge_facts.c.fact_id).where(and_(
            knowledge_facts.c.fact_id.in_(fact_ids or [""]),
            ~and_(knowledge_facts.c.hotel_id == hotel_id, knowledge_facts.c.source_id == source_id),
        )).limit(1)).scalar_one_or_none()
        if collisions is not None:
            raise ScopeError("replacement fact ID belongs to another source")
        media_collision = connection.execute(select(knowledge_media.c.media_id).where(and_(
            knowledge_media.c.media_id.in_(media_ids or [""]),
            ~and_(knowledge_media.c.hotel_id == hotel_id, knowledge_media.c.source_id == source_id),
        )).limit(1)).scalar_one_or_none()
        if media_collision is not None:
            raise ScopeError("replacement media ID belongs to another source")
        active_day = (now or utcnow()).astimezone(UTC).date().isoformat()
        active_other_facts = select(knowledge_facts.c.fact_id).select_from(
            knowledge_facts.outerjoin(knowledge_sources, and_(
                knowledge_sources.c.hotel_id == knowledge_facts.c.hotel_id,
                knowledge_sources.c.source_id == knowledge_facts.c.source_id,
                knowledge_sources.c.version == knowledge_facts.c.source_version,
            ))
        ).where(and_(
            knowledge_facts.c.hotel_id == hotel_id,
            knowledge_facts.c.source_id != source_id,
            knowledge_facts.c.status.in_(["confirmed", "unknown", "needs_confirmation"]),
            knowledge_facts.c.valid_from <= active_day,
            knowledge_facts.c.valid_to >= active_day,
            (knowledge_sources.c.source_id.is_(None) | and_(
                knowledge_sources.c.guest_approved.is_(True),
                knowledge_sources.c.lifecycle_status == "approved",
                knowledge_sources.c.valid_from <= active_day,
                knowledge_sources.c.valid_to >= active_day,
            )),
        )).limit(401)
        other_count = len(connection.execute(active_other_facts).all())
        replacement_active_count = sum(
            1 for fact in facts
            if source["guest_approved"] is True
            and source["valid_from"] <= active_day <= source["valid_to"]
            and fact["status"] in {"confirmed", "unknown", "needs_confirmation"}
            and fact["valid_from"] <= active_day <= fact["valid_to"]
        )
        if other_count + replacement_active_count > 400:
            raise ValueError("aggregate active hotel facts exceed the 400 fact limit")
        next_generation = expected_generation + 1
        connection.execute(delete(knowledge_facts).where(and_(
            knowledge_facts.c.hotel_id == hotel_id, knowledge_facts.c.source_id == source_id,
        )))
        connection.execute(delete(knowledge_media).where(and_(
            knowledge_media.c.hotel_id == hotel_id, knowledge_media.c.source_id == source_id,
        )))
        if facts:
            connection.execute(insert(knowledge_facts), [{
                "fact_id": fact["fact_id"], "hotel_id": hotel_id, "source_id": source_id,
                "source_version": source["version"], "section": fact.get("section", fact["topic"]),
                "fact_version": fact.get("fact_version", "1"), "status": fact["status"],
                "valid_from": fact["valid_from"], "valid_to": fact["valid_to"],
                "fact": fact, "imported_at": timestamp,
            } for fact in facts])
        if media:
            connection.execute(insert(knowledge_media), [{
                **{key: item.get(key) for key in (
                    "media_id", "source_id", "source_version", "fact_ids", "kind", "mime_type",
                    "byte_size", "sha256", "caption", "alt_text", "start_seconds", "end_seconds",
                    "duration_seconds", "captions_media_id", "guest_approved_whole_file",
                    "valid_from", "valid_to", "content",
                )}, "hotel_id": hotel_id,
            } for item in media])
        source_hash = _source_snapshot_hash(source, facts, media)
        connection.execute(update(knowledge_sources).where(and_(
            knowledge_sources.c.hotel_id == hotel_id,
            knowledge_sources.c.source_id == source_id,
        )).values(version=source["version"], scope=source["scope"],
                  guest_approved=source["guest_approved"], valid_from=source["valid_from"],
                  valid_to=source["valid_to"], source=source, source_hash=source_hash,
                  lifecycle_status="approved", last_success_at=timestamp, last_failure=None))
        connection.execute(update(hotels).where(and_(
            hotels.c.hotel_id == hotel_id,
            hotels.c.knowledge_generation == expected_generation,
        )).values(knowledge_generation=next_generation, updated_at=timestamp))
        result = {"status": "applied", "hotel_id": hotel_id, "source_id": source_id,
                  "generation": next_generation, "source_version": source["version"],
                  "source_hash": source_hash, "last_success_at": timestamp.isoformat()}
        connection.execute(insert(lifecycle_operations).values(
            operation_id=operation_id, hotel_id=hotel_id, source_id=source_id,
            operation_kind="refresh", payload_hash=payload_hash, result=result, created_at=timestamp,
        ))
    return result


def transition_source(
    engine: Engine, *, hotel_id: str, source_id: str, expected_generation: int,
    expected_version: str, expected_source_hash: str, operation_id: str,
    action: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Revoke or delete one source with CAS and durable operation replay."""
    if action not in {"revoke", "delete"}:
        raise ValueError("action must be revoke or delete")
    timestamp = (now or utcnow()).astimezone(UTC)
    payload_hash = _canonical_hash({"hotel_id": hotel_id, "source_id": source_id,
                                    "expected_generation": expected_generation,
                                    "expected_version": expected_version,
                                    "expected_source_hash": expected_source_hash, "action": action})
    if not operation_id or len(operation_id) > 128:
        raise ValueError("operation_id must contain 1–128 characters")
    with engine.begin() as connection:
        replay = _operation_replay(connection, operation_id, hotel_id, source_id,
                                   action, payload_hash, timestamp)
        if replay is not None:
            return replay
        hotel = connection.execute(select(hotels).where(
            hotels.c.hotel_id == hotel_id,
        ).with_for_update()).mappings().first()
        if hotel is None:
            raise ScopeError("hotel scope is invalid")
        replay = _operation_replay(connection, operation_id, hotel_id, source_id,
                                   action, payload_hash, timestamp)
        if replay is not None:
            return replay
        source = connection.execute(select(knowledge_sources).where(and_(
            knowledge_sources.c.hotel_id == hotel_id,
            knowledge_sources.c.source_id == source_id,
        )).with_for_update()).mappings().first()
        if source is None:
            raise ScopeError("selected source does not exist")
        if (hotel["knowledge_generation"] != expected_generation or source["version"] != expected_version
                or source["source_hash"] != expected_source_hash):
            raise VersionConflict("selected source or hotel generation changed")
        next_generation = expected_generation + 1
        if action == "revoke":
            connection.execute(update(knowledge_sources).where(and_(
                knowledge_sources.c.hotel_id == hotel_id, knowledge_sources.c.source_id == source_id,
            )).values(guest_approved=False, lifecycle_status="revoked"))
        else:
            connection.execute(delete(knowledge_media).where(and_(
                knowledge_media.c.hotel_id == hotel_id, knowledge_media.c.source_id == source_id,
            )))
            connection.execute(delete(knowledge_facts).where(and_(
                knowledge_facts.c.hotel_id == hotel_id, knowledge_facts.c.source_id == source_id,
            )))
            connection.execute(update(knowledge_sources).where(and_(
                knowledge_sources.c.hotel_id == hotel_id, knowledge_sources.c.source_id == source_id,
            )).values(guest_approved=False, lifecycle_status="deleted"))
        connection.execute(update(hotels).where(and_(
            hotels.c.hotel_id == hotel_id,
            hotels.c.knowledge_generation == expected_generation,
        )).values(knowledge_generation=next_generation, updated_at=timestamp))
        result = {"status": "applied", "hotel_id": hotel_id, "source_id": source_id,
                  "generation": next_generation, "source_version": source["version"],
                  "source_hash": source["source_hash"], "lifecycle_status": action + "d" if action == "revoke" else "deleted"}
        connection.execute(insert(lifecycle_operations).values(
            operation_id=operation_id, hotel_id=hotel_id, source_id=source_id,
            operation_kind=action, payload_hash=payload_hash, result=result, created_at=timestamp,
        ))
    return result


def record_source_failure(engine: Engine, hotel_id: str, source_id: str, failure_code: str,
                         *, now: datetime | None = None) -> None:
    """Record a bounded, non-sensitive failure label without changing active permission."""
    safe_code = "".join(character for character in failure_code if character.isalnum() or character in "_-.")[:80]
    with engine.begin() as connection:
        connection.execute(update(knowledge_sources).where(and_(
            knowledge_sources.c.hotel_id == hotel_id,
            knowledge_sources.c.source_id == source_id,
        )).values(last_failure=safe_code or "refresh_failed"))


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
    created_at = utcnow()
    requested_expiry = expires_at.astimezone(UTC)
    expires_at = min(requested_expiry, created_at + SESSION_CONTENT_MAX_AGE)
    with engine.begin() as connection:
        connection.execute(insert(sessions).values(
            session_id=session_id, hotel_id=hotel_id, state_version=0,
            created_at=created_at, expires_at=expires_at,
        ))


def _purge_session_content(connection: Any, session_id: str, hotel_id: str, now: datetime) -> None:
    """Remove session content while retaining only recent property quota reservations."""
    reservation_cutoff = now - ADMISSION_RESERVATION_WINDOW
    recent = connection.execute(select(
        requests.c.created_at, requests.c.lease_owner, requests.c.lease_expires_at,
        requests.c.provider_calls,
        requests.c.status,
    ).where(and_(
        requests.c.session_id == session_id,
        requests.c.hotel_id == hotel_id,
        requests.c.created_at > reservation_cutoff,
        requests.c.lease_owner.is_not(None),
    ))).mappings().all()
    connection.execute(delete(requests).where(and_(
        requests.c.session_id == session_id,
        requests.c.hotel_id == hotel_id,
    )))

    # Keep recent admission accounting for the B10 property window without retaining
    # client IDs, content hashes, responses, trace payloads, or session correlation.
    quota_session_id = str(uuid.uuid4())
    for row in recent:
        connection.execute(insert(requests).values(
            request_id=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            session_id=quota_session_id,
            hotel_id=hotel_id,
            expected_version=0,
            payload_hash=hashlib.sha256(b"redacted").hexdigest(),
            status=row["status"],
            provider_calls=row["provider_calls"],
            lease_owner=str(uuid.uuid4()),
            lease_expires_at=row["lease_expires_at"],
            response=None,
            error_code=None,
            created_at=row["created_at"],
        ))

    connection.execute(delete(messages).where(and_(
        messages.c.session_id == session_id, messages.c.hotel_id == hotel_id,
    )))
    connection.execute(delete(guest_briefs).where(and_(
        guest_briefs.c.session_id == session_id, guest_briefs.c.hotel_id == hotel_id,
    )))
    connection.execute(delete(guest_language_preferences).where(and_(
        guest_language_preferences.c.session_id == session_id,
        guest_language_preferences.c.hotel_id == hotel_id,
    )))
    connection.execute(delete(guest_brief_source_utterances).where(and_(
        guest_brief_source_utterances.c.session_id == session_id,
        guest_brief_source_utterances.c.hotel_id == hotel_id,
    )))
    connection.execute(delete(guest_brief_receipts).where(and_(
        guest_brief_receipts.c.session_id == session_id,
        guest_brief_receipts.c.hotel_id == hotel_id,
    )))
    connection.execute(delete(room_advice_selections).where(and_(
        room_advice_selections.c.session_id == session_id,
        room_advice_selections.c.hotel_id == hotel_id,
    )))
    connection.execute(delete(room_advice_results).where(and_(
        room_advice_results.c.session_id == session_id,
        room_advice_results.c.hotel_id == hotel_id,
    )))


def _lock_session_requests_for_cleanup(connection: Any, session_id: str, hotel_id: str) -> None:
    # complete_request locks a request row before the parent session. Cleanup uses
    # the same order to avoid a request/session deadlock during late commits.
    connection.execute(select(requests.c.request_id).where(and_(
        requests.c.session_id == session_id,
        requests.c.hotel_id == hotel_id,
    )).order_by(requests.c.request_id).with_for_update()).all()


def delete_guest_session(
    engine: Engine, *, session_id: str, hotel_id: str, now: datetime | None = None,
) -> bool:
    """Expire then erase one guest session; return false for an absent/foreign session."""
    timestamp = (now or utcnow()).astimezone(UTC)
    with engine.begin() as connection:
        updated = connection.execute(update(sessions).where(and_(
            sessions.c.session_id == session_id,
            sessions.c.hotel_id == hotel_id,
            sessions.c.expires_at > timestamp,
        )).values(expires_at=timestamp))
    # Keep phase one separate so in-flight admission/completion sees expiry before
    # cleanup. Phase two locks requests before the session, matching completion's
    # request-then-session order while serializing duplicate cleanup.
    with engine.begin() as connection:
        _lock_session_requests_for_cleanup(connection, session_id, hotel_id)
        session = connection.execute(select(
            sessions.c.session_id, sessions.c.hotel_id,
        ).where(and_(sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id))
         .with_for_update()).mappings().first()
        if session is None:
            return False
        _purge_session_content(connection, session_id, hotel_id, utcnow() if now is None else timestamp)
        connection.execute(delete(sessions).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
        )))
    return updated.rowcount == 1 or session is not None


def purge_expired_sessions(
    engine: Engine, *, now: datetime | None = None, batch_size: int = 100,
) -> int:
    """Purge expired sessions and aged orphan quota metadata using a controllable UTC clock."""
    timestamp = (now or utcnow()).astimezone(UTC)
    with engine.connect() as connection:
        expired = connection.execute(select(
            sessions.c.session_id, sessions.c.hotel_id,
        ).where(sessions.c.expires_at <= timestamp).order_by(
            sessions.c.expires_at, sessions.c.session_id,
        ).limit(max(1, min(batch_size, 1000)))).mappings().all()
    purged = 0
    for row in expired:
        with engine.begin() as connection:
            _lock_session_requests_for_cleanup(connection, row["session_id"], row["hotel_id"])
            current = connection.execute(select(
                sessions.c.session_id,
            ).where(and_(
                sessions.c.session_id == row["session_id"],
                sessions.c.hotel_id == row["hotel_id"],
                sessions.c.expires_at <= timestamp,
            )).with_for_update()).first()
            if current is None:
                continue
            cleanup_now = utcnow() if now is None else timestamp
            _purge_session_content(connection, row["session_id"], row["hotel_id"], cleanup_now)
            connection.execute(delete(sessions).where(and_(
                sessions.c.session_id == row["session_id"],
                sessions.c.hotel_id == row["hotel_id"],
            )))
            purged += 1
    # Session rows are gone after deletion, so reservation rows are safe to remove
    # once the complete property admission window has elapsed.
    with engine.begin() as connection:
        _purge_orphan_session_content(connection)
        cleanup_timestamp = utcnow() if now is None else timestamp
        connection.execute(delete(requests).where(and_(
            requests.c.created_at <= cleanup_timestamp - ADMISSION_RESERVATION_WINDOW,
            ~select(sessions.c.session_id).where(and_(
                sessions.c.session_id == requests.c.session_id,
                sessions.c.hotel_id == requests.c.hotel_id,
            )).exists(),
        )))
    return purged


def _purge_orphan_session_content(connection: Any) -> None:
    """Erase session-derived rows left by older writers after their parent disappeared."""
    session_content_tables = (
        messages,
        guest_briefs,
        guest_language_preferences,
        guest_brief_source_utterances,
        guest_brief_receipts,
        room_advice_selections,
        room_advice_results,
    )
    for table in session_content_tables:
        parent_exists = select(sessions.c.session_id).where(and_(
            sessions.c.session_id == table.c.session_id,
            sessions.c.hotel_id == table.c.hotel_id,
        )).correlate(table).exists()
        connection.execute(delete(table).where(~parent_exists))


def next_session_expiry(
    engine: Engine, *, now: datetime | None = None, hotel_id: str | None = None,
) -> datetime | None:
    """Return the nearest due/future expiry for the app lifecycle wait calculation."""
    query = select(func.min(sessions.c.expires_at))
    if hotel_id is not None:
        query = query.where(sessions.c.hotel_id == hotel_id)
    with engine.connect() as connection:
        value = connection.scalar(query)
    return value.astimezone(UTC) if value is not None else None


def _brief_snapshot(row: Any | None) -> GuestBriefSnapshot:
    if row is None:
        return GuestBriefSnapshot(0, {"dates": {"check_in": None, "check_out": None, "nights": None},
                                   "party": {"adults": None, "children": []}}, ())
    return GuestBriefSnapshot(int(row["brief_version"]), dict(row["data"]),
                              tuple(row["pending_fields"] or ()))


def get_guest_brief(
    engine: Engine, *, session_id: str, hotel_id: str,
    timeout_seconds: float | None = None,
) -> GuestBriefSnapshot:
    """Read the canonical brief in its hotel/session scope; absent briefs are version zero."""
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        session = connection.execute(select(sessions.c.session_id).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.expires_at > utcnow(),
        ))).first()
        if session is None:
            raise ScopeError("session scope is invalid")
        row = connection.execute(select(guest_briefs).where(and_(
            guest_briefs.c.session_id == session_id, guest_briefs.c.hotel_id == hotel_id,
        ))).mappings().first()
        return _brief_snapshot(row)


def _room_advice_currentness(connection: Any, row: Any, now: datetime) -> str:
    hotel = connection.execute(select(hotels).where(hotels.c.hotel_id == row["hotel_id"])).mappings().first()
    session = connection.execute(select(sessions).where(and_(
        sessions.c.session_id == row["session_id"], sessions.c.hotel_id == row["hotel_id"],
        sessions.c.expires_at > now,
    ))).first()
    if hotel is None or session is None:
        return "stale"
    brief_version = connection.scalar(select(guest_briefs.c.brief_version).where(and_(
        guest_briefs.c.session_id == row["session_id"], guest_briefs.c.hotel_id == row["hotel_id"],
    ))) or 0
    if (brief_version != row["brief_version"]
            or hotel["knowledge_generation"] != row["source_generation"]
            or hotel["config_version"] != row["config_version"]
            or row["algorithm_version"] != ROOM_ADVICE_ALGORITHM_VERSION):
        return "stale"
    latest_result_version = connection.scalar(select(room_advice_results.c.result_version).where(
        room_advice_results.c.session_id == row["session_id"],
    ).order_by(room_advice_results.c.result_version.desc()).limit(1))
    if latest_result_version != row["result_version"]:
        return "stale"
    refs = row["source_refs"] or []
    if refs and not _validate_evidence_on_connection(connection, row["hotel_id"], refs, now).eligible:
        return "stale"
    return "current"


def save_room_advice_result(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str,
    payload: dict[str, Any], brief_version: int, source_generation: int,
    config_version: str, source_refs: list[dict[str, Any]],
    expected_state_version: int,
    policy_version: str | None = None, price_version: str | None = None,
    algorithm_version: str = ROOM_ADVICE_ALGORITHM_VERSION,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Atomically persist a checked result only while its input dependencies are still current."""
    now = utcnow()
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        session = connection.execute(select(sessions).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.expires_at > now,
        )).with_for_update()).mappings().first()
        hotel = connection.execute(select(hotels).where(
            hotels.c.hotel_id == hotel_id,
        ).with_for_update()).mappings().first()
        if session is None or hotel is None:
            raise ScopeError("room advice scope is invalid")
        now = utcnow()
        if session["expires_at"] <= now:
            raise ScopeError("room advice session expired before commit")
        existing = connection.execute(select(room_advice_results).where(and_(
            room_advice_results.c.session_id == session_id,
            room_advice_results.c.request_id == request_id,
        ))).mappings().first()
        dependency = {
            "brief_version": brief_version, "source_generation": source_generation,
            "config_version": config_version, "policy_version": policy_version,
            "price_version": price_version, "algorithm_version": algorithm_version,
            "source_refs": source_refs,
        }
        fingerprint = _canonical_hash(dependency)
        if existing is not None:
            if existing["dependency_fingerprint"] != fingerprint or existing["payload"] != payload:
                raise IdempotencyConflict("room advice request id was reused with different result content")
            now = utcnow()
            if session["expires_at"] <= now:
                raise ScopeError("room advice session expired before result replay")
            result = dict(existing)
            result["currentness"] = _room_advice_currentness(connection, existing, now)
            selection = connection.execute(select(room_advice_selections).where(and_(
                room_advice_selections.c.session_id == session_id,
                room_advice_selections.c.hotel_id == hotel_id,
            ))).mappings().first()
            result["selection"] = _selection_payload(selection, existing)
            return result
        if session["state_version"] != expected_state_version:
            raise VersionConflict("guest session advanced before the room advice result was committed")
        prior_for_turn = connection.execute(select(room_advice_results.c.result_id).where(and_(
            room_advice_results.c.session_id == session_id,
            room_advice_results.c.session_state_version == expected_state_version,
        ))).first()
        if prior_for_turn is not None:
            raise VersionConflict("a room advice result already exists for this guest turn")
        brief_row = connection.execute(select(guest_briefs.c.brief_version).where(and_(
            guest_briefs.c.session_id == session_id, guest_briefs.c.hotel_id == hotel_id,
        ))).scalar_one_or_none()
        current_brief_version = int(brief_row or 0)
        if (current_brief_version != brief_version
                or hotel["knowledge_generation"] != source_generation
                or hotel["config_version"] != config_version):
            raise StaleSource("room advice dependencies changed before result commit")
        decision = _validate_evidence_on_connection(connection, hotel_id, source_refs, now)
        if source_refs and not decision.eligible:
            raise StaleSource("room advice source evidence is no longer eligible")
        now = utcnow()
        if session["expires_at"] <= now:
            raise ScopeError("room advice session expired before commit")
        result_version = int(connection.scalar(select(room_advice_results.c.result_version).where(
            room_advice_results.c.session_id == session_id,
        ).order_by(room_advice_results.c.result_version.desc()).limit(1)) or 0) + 1
        result_id = str(uuid.uuid4())
        connection.execute(insert(room_advice_results).values(
            result_id=result_id, session_id=session_id, hotel_id=hotel_id,
            request_id=request_id, result_version=result_version,
            session_state_version=expected_state_version,
            brief_version=brief_version, source_generation=source_generation,
            config_version=config_version, policy_version=policy_version,
            price_version=price_version, algorithm_version=algorithm_version,
            dependency_fingerprint=fingerprint,
            source_refs=source_refs, payload=payload, created_at=now,
        ))
        saved = connection.execute(select(room_advice_results).where(
            room_advice_results.c.result_id == result_id,
        )).mappings().one()
        result = dict(saved)
        result["currentness"] = "current"
        result["selection"] = None
        return result


def _selection_payload(selection: Any | None, result: Any) -> dict[str, Any] | None:
    if selection is None or selection["result_id"] != result["result_id"]:
        return None
    return {"result_id": selection["result_id"], "result_version": selection["result_version"],
            "option_id": selection["option_id"], "updated_at": selection["updated_at"].isoformat()}


def get_room_advice_result(
    engine: Engine, *, session_id: str, hotel_id: str,
    result_id: str | None = None, timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        query = select(room_advice_results).where(and_(
            room_advice_results.c.session_id == session_id,
            room_advice_results.c.hotel_id == hotel_id,
        ))
        if result_id is not None:
            query = query.where(room_advice_results.c.result_id == result_id)
        else:
            query = query.order_by(room_advice_results.c.result_version.desc()).limit(1)
        row = connection.execute(query).mappings().first()
        if row is None:
            return None
        result = dict(row)
        result["currentness"] = _room_advice_currentness(connection, row, utcnow())
        selection = connection.execute(select(room_advice_selections).where(and_(
            room_advice_selections.c.session_id == session_id,
            room_advice_selections.c.hotel_id == hotel_id,
        ))).mappings().first()
        result["selection"] = _selection_payload(selection, row) if result["currentness"] == "current" else None
        return result


def update_room_advice_presentation(
    engine: Engine, *, session_id: str, hotel_id: str, result_id: str,
    expected_result_version: int, expected_payload: dict[str, Any],
    payload: dict[str, Any], expected_language_revision: int,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Persist localized display text without changing the checked advice decision.

    The stored result version and dependency fingerprint remain stable. The caller
    supplies the payload it read; this compare-and-set accepts only changes to
    presentation labels and rendered rationale/question text and metadata.
    """
    def decision_content(value: dict[str, Any]) -> dict[str, Any]:
        content = json.loads(json.dumps(value, ensure_ascii=False))
        content.pop("presentation_labels", None)
        content.pop("presentation_locale", None)
        claim_codes = {
            "party_fit", "bed_setup", "reference_price", "policy_confirmation",
            "accessibility_confirmation", "preference_tradeoff", "charges_confirmation",
        }
        def checked_key(actual: Any, expected: str) -> str:
            if actual is not None and actual != expected:
                raise ValueError("localized room advice contains an invalid presentation key")
            return expected

        def question_key(question: dict[str, Any]) -> str:
            field = question.get("field")
            if (field == "room_requirements.hard_accessibility_needs"
                    and question.get("presentation_key") == "question.accessibility_confirmation"):
                # The checked producer stores this marker only for a saved,
                # non-pending hard need; preserve it through language-only CAS.
                return "question.accessibility_confirmation"
            if field == "room_requirements.budget_strength":
                return "question.budget_strength"
            unknowns = set(content.get("explanation_inputs", {}).get("unknowns", ()))
            conflicts = set(content.get("explanation_inputs", {}).get("conflicts", ()))
            if "rate_basis" in unknowns:
                return "question.rate_basis"
            if "rate_validity_window" in unknowns:
                return "question.rate_validity_window"
            if field == "room_advice" and conflicts:
                conflict = min(conflicts)
                return {
                    "hard_budget_exceeded": "question.hard_budget_exceeded",
                    "source_fact_conflict": "question.source_fact_conflict",
                }.get(conflict, "question.room_rule_conflict")
            if field in {"dates.check_in", "dates.check_out"}:
                return "question.dates"
            if field == "party.adults":
                return "question.party"
            if field == "party.children.age" or (
                isinstance(field, str) and field.startswith("party.children.") and field.endswith(".age")
            ):
                return "question.age"
            if field == "room_advice" or isinstance(field, str) and field.startswith("room_requirements."):
                return "question.room"
            return "question.generic"

        for option in content.get("options", ()):
            if not isinstance(option, dict):
                continue
            for item in option.get("rationale", ()):
                if isinstance(item, dict):
                    claim_code = item.get("claim_code")
                    if claim_code not in claim_codes:
                        raise ValueError("localized room advice contains an invalid rationale code")
                    item["presentation_key"] = checked_key(
                        item.get("presentation_key"), f"claim.{claim_code}",
                    )
                    for key in ("text", "locale", "locale_fallback"):
                        item.pop(key, None)
        for question in content.get("questions", ()):
            if isinstance(question, dict):
                question["presentation_key"] = checked_key(
                    question.get("presentation_key"), question_key(question),
                )
                for key in ("reason", "locale", "locale_fallback"):
                    question.pop(key, None)
        return content

    if decision_content(expected_payload) != decision_content(payload):
        raise ValueError("localized room advice changed checked decision content")
    now = utcnow()
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        session = connection.execute(select(sessions.c.session_id).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.expires_at > now,
        )).with_for_update()).first()
        if session is None:
            raise ScopeError("room advice presentation session is no longer current")
        row = connection.execute(select(room_advice_results).where(and_(
            room_advice_results.c.result_id == result_id,
            room_advice_results.c.session_id == session_id,
            room_advice_results.c.hotel_id == hotel_id,
        )).with_for_update()).mappings().first()
        if (row is None or row["result_version"] != expected_result_version
                or decision_content(row["payload"]) != decision_content(expected_payload)):
            raise VersionConflict("room advice changed before its presentation was updated")
        if _room_advice_currentness(connection, row, now) != "current":
            raise StaleSource("room advice dependencies changed before presentation update")
        preference = connection.execute(select(guest_language_preferences.c.revision).where(and_(
            guest_language_preferences.c.session_id == session_id,
            guest_language_preferences.c.hotel_id == hotel_id,
        )).with_for_update()).scalar_one_or_none()
        if int(preference or 0) != expected_language_revision:
            raise VersionConflict("guest language preference changed before presentation update")
        connection.execute(update(room_advice_results).where(
            room_advice_results.c.result_id == result_id,
        ).values(payload=payload))
        updated = connection.execute(select(room_advice_results).where(
            room_advice_results.c.result_id == result_id,
        )).mappings().one()
        result = dict(updated)
        result["currentness"] = "current"
        selection = connection.execute(select(room_advice_selections).where(and_(
            room_advice_selections.c.session_id == session_id,
            room_advice_selections.c.hotel_id == hotel_id,
        ))).mappings().first()
        result["selection"] = _selection_payload(selection, updated)
        return result


def select_room_advice_option(
    engine: Engine, *, session_id: str, hotel_id: str, result_id: str,
    expected_result_version: int, option_id: str, timeout_seconds: float | None = None,
) -> dict[str, Any]:
    now = utcnow()
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        session = connection.execute(select(sessions).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.expires_at > now,
        )).with_for_update()).mappings().first()
        # Match source lifecycle's hotel-row lock so revocation/refresh cannot race a selection.
        hotel_lock = connection.execute(select(hotels.c.hotel_id).where(
            hotels.c.hotel_id == hotel_id,
        ).with_for_update()).first()
        result = connection.execute(select(room_advice_results).where(and_(
            room_advice_results.c.result_id == result_id,
            room_advice_results.c.session_id == session_id,
            room_advice_results.c.hotel_id == hotel_id,
        )).with_for_update()).mappings().first()
        if session is None or hotel_lock is None or result is None:
            raise ScopeError("room advice result scope is invalid")
        now = utcnow()
        if session["expires_at"] <= now:
            raise ScopeError("room advice session expired before selection")
        if result["result_version"] != expected_result_version:
            raise VersionConflict("room advice result version changed")
        if _room_advice_currentness(connection, result, now) != "current":
            raise StaleSource("room advice result is stale")
        options = result["payload"].get("options", [])
        if not any(isinstance(option, dict) and option.get("option_id") == option_id for option in options):
            raise ScopeError("room advice option is not part of this result")
        values = {"hotel_id": hotel_id, "result_id": result_id,
                  "result_version": expected_result_version, "option_id": option_id, "updated_at": now}
        existing = connection.execute(select(room_advice_selections.c.session_id).where(and_(
            room_advice_selections.c.session_id == session_id,
            room_advice_selections.c.hotel_id == hotel_id,
        )).with_for_update()).first()
        now = utcnow()
        if session["expires_at"] <= now:
            raise ScopeError("room advice session expired before selection")
        values["updated_at"] = now
        if existing:
            connection.execute(update(room_advice_selections).where(
                room_advice_selections.c.session_id == session_id,
            ).values(**values))
        else:
            connection.execute(insert(room_advice_selections).values(session_id=session_id, **values))
        return {"result_id": result_id, "result_version": expected_result_version,
                "option_id": option_id, "updated_at": now.isoformat()}


def _brief_receipt(row: Any) -> GuestBriefReceipt:
    ref = GuestBriefSourceRef(
        source_utterance_id=row["source_utterance_id"], request_id=row["request_id"],
        fields=tuple(row["source_fields"] or ()),
    )
    return GuestBriefReceipt(
        request_id=row["request_id"], status=row["status"],
        brief_version_before=int(row["brief_version_before"]),
        brief_version_after=int(row["brief_version_after"]),
        applied_delta=dict(row["applied_delta"] or {}), source_refs=(ref,),
        answer_status=row["answer_status"], brief_version_used=row["brief_version_used"],
    )


def get_guest_brief_receipt(
    engine: Engine, *, session_id: str, hotel_id: str, receipt_id: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    """Load an applied receipt and current brief only for its owning session and hotel."""
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        row = connection.execute(select(guest_brief_receipts).where(and_(
            guest_brief_receipts.c.request_id == receipt_id,
            guest_brief_receipts.c.session_id == session_id,
            guest_brief_receipts.c.hotel_id == hotel_id,
        ))).mappings().first()
        if row is None:
            return None
        current = connection.execute(select(guest_briefs).where(and_(
            guest_briefs.c.session_id == session_id, guest_briefs.c.hotel_id == hotel_id,
        ))).mappings().first()
        return {
            "brief": _brief_snapshot(current), "receipt": _brief_receipt(row),
            "answer_payload": row["answer_payload"] if isinstance(row["answer_payload"], dict) else {},
            "brief_dependent": bool(row["brief_dependent"]),
        }


def get_guest_brief_source_utterance(
    engine: Engine, *, session_id: str, hotel_id: str, receipt_id: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    """Load the durable original utterance only through its owning applied receipt."""
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        row = connection.execute(select(
            guest_brief_source_utterances.c.source_utterance_id,
            guest_brief_source_utterances.c.request_id,
            guest_brief_source_utterances.c.content,
            guest_brief_source_utterances.c.fields,
        ).select_from(guest_brief_receipts.join(
            guest_brief_source_utterances,
            guest_brief_receipts.c.source_utterance_id
            == guest_brief_source_utterances.c.source_utterance_id,
        )).where(and_(
            guest_brief_receipts.c.request_id == receipt_id,
            guest_brief_receipts.c.session_id == session_id,
            guest_brief_receipts.c.hotel_id == hotel_id,
        ))).mappings().first()
        return dict(row) if row else None


def apply_guest_brief_patch(
    engine: Engine, *, context: GuestBriefContext, mutation: ValidatedGuestBriefPatch,
    payload_hash: str, timeout_seconds: float | None = None,
    now: datetime | None = None, deadline_monotonic: float | None = None,
    cancellation_event: Event | None = None,
) -> GuestBriefMutationResult:
    """CAS-commit canonical brief, durable guest utterance, delta, and receipt atomically."""
    checked_at = (now or utcnow()).astimezone(UTC)
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        session = connection.execute(select(sessions).where(and_(
            sessions.c.session_id == context.session_id,
            sessions.c.hotel_id == context.hotel_id,
            sessions.c.expires_at > checked_at,
        )).with_for_update()).mappings().first()
        if session is None:
            raise ScopeError("session scope is invalid")
        checked_at = (now or utcnow()).astimezone(UTC)
        if session["expires_at"] <= checked_at:
            raise ScopeError("session expired before brief commit")
        prior_receipt = connection.execute(select(guest_brief_receipts).where(
            guest_brief_receipts.c.request_id == context.request_id,
        )).mappings().first()
        if prior_receipt is not None:
            if (prior_receipt["session_id"] != context.session_id
                    or prior_receipt["hotel_id"] != context.hotel_id
                    or prior_receipt["payload_hash"] != payload_hash):
                raise IdempotencyConflict("request_id was already used with different brief data")
            current = connection.execute(select(guest_briefs).where(and_(
                guest_briefs.c.session_id == context.session_id,
                guest_briefs.c.hotel_id == context.hotel_id,
            ))).mappings().first()
            return GuestBriefMutationResult(_brief_snapshot(current), _brief_receipt(prior_receipt), True)

        current_row = connection.execute(select(guest_briefs).where(and_(
            guest_briefs.c.session_id == context.session_id,
            guest_briefs.c.hotel_id == context.hotel_id,
        )).with_for_update()).mappings().first()
        checked_at = (now or utcnow()).astimezone(UTC)
        if session["expires_at"] <= checked_at:
            raise ScopeError("session expired before brief commit")
        current = _brief_snapshot(current_row)
        if current.brief_version != context.expected_brief_version:
            raise VersionConflict("guest brief version changed")
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        checked_at = (now or utcnow()).astimezone(UTC)
        if session["expires_at"] <= checked_at:
            raise ScopeError("session expired before brief commit")
        before = current.brief_version
        changed = (mutation.data != current.data
                   or tuple(mutation.pending_fields) != current.pending_fields)
        after = before + 1 if changed else before
        status = mutation.status if changed else "no_change"
        if changed:
            if current_row is None:
                connection.execute(insert(guest_briefs).values(
                    session_id=context.session_id, hotel_id=context.hotel_id,
                    brief_version=after, data=mutation.data,
                    pending_fields=list(mutation.pending_fields), updated_at=checked_at,
                ))
            else:
                connection.execute(update(guest_briefs).where(and_(
                    guest_briefs.c.session_id == context.session_id,
                    guest_briefs.c.hotel_id == context.hotel_id,
                    guest_briefs.c.brief_version == before,
                )).values(brief_version=after, data=mutation.data,
                          pending_fields=list(mutation.pending_fields), updated_at=checked_at))
        connection.execute(insert(guest_brief_source_utterances).values(
            source_utterance_id=context.source_utterance_id,
            session_id=context.session_id, hotel_id=context.hotel_id,
            request_id=context.request_id, content=context.source_utterance,
            fields=list(mutation.source_fields), created_at=checked_at,
        ))
        connection.execute(insert(guest_brief_receipts).values(
            request_id=context.request_id, session_id=context.session_id,
            hotel_id=context.hotel_id, expected_brief_version=before,
            payload_hash=payload_hash, status=status,
            brief_version_before=before, brief_version_after=after,
            applied_delta=mutation.applied_delta,
            source_utterance_id=context.source_utterance_id,
            source_fields=list(mutation.source_fields), answer_status="pending",
            brief_version_used=after if changed else None, brief_dependent=changed,
            answer_payload={
                "turn_intents": list(context.turn_intents),
                "authorized_targets": list(context.authorized_targets),
            },
            created_at=checked_at,
        ))
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        brief = GuestBriefSnapshot(after, mutation.data, tuple(mutation.pending_fields))
        source_ref = GuestBriefSourceRef(context.source_utterance_id, context.request_id,
                                         tuple(mutation.source_fields))
        receipt = GuestBriefReceipt(context.request_id, status, before, after,
                                    mutation.applied_delta, (source_ref,), "pending",
                                    after if changed else None)
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        return GuestBriefMutationResult(brief, receipt)


def record_guest_brief_answer(
    engine: Engine, *, context: GuestBriefContext, brief_version_used: int,
    answer_status: str, answer_payload: dict[str, Any],
    evidence_bindings: list[EvidenceBinding | dict[str, Any]] | None = None,
    expected_generation: int | None = None,
    timeout_seconds: float | None = None,
) -> None:
    """Persist a terminal receipt outcome; completion freshness is checked separately."""
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        existing_payload = connection.execute(select(guest_brief_receipts.c.answer_payload).where(and_(
            guest_brief_receipts.c.request_id == context.request_id,
            guest_brief_receipts.c.session_id == context.session_id,
            guest_brief_receipts.c.hotel_id == context.hotel_id,
        ))).scalar_one_or_none() or {}
        if not isinstance(existing_payload, dict):
            existing_payload = {}
        updated = connection.execute(update(guest_brief_receipts).where(and_(
            guest_brief_receipts.c.request_id == context.request_id,
            guest_brief_receipts.c.session_id == context.session_id,
            guest_brief_receipts.c.hotel_id == context.hotel_id,
        )).values(answer_status=answer_status, brief_version_used=brief_version_used,
                  answer_payload={
                      **answer_payload,
                      "turn_intents": list(existing_payload.get("turn_intents", context.turn_intents)),
                      "authorized_targets": list(existing_payload.get("authorized_targets", context.authorized_targets)),
                  }, brief_dependent=True))
        if updated.rowcount != 1:
            raise ScopeError("guest brief receipt scope is invalid")


def get_session(
    engine: Engine, session_id: str, *, timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        row = connection.execute(select(sessions).where(sessions.c.session_id == session_id)).mappings().first()
    return dict(row) if row else None


def get_language_preference(
    engine: Engine, *, session_id: str, hotel_id: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        row = connection.execute(select(guest_language_preferences).where(and_(
            guest_language_preferences.c.session_id == session_id,
            guest_language_preferences.c.hotel_id == hotel_id,
        ))).mappings().first()
    return dict(row) if row else None


def commit_language_preference(
    engine: Engine, *, session_id: str, hotel_id: str, language_tag: str,
    source: str, expected_revision: int, timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Commit one scoped preference change; identical explicit choices are no-ops."""
    if source not in {"explicit", "inferred", "fallback"}:
        raise ValueError("Invalid language preference provenance.")
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        session = connection.execute(select(sessions.c.expires_at).where(and_(
            sessions.c.session_id == session_id,
            sessions.c.hotel_id == hotel_id,
        )).with_for_update()).mappings().first()
        # Sample the wall clock after acquiring the owning-session lock. A DELETE
        # or expiry purge that committed while this writer waited must fence it out.
        if session is None or session["expires_at"] <= utcnow():
            raise ScopeError("session scope is invalid")
        current = connection.execute(select(guest_language_preferences).where(and_(
            guest_language_preferences.c.session_id == session_id,
            guest_language_preferences.c.hotel_id == hotel_id,
        )).with_for_update()).mappings().first()
        actual_revision = int(current["revision"]) if current else 0
        if actual_revision != expected_revision:
            return dict(current) if current else {
                "session_id": session_id, "hotel_id": hotel_id, "language_tag": "und",
                "source": "fallback", "revision": 0, "updated_at": utcnow(),
            }
        if current and current["language_tag"] == language_tag:
            if source == "explicit" and current["source"] != "explicit":
                connection.execute(update(guest_language_preferences).where(and_(
                    guest_language_preferences.c.session_id == session_id,
                    guest_language_preferences.c.hotel_id == hotel_id,
                )).values(source="explicit", updated_at=utcnow()))
                return {**dict(current), "source": "explicit", "updated_at": utcnow()}
            return dict(current)
        revision = (int(current["revision"]) + 1) if current else 1
        values = {
            "session_id": session_id, "hotel_id": hotel_id,
            "language_tag": language_tag, "source": source,
            "revision": revision, "updated_at": utcnow(),
        }
        if current:
            connection.execute(update(guest_language_preferences).where(and_(
                guest_language_preferences.c.session_id == session_id,
                guest_language_preferences.c.hotel_id == hotel_id,
            )).values(**values))
        else:
            connection.execute(insert(guest_language_preferences).values(**values))
        return values


def recent_messages(
    engine: Engine, session_id: str, hotel_id: str, *, limit: int = 8,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    now = utcnow()
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        rows = connection.execute(
            select(messages.c.role, messages.c.content, messages.c.evidence_bindings)
            .where(and_(messages.c.session_id == session_id, messages.c.hotel_id == hotel_id))
            .order_by(messages.c.sequence.desc()).limit(limit)
        ).all()
        projected = []
        for row in reversed(rows):
            bindings = row.evidence_bindings or []
            if row.role == "assistant" and bindings:
                decision = _validate_evidence_on_connection(connection, hotel_id, bindings, now)
                if not decision.eligible:
                    continue
            projected.append({"role": row.role, "content": row.content})
    return projected


def reserve_request(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str, question: str,
    timeout_seconds: float | None = None,
    deadline_monotonic: float | None = None,
    cancellation_event: Event | None = None,
    limits: GuestAdmissionLimits | None = None,
    lease_owner: str | None = None,
    lease_until: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    digest = request_payload_hash(question)
    if limits is None:
        # Internal child reservations keep their existing replay record but do not
        # consume a guest turn or in-flight slot of their own.
        lease_owner = None
        lease_until = None
    if limits is not None and lease_owner is None:
        lease_owner = str(uuid.uuid4())
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        connection.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))",
        ), {"lock_key": f"staylead:guest-admission:hotel:{hotel_id}"})
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        session = connection.execute(select(sessions).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
        )).with_for_update()).mappings().first()
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        # Admission time must be sampled after both serialization locks. A request
        # queued behind another reservation must count that reservation even if
        # it began waiting before the earlier request committed.
        timestamp = (now or utcnow()).astimezone(UTC)
        if session is None or session["expires_at"] <= timestamp:
            raise ScopeError("session scope is invalid")
        if limits is not None and lease_until is None:
            remaining = limits.lease_seconds
            if deadline_monotonic is not None:
                remaining = min(remaining, max(0.0, deadline_monotonic - time.monotonic()))
            lease_until = timestamp + timedelta(seconds=remaining)
        if lease_until is not None:
            lease_until = lease_until.astimezone(UTC)
        inserted = connection.execute(pg_insert(requests).values(
            session_id=session_id, request_id=request_id, hotel_id=hotel_id,
            expected_version=session["state_version"], payload_hash=digest,
            status="processing", created_at=timestamp,
            provider_calls=0, lease_owner=lease_owner, lease_expires_at=lease_until,
        ).on_conflict_do_nothing().returning(requests.c.request_id))
        # psycopg may report rowcount=-1 for INSERT ... RETURNING; use the
        # returned row to distinguish a fresh reservation from a replay.
        if inserted.scalar_one_or_none() is not None:
            if limits is not None:
                boundary = timestamp - timedelta(seconds=limits.window_seconds)
                hotel_turns = connection.scalar(select(func.count()).select_from(requests).where(and_(
                    requests.c.hotel_id == hotel_id, requests.c.created_at > boundary,
                    requests.c.created_at <= timestamp,
                    requests.c.lease_owner.is_not(None),
                ))) or 0
                if hotel_turns > limits.turns_per_hotel:
                    oldest = connection.scalar(select(func.min(requests.c.created_at)).where(and_(
                        requests.c.hotel_id == hotel_id, requests.c.created_at > boundary,
                        requests.c.created_at <= timestamp,
                        requests.c.lease_owner.is_not(None),
                    )))
                    raise QuotaExceeded("hotel_turns", int((oldest + timedelta(
                        seconds=limits.window_seconds) - timestamp).total_seconds() + 0.999))
                session_turns = connection.scalar(select(func.count()).select_from(requests).where(and_(
                    requests.c.session_id == session_id, requests.c.created_at > boundary,
                    requests.c.created_at <= timestamp,
                    requests.c.lease_owner.is_not(None),
                ))) or 0
                if session_turns > limits.turns_per_session:
                    oldest = connection.scalar(select(func.min(requests.c.created_at)).where(and_(
                        requests.c.session_id == session_id, requests.c.created_at > boundary,
                        requests.c.created_at <= timestamp,
                        requests.c.lease_owner.is_not(None),
                    )))
                    raise QuotaExceeded("session_turns", int((oldest + timedelta(
                        seconds=limits.window_seconds) - timestamp).total_seconds() + 0.999))
                active_hotel = connection.scalar(select(func.count()).select_from(requests).where(and_(
                    requests.c.hotel_id == hotel_id, requests.c.status == "processing",
                    requests.c.lease_expires_at > timestamp,
                ))) or 0
                if active_hotel > limits.in_flight_per_hotel:
                    soonest = connection.scalar(select(func.min(requests.c.lease_expires_at)).where(and_(
                        requests.c.hotel_id == hotel_id, requests.c.status == "processing",
                        requests.c.lease_expires_at > timestamp,
                    )))
                    raise QuotaExceeded("hotel_in_flight", int((soonest - timestamp).total_seconds() + 0.999))
                active_session = connection.scalar(select(func.count()).select_from(requests).where(and_(
                    requests.c.session_id == session_id, requests.c.status == "processing",
                    requests.c.lease_expires_at > timestamp,
                ))) or 0
                if active_session > limits.in_flight_per_session:
                    soonest = connection.scalar(select(func.min(requests.c.lease_expires_at)).where(and_(
                        requests.c.session_id == session_id, requests.c.status == "processing",
                        requests.c.lease_expires_at > timestamp,
                    )))
                    raise QuotaExceeded("session_in_flight", int((soonest - timestamp).total_seconds() + 0.999))
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
            # The worker may have committed the canonical brief and then lost its
            # acknowledgement to a timeout/cancellation. Recover the durable effect
            # by request ID so a same-ID replay never reapplies it or calls the model.
            receipt_row = connection.execute(select(guest_brief_receipts).where(and_(
                guest_brief_receipts.c.request_id == request_id,
                guest_brief_receipts.c.session_id == session_id,
                guest_brief_receipts.c.hotel_id == hotel_id,
            ))).mappings().first()
            if (row["error_code"] == "brief_apply_outcome_unknown"
                    and (receipt_row is None or receipt_row["brief_version_after"]
                         <= receipt_row["brief_version_before"])):
                raise RuntimeError("brief_apply_no_effect")
            if receipt_row is None:
                raise RuntimeError(row["error_code"] or "request_failed")
            connection.execute(update(guest_brief_receipts).where(and_(
                guest_brief_receipts.c.request_id == request_id,
                guest_brief_receipts.c.session_id == session_id,
                guest_brief_receipts.c.hotel_id == hotel_id,
            )).values(answer_status="failed"))
            current_brief = connection.execute(select(guest_briefs).where(and_(
                guest_briefs.c.session_id == session_id,
                guest_briefs.c.hotel_id == hotel_id,
            ))).mappings().first()
            response = {
                "request_id": request_id, "status": "partial_success",
                "answer_status": "failed", "error": {
                    "code": row["error_code"] or "answer_failed",
                    "message": "The brief was saved, but the answer did not finish. Resume using this receipt.",
                },
                "applied_delta": receipt_row["applied_delta"] or {},
                "brief_receipt": {
                    "request_id": request_id, "status": receipt_row["status"],
                    "brief_version_before": receipt_row["brief_version_before"],
                    "brief_version_after": receipt_row["brief_version_after"],
                    "applied_delta": receipt_row["applied_delta"] or {},
                    "answer_status": "failed",
                    "brief_version_used": receipt_row["brief_version_used"],
                    "source_refs": [{
                        "source_utterance_id": receipt_row["source_utterance_id"],
                        "request_id": request_id,
                        "fields": receipt_row["source_fields"] or [],
                    }],
                },
                "evidence": [], "evidence_bindings": [],
            }
            if current_brief is not None:
                response["guest_brief"] = {
                    "brief_version": current_brief["brief_version"],
                    **(current_brief["data"] or {}),
                    "pending_fields": current_brief["pending_fields"] or [],
                }
            connection.execute(update(requests).where(and_(
                requests.c.session_id == session_id,
                requests.c.hotel_id == hotel_id,
                requests.c.request_id == request_id,
                requests.c.status == "error",
            )).values(status="completed", response=response))
        else:
            response = dict(row["response"])
        bindings = response.get("evidence_bindings", [])
        decision = _validate_evidence_on_connection(connection, hotel_id, bindings, utcnow())
        response["freshness"] = {"status": decision.status, "eligible": decision.eligible,
                                 "checked_at": decision.checked_at.isoformat(), "reason": decision.reason}
        if response.get("brief_dependent"):
            current_brief = connection.execute(select(guest_briefs).where(and_(
                guest_briefs.c.session_id == session_id, guest_briefs.c.hotel_id == hotel_id,
            ))).mappings().first()
            current_brief_version = int(current_brief["brief_version"]) if current_brief else 0
            response["brief_narrative_stale"] = current_brief_version != response.get("brief_version_used")
            response["brief_freshness"] = "stale" if response["brief_narrative_stale"] else "current"
            if current_brief is not None:
                response["guest_brief"] = {
                    "brief_version": current_brief_version,
                    **(current_brief["data"] or {}),
                    "pending_fields": current_brief["pending_fields"] or [],
                }
        return response


def consume_provider_slot(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str, payload_hash: str,
    lease_owner: str, limits: GuestAdmissionLimits | None = None, limit: int | None = None,
    timeout_seconds: float | None = None,
) -> int:
    """Durably consume one provider dispatch before the provider is called."""
    selected_limit = limit or (limits.provider_calls_per_request if limits else 2)
    timestamp = utcnow()
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        updated = connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id,
            requests.c.hotel_id == hotel_id,
            requests.c.request_id == request_id,
            requests.c.payload_hash == payload_hash,
            requests.c.status == "processing",
            requests.c.lease_owner == lease_owner,
            requests.c.lease_expires_at > timestamp,
            requests.c.provider_calls < selected_limit,
            select(sessions.c.session_id).where(and_(
                sessions.c.session_id == session_id,
                sessions.c.hotel_id == hotel_id,
                sessions.c.expires_at > timestamp,
            )).exists(),
        )).values(provider_calls=requests.c.provider_calls + 1).returning(
            requests.c.provider_calls,
        ))
        consumed = updated.scalar_one_or_none()
        if consumed is not None:
            return int(consumed)
        row = connection.execute(select(requests).where(and_(
            requests.c.session_id == session_id,
            requests.c.hotel_id == hotel_id,
            requests.c.request_id == request_id,
            requests.c.payload_hash == payload_hash,
        )).with_for_update()).mappings().first()
        if (row is None or row["status"] != "processing"
                or row["lease_owner"] != lease_owner
                or row["lease_expires_at"] is None or row["lease_expires_at"] <= timestamp):
            raise ProviderCallLimitExceeded("turn_lease_expired")
        if row["provider_calls"] >= selected_limit:
            raise ProviderCallLimitExceeded()
        raise ProviderCallLimitExceeded("provider_call_unavailable")


def complete_request(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str,
    question: str, answer: str, evidence: list[dict[str, Any]],
    response_fields: dict[str, Any] | None = None,
    expected_generation: int | None = None,
    brief_version_used: int | None = None,
    brief_dependent: bool = False,
    brief_receipt_id: str | None = None,
    evidence_bindings: list[EvidenceBinding | dict[str, Any]] | None = None,
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
    if brief_version_used is not None:
        result["brief_version_used"] = brief_version_used
        result["brief_dependent"] = brief_dependent
    bindings = evidence_bindings or []
    serialized_bindings = [{
        "source": {
            "hotel_id": item.source.hotel_id, "source_id": item.source.source_id,
            "hotel_generation": item.source.hotel_generation,
            "source_version": item.source.source_version, "source_hash": item.source.source_hash,
            "status": item.source.status, "guest_approved": item.source.guest_approved,
            "valid_from": item.source.valid_from, "valid_to": item.source.valid_to,
            "last_failure": item.source.last_failure,
            "last_success_at": item.source.last_success_at,
        }, "fact_ids": list(item.fact_ids), "media_ids": list(item.media_ids),
        "media_sha256": item.media_sha256 or {},
    } for item in map(_binding_from_value, bindings)]
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        hotel = connection.execute(select(hotels).where(
            hotels.c.hotel_id == hotel_id,
        ).with_for_update()).mappings().first()
        if hotel is None:
            raise ScopeError("hotel scope is invalid")
        result["config_version"] = hotel["config_version"]
        if expected_generation is not None and hotel["knowledge_generation"] != expected_generation:
            raise StaleSource("hotel knowledge generation changed before commit")
        decision = _validate_evidence_on_connection(connection, hotel_id, serialized_bindings, now)
        if not decision.eligible:
            raise StaleSource(f"source evidence is no longer eligible: {decision.status}")
        result["knowledge_generation"] = hotel["knowledge_generation"]
        result["evidence_bindings"] = serialized_bindings
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
        if brief_dependent:
            if brief_version_used is None:
                raise ValueError("A brief-dependent answer requires brief_version_used.")
            current_brief_version = connection.scalar(select(guest_briefs.c.brief_version).where(and_(
                guest_briefs.c.session_id == session_id, guest_briefs.c.hotel_id == hotel_id,
            ))) or 0
            if brief_version_used != current_brief_version:
                raise VersionConflict("guest brief changed before the answer completed")
        # Locks may have waited across session or source expiry. Validate the actual
        # commit-time UTC day after all scope locks have been acquired.
        now = utcnow()
        if session["expires_at"] <= now:
            raise ScopeError("session scope is invalid")
        decision = _validate_evidence_on_connection(connection, hotel_id, serialized_bindings, now)
        if not decision.eligible:
            raise StaleSource(f"source evidence is no longer eligible: {decision.status}")
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
             "content": question, "created_at": now, "evidence_bindings": []},
            {"message_id": assistant_message_id, "session_id": session_id,
             "hotel_id": hotel_id, "sequence": sequence + 1, "role": "assistant",
             "content": answer, "created_at": now, "evidence_bindings": serialized_bindings},
        ])
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        updated = connection.execute(update(sessions).where(and_(
            sessions.c.session_id == session_id, sessions.c.hotel_id == hotel_id,
            sessions.c.state_version == start,
        )).values(state_version=start + 1))
        if updated.rowcount != 1:
            raise VersionConflict("session state version changed")
        refresh_transaction_deadline(connection, deadline_monotonic, cancellation_event)
        if brief_version_used is not None or brief_receipt_id is not None:
            receipt_query = select(guest_brief_receipts.c.request_id).where(and_(
                guest_brief_receipts.c.request_id == (brief_receipt_id or request_id),
                guest_brief_receipts.c.session_id == session_id,
                guest_brief_receipts.c.hotel_id == hotel_id,
            ))
            receipt_exists = connection.scalar(receipt_query)
            if receipt_exists is not None:
                saved_payload = connection.execute(select(guest_brief_receipts.c.answer_payload).where(and_(
                    guest_brief_receipts.c.request_id == (brief_receipt_id or request_id),
                    guest_brief_receipts.c.session_id == session_id,
                    guest_brief_receipts.c.hotel_id == hotel_id,
                ))).scalar_one_or_none() or {}
                if not isinstance(saved_payload, dict):
                    saved_payload = {}
                receipt_values: dict[str, Any] = {
                    "answer_status": "completed",
                    "answer_payload": {
                        "answer": answer,
                        "turn_intents": list(saved_payload.get("turn_intents", ())),
                        "authorized_targets": list(saved_payload.get("authorized_targets", ())),
                    },
                    "brief_dependent": brief_dependent,
                }
                if brief_version_used is not None:
                    receipt_values["brief_version_used"] = brief_version_used
                receipt_updated = connection.execute(update(guest_brief_receipts).where(and_(
                    guest_brief_receipts.c.request_id == (brief_receipt_id or request_id),
                    guest_brief_receipts.c.session_id == session_id,
                    guest_brief_receipts.c.hotel_id == hotel_id,
                )).values(**receipt_values))
                if receipt_updated.rowcount != 1:
                    raise ScopeError("guest brief receipt scope is invalid")
                receipt_row = connection.execute(select(guest_brief_receipts).where(and_(
                    guest_brief_receipts.c.request_id == (brief_receipt_id or request_id),
                    guest_brief_receipts.c.session_id == session_id,
                    guest_brief_receipts.c.hotel_id == hotel_id,
                ))).mappings().one()
                result["brief_receipt"] = {
                    "request_id": receipt_row["request_id"],
                    "status": receipt_row["status"],
                    "brief_version_before": receipt_row["brief_version_before"],
                    "brief_version_after": receipt_row["brief_version_after"],
                    "applied_delta": receipt_row["applied_delta"],
                    "source_refs": [{
                        "source_utterance_id": receipt_row["source_utterance_id"],
                        "request_id": receipt_row["request_id"],
                        "fields": receipt_row["source_fields"],
                    }],
                    "answer_status": receipt_row["answer_status"],
                    "brief_version_used": receipt_row["brief_version_used"],
                }
                current_brief = connection.execute(select(guest_briefs).where(and_(
                    guest_briefs.c.session_id == session_id,
                    guest_briefs.c.hotel_id == hotel_id,
                ))).mappings().first()
                if current_brief is not None:
                    result["guest_brief"] = {
                        "brief_version": current_brief["brief_version"],
                        **(current_brief["data"] or {}),
                        "pending_fields": current_brief["pending_fields"],
                    }
        updated_request = connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id, requests.c.request_id == request_id,
            requests.c.hotel_id == hotel_id, requests.c.status == "processing",
        )).values(status="completed", response=result))
        if updated_request.rowcount != 1:
            raise ScopeError("request scope is invalid")
        final_now = utcnow()
        if session["expires_at"] <= final_now:
            raise ScopeError("session scope is invalid")
        final_decision = _validate_evidence_on_connection(
            connection, hotel_id, serialized_bindings, final_now,
        )
        if not final_decision.eligible:
            raise StaleSource(f"source evidence is no longer eligible: {final_decision.status}")
        if (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic
                or cancellation_event is not None and cancellation_event.is_set()):
            raise TimeoutError("The guest turn expired before its transaction could commit.")
    return result


def complete_request_with_response_only(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str,
    question: str, response: dict[str, Any], timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Persist a scoped response without inventing transcript messages or advancing session state."""
    digest = hashlib.sha256(question.encode("utf-8")).hexdigest()
    saved_response = dict(response)
    if saved_response.get("request_id") != request_id:
        raise ValueError("Response request ID must match its reservation.")
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        row = connection.execute(select(requests).where(and_(
            requests.c.session_id == session_id,
            requests.c.hotel_id == hotel_id,
            requests.c.request_id == request_id,
        )).with_for_update()).mappings().first()
        if row is None or row["payload_hash"] != digest:
            raise ScopeError("request scope is invalid")
        if row["status"] == "completed":
            existing = row["response"] if isinstance(row["response"], dict) else {}
            if existing.get("request_id") != request_id:
                raise IdempotencyConflict("request response is invalid")
            return dict(existing)
        if row["status"] != "processing":
            raise RequestInProgress("request is not in a completable state")
        updated = connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id,
            requests.c.hotel_id == hotel_id,
            requests.c.request_id == request_id,
            requests.c.payload_hash == digest,
            requests.c.status == "processing",
        )).values(status="completed", response=saved_response))
        if updated.rowcount != 1:
            raise RequestInProgress("request reservation changed before completion")
    return saved_response


def fail_request(
    engine: Engine, *, session_id: str, request_id: str, code: str,
    timeout_seconds: float | None = None, trace: dict[str, Any] | None = None,
) -> None:
    safe_trace = _safe_turn_trace(trace) if trace is not None else None
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        values: dict[str, Any] = {"status": "error", "error_code": code}
        if safe_trace is not None:
            values["response"] = {"trace": safe_trace}
        connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id, requests.c.request_id == request_id,
            requests.c.status == "processing",
        )).values(**values))


def _safe_turn_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Persist only the bounded execution metadata shape; never raw guest/provider text."""
    from re import fullmatch

    string_fields = {
        "request_id", "session_id", "hotel_id", "provider", "deployment", "model",
        "provider_request_id", "config_version", "prompt_version", "answer_schema_version",
        "cost_status", "limits_version",
    }
    numeric_fields = {
        "calls", "input_tokens", "output_tokens", "total_tokens", "schema_version",
        "answer_schema_version", "source_generation", "brief_version", "elapsed_ms",
        "context_chars", "turn_timeout_ms", "provider_timeout_ms", "max_output_tokens",
    }
    outcome = trace.get("outcome")
    failure_stage = trace.get("failure_stage")
    elapsed_ms = trace.get("elapsed_ms")
    safe: dict[str, Any] = {
        "schema_version": 1,
        "outcome": outcome if isinstance(outcome, str) and outcome in {
            "ok", "error", "cancelled", "in_progress",
        } else "error",
        "elapsed_ms": max(0, elapsed_ms) if isinstance(elapsed_ms, int) and not isinstance(elapsed_ms, bool) else None,
        "failure_stage": failure_stage if isinstance(failure_stage, str) and failure_stage in {
            "admission", "retrieval", "capability", "provider", "response",
        } else None,
        "failure_code": trace.get("failure_code") if isinstance(trace.get("failure_code"), str)
        and fullmatch(r"[A-Za-z0-9_.-]{1,64}", trace["failure_code"]) else None,
    }
    for key in string_fields:
        value = trace.get(key)
        if isinstance(value, str) and 0 < len(value) <= 128 and not any(ord(char) < 32 for char in value):
            safe[key] = value
    for key in numeric_fields - {"elapsed_ms"}:
        value = trace.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            safe[key] = max(0, value)
    events: list[dict[str, Any]] = []
    for event in trace.get("events", [])[:20] if isinstance(trace.get("events"), list) else []:
        if not isinstance(event, dict) or event.get("stage") not in {
            "admission", "retrieval", "capability", "provider", "response",
        } or event.get("status") not in {"started", "ok", "error", "cancelled", "denied"}:
            continue
        item: dict[str, Any] = {"stage": event["stage"], "status": event["status"]}
        duration = event.get("duration_ms")
        if isinstance(duration, int) and not isinstance(duration, bool):
            item["duration_ms"] = max(0, duration)
        event_code = event.get("code")
        if isinstance(event_code, str) and fullmatch(r"[A-Za-z0-9_.-]{1,64}", event_code):
            item["code"] = event_code
        for key in string_fields:
            value = event.get(key)
            if isinstance(value, str) and 0 < len(value) <= 128 and not any(ord(char) < 32 for char in value):
                item[key] = value
        for key in numeric_fields - {"elapsed_ms"}:
            value = event.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                item[key] = max(0, value)
        events.append(item)
    safe["events"] = events
    # This allowlist is naturally small, but retain a hard storage ceiling if fields change.
    while len(json.dumps(safe, separators=(",", ":")).encode("utf-8")) > 8192 and safe["events"]:
        safe["events"].pop()
    return safe


def complete_partial_request(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str,
    response: dict[str, Any], brief_receipt_id: str | None = None,
    brief_version_used: int | None = None, timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Persist an applied-brief/failed-answer result as replayable terminal state."""
    if response.get("status") != "partial_success" or response.get("answer_status") != "failed":
        raise ValueError("A partial brief result must have failed answer status.")
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        result = dict(response)
        receipt_id = brief_receipt_id or request_id
        receipt_query = select(guest_brief_receipts).where(and_(
            guest_brief_receipts.c.request_id == receipt_id,
            guest_brief_receipts.c.session_id == session_id,
            guest_brief_receipts.c.hotel_id == hotel_id,
        )).with_for_update()
        receipt = connection.execute(receipt_query).mappings().first()
        if receipt is None:
            raise ScopeError("guest brief receipt scope is invalid")
        saved_receipt_payload = receipt["answer_payload"] if isinstance(receipt["answer_payload"], dict) else {}
        receipt_values: dict[str, Any] = {
            "answer_status": "failed",
            "answer_payload": {
                "response": result,
                "turn_intents": list(saved_receipt_payload.get("turn_intents", ())),
                "authorized_targets": list(saved_receipt_payload.get("authorized_targets", ())),
            },
            "brief_dependent": brief_version_used is not None,
        }
        if brief_version_used is not None:
            receipt_values["brief_version_used"] = brief_version_used
        changed = receipt["brief_version_after"] > receipt["brief_version_before"]
        if changed:
            receipt_values["status"] = "partial_success"
        receipt_updated = connection.execute(update(guest_brief_receipts).where(and_(
            guest_brief_receipts.c.request_id == receipt_id,
            guest_brief_receipts.c.session_id == session_id,
            guest_brief_receipts.c.hotel_id == hotel_id,
        )).values(**receipt_values))
        if receipt_updated.rowcount != 1:
            raise ScopeError("guest brief receipt scope is invalid")
        receipt = connection.execute(receipt_query).mappings().one()
        result["applied_delta"] = receipt["applied_delta"] or {}
        result["brief_receipt"] = {
            "request_id": receipt["request_id"], "status": receipt["status"],
            "brief_version_before": receipt["brief_version_before"],
            "brief_version_after": receipt["brief_version_after"],
            "applied_delta": receipt["applied_delta"] or {},
            "source_refs": [{
                "source_utterance_id": receipt["source_utterance_id"],
                "request_id": receipt["request_id"],
                "fields": receipt["source_fields"] or [],
            }],
            "answer_status": "failed",
            "brief_version_used": receipt["brief_version_used"],
        }
        current_brief = connection.execute(select(guest_briefs).where(and_(
            guest_briefs.c.session_id == session_id,
            guest_briefs.c.hotel_id == hotel_id,
        ))).mappings().first()
        if current_brief is not None:
            result["guest_brief"] = {
                "brief_version": current_brief["brief_version"],
                **(current_brief["data"] or {}),
                "pending_fields": current_brief["pending_fields"] or [],
            }
        connection.execute(update(guest_brief_receipts).where(and_(
            guest_brief_receipts.c.request_id == receipt_id,
            guest_brief_receipts.c.session_id == session_id,
            guest_brief_receipts.c.hotel_id == hotel_id,
        )).values(answer_payload={
            "response": result,
            "turn_intents": list(saved_receipt_payload.get("turn_intents", ())),
            "authorized_targets": list(saved_receipt_payload.get("authorized_targets", ())),
        }))
        updated = connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id,
            requests.c.hotel_id == hotel_id,
            requests.c.request_id == request_id,
            requests.c.status == "processing",
        )).values(status="completed", response=result))
        if updated.rowcount != 1:
            raise ScopeError("request scope is invalid")
    return result


def update_completed_response(engine: Engine, session_id: str, request_id: str, response: dict[str, Any]) -> None:
    with engine.begin() as connection:
        updated = connection.execute(update(requests).where(and_(
            requests.c.session_id == session_id, requests.c.request_id == request_id,
            requests.c.status == "completed",
        )).values(response=response))
        if updated.rowcount != 1:
            raise ScopeError("completed request scope is invalid")


def get_completed_response(
    engine: Engine, *, session_id: str, hotel_id: str, request_id: str,
    now: datetime | None = None, timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    """Load a completed response within its owner scope and recompute evidence freshness."""
    checked_at = (now or utcnow()).astimezone(UTC)
    with engine.begin() as connection:
        set_transaction_timeout(connection, timeout_seconds)
        row = connection.execute(select(requests.c.response).where(and_(
            requests.c.session_id == session_id, requests.c.hotel_id == hotel_id,
            requests.c.request_id == request_id, requests.c.status == "completed",
        ))).scalar_one_or_none()
        if row is None:
            return None
        response = dict(row)
        decision = _validate_evidence_on_connection(
            connection, hotel_id, response.get("evidence_bindings", []), checked_at,
        )
        response["freshness"] = {
            "status": decision.status, "eligible": decision.eligible,
            "checked_at": decision.checked_at.isoformat(), "reason": decision.reason,
        }
        return response


def export_snapshot(engine: Engine, hotel_id: str) -> dict[str, Any]:
    """Test helper that proves durable state can be read by a fresh repository handle."""
    return {"hotel": get_hotel(engine, hotel_id), "facts": facts_for_hotel(engine, hotel_id)}
