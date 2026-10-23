"""SQL adapter for the domain-neutral guest knowledge port."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from staylead_platform.infrastructure.persistence.store import (
    hotels,
    knowledge_facts,
    knowledge_sources,
    set_transaction_timeout,
)
from staylead_platform.platform.contracts.knowledge import KnowledgeFact


class PostgresKnowledgeFactRepository:
    def __init__(self, engine: Engine, *, clock: Callable[[], datetime] | None = None) -> None:
        self._engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _materialize(row: object) -> KnowledgeFact:
        values = row._mapping
        fact = values["fact"]
        return KnowledgeFact(
            fact_id=values["fact_id"], hotel_id=values["hotel_id"],
            topic=fact["topic"], subject=fact["subject"], field=fact["field"],
            value=fact.get("value"), conditions=fact.get("conditions", {}),
            status=values["status"], valid_from=values["valid_from"], valid_to=values["valid_to"],
            provenance={
                "source_id": values["source_id"], "source_version": values["source_version"],
                "source_hash": values.get("source_hash") or "",
                "source_generation": values.get("source_generation") or 0,
                "section": values["section"], "fact_version": values["fact_version"],
                "imported_at": values["imported_at"].isoformat(),
            },
        )

    def list_guest_facts(
        self, hotel_id: str, *, limit: int = 400, timeout_seconds: float | None = None,
    ) -> list[KnowledgeFact]:
        today = self._clock().astimezone(UTC).date().isoformat()
        try:
            with self._engine.begin() as connection:
                set_transaction_timeout(connection, timeout_seconds)
                today = self._clock().astimezone(UTC).date().isoformat()
                rows = connection.execute(select(
                    knowledge_facts, knowledge_sources.c.source_hash,
                    hotels.c.knowledge_generation.label("source_generation"),
                ).join(knowledge_sources, and_(
                    knowledge_sources.c.hotel_id == knowledge_facts.c.hotel_id,
                    knowledge_sources.c.source_id == knowledge_facts.c.source_id,
                    knowledge_sources.c.version == knowledge_facts.c.source_version,
                )).join(hotels, hotels.c.hotel_id == knowledge_facts.c.hotel_id).where(and_(
                    knowledge_facts.c.hotel_id == hotel_id,
                    knowledge_facts.c.status.in_(["confirmed", "unknown", "needs_confirmation"]),
                    knowledge_facts.c.valid_from <= today,
                    knowledge_facts.c.valid_to >= today,
                    knowledge_sources.c.guest_approved.is_(True),
                    knowledge_sources.c.lifecycle_status == "approved",
                    knowledge_sources.c.valid_from <= today,
                    knowledge_sources.c.valid_to >= today,
                )).limit(min(max(limit, 1), 400))).all()
        except OperationalError as exc:
            self._raise_if_timeout(exc)
            raise
        return [self._materialize(row) for row in rows]

    def get_guest_facts(
        self, hotel_id: str, fact_ids: set[str], *, timeout_seconds: float | None = None,
    ) -> list[KnowledgeFact]:
        if not fact_ids:
            return []
        today = self._clock().astimezone(UTC).date().isoformat()
        try:
            with self._engine.begin() as connection:
                set_transaction_timeout(connection, timeout_seconds)
                rows = connection.execute(select(
                    knowledge_facts, knowledge_sources.c.source_hash,
                    hotels.c.knowledge_generation.label("source_generation"),
                ).join(knowledge_sources, and_(
                    knowledge_sources.c.hotel_id == knowledge_facts.c.hotel_id,
                    knowledge_sources.c.source_id == knowledge_facts.c.source_id,
                    knowledge_sources.c.version == knowledge_facts.c.source_version,
                )).join(hotels, hotels.c.hotel_id == knowledge_facts.c.hotel_id).where(and_(
                knowledge_facts.c.hotel_id == hotel_id,
                knowledge_facts.c.fact_id.in_(fact_ids),
                knowledge_facts.c.status.in_(["confirmed", "unknown", "needs_confirmation"]),
                knowledge_facts.c.valid_from <= today,
                knowledge_facts.c.valid_to >= today,
                knowledge_sources.c.guest_approved.is_(True),
                knowledge_sources.c.lifecycle_status == "approved",
                knowledge_sources.c.valid_from <= today,
                knowledge_sources.c.valid_to >= today,
                ))).all()
        except OperationalError as exc:
            self._raise_if_timeout(exc)
            raise
        return [self._materialize(row) for row in rows]

    @staticmethod
    def _raise_if_timeout(exc: OperationalError) -> None:
        if getattr(getattr(exc, "orig", None), "sqlstate", None) in {"55P03", "57014"}:
            raise TimeoutError("The knowledge query exceeded its database time limit.") from exc
