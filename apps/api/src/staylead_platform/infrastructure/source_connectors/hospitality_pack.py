"""Trusted local connector for allowlisted Hospitality pack roots."""

from pathlib import Path

from sqlalchemy.engine import Engine
from staylead_platform.domains.hospitality.registration.pack_schema import validate_pack
from staylead_platform.infrastructure.persistence.pack_repository import PostgresPackRepository


def import_hospitality_pack(engine: Engine, pack_root: str | Path, *, allowed_root: str | Path) -> dict[str, str]:
    root = Path(allowed_root).resolve(strict=True)
    candidate = Path(pack_root).resolve(strict=True)
    if root not in candidate.parents or not candidate.is_dir():
        raise ValueError("Pack must be a directory beneath the configured allowlisted root.")
    prepared = validate_pack(candidate)
    return PostgresPackRepository(engine).import_pack(prepared)
