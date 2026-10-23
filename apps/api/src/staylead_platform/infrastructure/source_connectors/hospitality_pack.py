"""Trusted local connector for allowlisted Hospitality pack roots."""

from pathlib import Path

from sqlalchemy.engine import Engine

from staylead_platform.domains.hospitality.registration.pack_schema import validate_pack
from staylead_platform.infrastructure.persistence.pack_repository import PostgresPackRepository
from staylead_platform.infrastructure.persistence.store import (
    record_source_failure,
    replace_source_snapshot,
    transition_source,
)


def import_hospitality_pack(engine: Engine, pack_root: str | Path, *, allowed_root: str | Path) -> dict[str, str]:
    root = Path(allowed_root).resolve(strict=True)
    candidate = Path(pack_root).resolve(strict=True)
    if root not in candidate.parents or not candidate.is_dir():
        raise ValueError("Pack must be a directory beneath the configured allowlisted root.")
    prepared = validate_pack(candidate)
    return PostgresPackRepository(engine).import_pack(prepared)


def refresh_hospitality_source(
    engine: Engine, pack_root: str | Path, *, allowed_root: str | Path,
    hotel_id: str, source_id: str, expected_generation: int, expected_version: str,
    expected_source_hash: str, operation_id: str,
) -> dict:
    """Validate an allowlisted one-source snapshot and publish it with CAS."""
    root = Path(allowed_root).resolve(strict=True)
    candidate = Path(pack_root).resolve(strict=True)
    if root not in candidate.parents or not candidate.is_dir():
        raise ValueError("Source snapshot must be beneath the configured allowlisted root.")
    try:
        prepared = validate_pack(candidate)
        return replace_source_snapshot(
            engine, hotel_id=hotel_id, source_id=source_id,
            expected_generation=expected_generation, expected_version=expected_version,
            expected_source_hash=expected_source_hash, operation_id=operation_id, pack=prepared,
        )
    except Exception as exc:
        record_source_failure(engine, hotel_id, source_id, type(exc).__name__)
        raise


def transition_hospitality_source(
    engine: Engine, *, hotel_id: str, source_id: str, expected_generation: int,
    expected_version: str, expected_source_hash: str, operation_id: str, action: str,
) -> dict:
    return transition_source(
        engine, hotel_id=hotel_id, source_id=source_id,
        expected_generation=expected_generation, expected_version=expected_version,
        expected_source_hash=expected_source_hash, operation_id=operation_id, action=action,
    )
