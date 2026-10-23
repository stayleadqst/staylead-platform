"""Persistence adapter for complete immutable knowledge-pack publication."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.engine import Engine
from staylead_platform.infrastructure.persistence.store import (
    import_complete_pack,
    knowledge_facts,
    knowledge_media,
    knowledge_sources,
    set_transaction_timeout,
)
from staylead_platform.platform.contracts.knowledge import EligibleAsset, MediaDescriptor


class PostgresPackRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def import_pack(self, pack: dict) -> dict[str, str]:
        return import_complete_pack(self._engine, pack)


class PostgresMediaRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _descriptor(values: object, *, fact_ids: tuple[str, ...] | None = None) -> MediaDescriptor:
        return MediaDescriptor(
            media_id=values["media_id"], hotel_id=values["hotel_id"],
            fact_ids=fact_ids if fact_ids is not None else tuple(values["fact_ids"]), kind=values["kind"],
            mime_type=values["mime_type"], byte_size=values["byte_size"],
            sha256=values["sha256"], caption=values["caption"], alt_text=values["alt_text"],
            source_id=values["source_id"], source_version=values["source_version"],
            start_seconds=values["start_seconds"], end_seconds=values["end_seconds"],
            duration_seconds=values["duration_seconds"],
            captions_media_id=values["captions_media_id"],
        )

    def list_eligible_media(
        self, hotel_id: str, fact_ids: set[str], now: datetime, *,
        timeout_seconds: float | None = None,
    ) -> list[MediaDescriptor]:
        if not fact_ids:
            return []
        today = now.date().isoformat()
        with self._engine.begin() as connection:
            set_transaction_timeout(connection, timeout_seconds)
            rows = connection.execute(select(knowledge_media).join(
                knowledge_sources, and_(
                    knowledge_sources.c.source_id == knowledge_media.c.source_id,
                    knowledge_sources.c.hotel_id == knowledge_media.c.hotel_id,
                    knowledge_sources.c.version == knowledge_media.c.source_version,
                ),
            ).where(and_(
                knowledge_media.c.hotel_id == hotel_id,
                knowledge_media.c.guest_approved_whole_file.is_(True),
                knowledge_media.c.kind.in_(["image", "video"]),
                knowledge_media.c.valid_from <= today,
                knowledge_media.c.valid_to >= today,
                knowledge_sources.c.guest_approved.is_(True),
                knowledge_sources.c.valid_from <= today,
                knowledge_sources.c.valid_to >= today,
            ))).mappings().all()
        result = []
        for row in rows:
            cited = set(row["fact_ids"]).intersection(fact_ids)
            if not cited:
                continue
            with self._engine.begin() as connection:
                set_transaction_timeout(connection, timeout_seconds)
                eligible = set(connection.scalars(select(knowledge_facts.c.fact_id).where(and_(
                    knowledge_facts.c.hotel_id == hotel_id,
                    knowledge_facts.c.fact_id.in_(cited),
                    knowledge_facts.c.source_id == row["source_id"],
                    knowledge_facts.c.source_version == row["source_version"],
                    knowledge_facts.c.status.in_(["confirmed", "unknown", "needs_confirmation"]),
                    knowledge_facts.c.valid_from <= today,
                    knowledge_facts.c.valid_to >= today,
                ))).all())
            if eligible:
                result.append(self._descriptor(row, fact_ids=tuple(sorted(eligible))))
        return result

    def read_eligible_asset(
        self, hotel_id: str, media_id: str, now: datetime, *,
        timeout_seconds: float | None = None,
    ) -> EligibleAsset | None:
        today = now.date().isoformat()
        with self._engine.begin() as connection:
            set_transaction_timeout(connection, timeout_seconds)
            row = connection.execute(select(knowledge_media).join(
                knowledge_sources, and_(
                    knowledge_sources.c.source_id == knowledge_media.c.source_id,
                    knowledge_sources.c.hotel_id == knowledge_media.c.hotel_id,
                    knowledge_sources.c.version == knowledge_media.c.source_version,
                ),
            ).where(and_(
                knowledge_media.c.hotel_id == hotel_id,
                knowledge_media.c.media_id == media_id,
                knowledge_media.c.guest_approved_whole_file.is_(True),
                knowledge_media.c.valid_from <= today,
                knowledge_media.c.valid_to >= today,
                knowledge_sources.c.guest_approved.is_(True),
                knowledge_sources.c.valid_from <= today,
                knowledge_sources.c.valid_to >= today,
            ))).mappings().first()
        if row is None:
            return None
        with self._engine.begin() as connection:
            set_transaction_timeout(connection, timeout_seconds)
            eligible_fact_ids = tuple(connection.scalars(select(knowledge_facts.c.fact_id).where(and_(
                knowledge_facts.c.hotel_id == hotel_id,
                knowledge_facts.c.fact_id.in_(row["fact_ids"]),
                knowledge_facts.c.source_id == row["source_id"],
                knowledge_facts.c.source_version == row["source_version"],
                knowledge_facts.c.status.in_(["confirmed", "unknown", "needs_confirmation"]),
                knowledge_facts.c.valid_from <= today,
                knowledge_facts.c.valid_to >= today,
            ))).all())
        if not eligible_fact_ids:
            return None
        descriptor = self._descriptor(row, fact_ids=tuple(sorted(eligible_fact_ids)))
        return EligibleAsset(content=bytes(row["content"]), mime_type=row["mime_type"],
                             descriptor=descriptor)
