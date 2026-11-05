"""Local connector for the synthetic local-guide pack using existing M1 lifecycle ports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.engine import Engine

from staylead_platform.domains.hospitality.registration.local_guide_pack import (
    HOTEL_ID,
    LocalGuidePack,
    parse_local_guide_pack,
)
from staylead_platform.infrastructure.persistence.store import (
    get_active_snapshot,
    import_complete_pack,
    replace_source_snapshot,
    transition_source,
)


def _allowed_pack(pack_root: str | Path, allowed_root: str | Path) -> tuple[Path, LocalGuidePack]:
    root = Path(allowed_root).resolve(strict=True)
    candidate = Path(pack_root).resolve(strict=True)
    if root not in candidate.parents or not candidate.is_dir():
        raise ValueError("Local-guide pack must be beneath the configured allowlisted root.")
    return candidate, parse_local_guide_pack(candidate)


def _single_source(pack: LocalGuidePack, source_id: str, *, activate: bool) -> dict[str, Any]:
    full = pack.pack
    sources = [source for source in full["sources"] if source["source_id"] == source_id]
    if len(sources) != 1:
        raise ValueError("Selected source does not exist in the local-guide pack.")
    source = dict(sources[0])
    source["guest_approved"] = activate
    facts = [fact for fact in full["facts"] if fact["source_refs"][0]["source_id"] == source_id]
    manifest = dict(full["manifest"])
    manifest["source_id"] = source_id
    manifest["source_version"] = source["version"]
    manifest["guest_approved"] = activate
    material = {"hotel": full["hotel"], "source": source, "facts": facts}
    return {
        "pack_id": full["pack_id"], "pack_version": source["version"], "schema_version": 1,
        "canonical_hash": hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")).hexdigest(),
        "manifest": manifest, "hotel": full["hotel"], "sources": [source], "facts": facts, "media": [],
    }


def import_local_guide_pack(engine: Engine, pack_root: str | Path, *, allowed_root: str | Path) -> dict[str, Any]:
    """Import all pack sources into M1 staged; guest retrieval excludes them until activation."""
    _, prepared = _allowed_pack(pack_root, allowed_root)
    result = import_complete_pack(engine, prepared.pack)
    snapshot = get_active_snapshot(engine, prepared.pack["hotel"]["hotel_id"])
    sources = [{
        "source_id": ref.source_id, "version": ref.source_version, "source_hash": ref.source_hash,
        "status": "staged" if not ref.guest_approved else ref.status,
        "guest_approved": ref.guest_approved, "valid_from": ref.valid_from, "valid_to": ref.valid_to,
    } for ref in snapshot.sources] if snapshot else []
    return {**result, "source_ids": [source["source_id"] for source in sources],
            "generation": snapshot.generation if snapshot else None, "sources": sources,
            "status": result.get("status", "imported")}


def activate_local_guide_source(
    engine: Engine, pack_root: str | Path, *, allowed_root: str | Path, hotel_id: str,
    source_id: str, expected_generation: int, expected_version: str,
    expected_source_hash: str, operation_id: str,
) -> dict[str, Any]:
    _, parsed = _allowed_pack(pack_root, allowed_root)
    if parsed.pack["hotel"]["hotel_id"] != hotel_id:
        raise ValueError("Selected local-guide property does not match the pack.")
    approved = _single_source(parsed, source_id, activate=True)
    return replace_source_snapshot(
        engine, hotel_id=hotel_id, source_id=source_id, expected_generation=expected_generation,
        expected_version=expected_version, expected_source_hash=expected_source_hash,
        operation_id=operation_id, pack=approved,
    )


def refresh_local_guide_source(
    engine: Engine, *, allowed_root: str | Path, hotel_id: str,
    source_id: str, expected_generation: int, expected_version: str,
    expected_source_hash: str, operation_id: str,
    revision: Literal["primary-price-110000", "secondary-hours-confirmed"],
) -> dict[str, Any]:
    revision_roots = {
        "primary-price-110000": ("S8-GUIDE-PRIMARY", "sprint8-local-guide-v2-primary"),
        "secondary-hours-confirmed": ("S8-GUIDE-SECONDARY", "sprint8-local-guide-v2-secondary"),
    }
    selected_source, directory = revision_roots[revision]
    if source_id != selected_source or hotel_id != HOTEL_ID:
        raise ValueError("Refresh revision does not match the selected source and pilot property.")
    _, parsed = _allowed_pack(Path(allowed_root) / directory, allowed_root)
    if parsed.pack["hotel"]["hotel_id"] != hotel_id:
        raise ValueError("Selected local-guide property does not match the pack.")
    updated = _single_source(parsed, source_id, activate=True)
    return replace_source_snapshot(
        engine, hotel_id=hotel_id, source_id=source_id, expected_generation=expected_generation,
        expected_version=expected_version, expected_source_hash=expected_source_hash,
        operation_id=operation_id, pack=updated,
    )


def transition_local_guide_source(
    engine: Engine, *, hotel_id: str, source_id: str, expected_generation: int,
    expected_version: str, expected_source_hash: str, operation_id: str,
    action: Literal["revoke", "delete"],
) -> dict[str, Any]:
    return transition_source(
        engine, hotel_id=hotel_id, source_id=source_id, expected_generation=expected_generation,
        expected_version=expected_version, expected_source_hash=expected_source_hash,
        operation_id=operation_id, action=action,
    )
