"""Operator preview adapter over the existing M1 source and fact tables."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.engine import Engine

from staylead_platform.infrastructure.persistence.store import (
    hotels,
    knowledge_facts,
    knowledge_sources,
)
from staylead_platform.platform.contracts.knowledge import (
    ActiveKnowledgeSnapshot,
    KnowledgeFact,
    SourceVersionRef,
)


class PostgresLocalGuideRepository:
    """Reads operator-visible current source records; never used for guest retrieval."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def active_snapshot(self, hotel_id: str, *, now: datetime | None = None) -> ActiveKnowledgeSnapshot | None:
        checked = (now or datetime.now(UTC)).astimezone(UTC)
        day = checked.date().isoformat()
        with self._engine.begin() as connection:
            generation = connection.execute(select(hotels.c.knowledge_generation).where(
                hotels.c.hotel_id == hotel_id,
            )).scalar_one_or_none()
            if generation is None:
                return None
            rows = connection.execute(select(knowledge_sources).where(
                knowledge_sources.c.hotel_id == hotel_id,
            ).order_by(knowledge_sources.c.source_id)).mappings().all()
        refs = []
        for row in rows:
            status = row["lifecycle_status"]
            if status == "approved" and row["valid_to"] < day:
                status = "expired"
            elif status == "approved" and (not row["guest_approved"] or row["valid_from"] > day):
                status = "staged"
            refs.append(SourceVersionRef(
                hotel_id=hotel_id, source_id=row["source_id"], hotel_generation=generation,
                source_version=row["version"], source_hash=row["source_hash"], status=status,
                guest_approved=row["guest_approved"], valid_from=row["valid_from"], valid_to=row["valid_to"],
                last_failure=row["last_failure"],
                last_success_at=row["last_success_at"].isoformat() if row["last_success_at"] else None,
            ))
        return ActiveKnowledgeSnapshot(hotel_id, generation, tuple(refs))

    def list_operator_facts(self, hotel_id: str) -> tuple[KnowledgeFact, ...]:
        """Return latest persisted versions for protected operator preview, including staged/expired state."""
        with self._engine.begin() as connection:
            rows = connection.execute(select(
                knowledge_facts, knowledge_sources.c.source_hash,
                knowledge_sources.c.lifecycle_status, knowledge_sources.c.guest_approved,
                knowledge_sources.c.source,
            ).join(knowledge_sources, and_(
                knowledge_sources.c.hotel_id == knowledge_facts.c.hotel_id,
                knowledge_sources.c.source_id == knowledge_facts.c.source_id,
                knowledge_sources.c.version == knowledge_facts.c.source_version,
            )).where(knowledge_facts.c.hotel_id == hotel_id).order_by(
                knowledge_facts.c.fact_id,
            )).mappings().all()
        facts = []
        for row in rows:
            stored = row["fact"]
            source = row["source"]
            facts.append(KnowledgeFact(
                fact_id=row["fact_id"], hotel_id=row["hotel_id"], topic=stored["topic"],
                subject=stored["subject"], field=stored["field"], value=stored.get("value"),
                conditions=stored.get("conditions", {}), status=row["status"],
                valid_from=row["valid_from"], valid_to=row["valid_to"],
                provenance={
                    "source_id": row["source_id"], "source_version": row["source_version"],
                    "source_hash": row["source_hash"], "section": row["section"],
                    "fact_version": row["fact_version"], "lifecycle_status": row["lifecycle_status"],
                    "guest_approved": row["guest_approved"],
                    "source_checked_at": source.get("checked_at"),
                    "imported_at": row["imported_at"].isoformat(),
                },
            ))
        return tuple(facts)
