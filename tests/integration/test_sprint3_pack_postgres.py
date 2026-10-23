"""Focused persistence acceptance against an explicitly isolated PostgreSQL database."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations,
    get_hotel_by_slug,
    knowledge_facts,
    knowledge_media,
    knowledge_packs,
    knowledge_sources,
    schema_version,
)
from staylead_platform.infrastructure.source_connectors.hospitality_pack import (
    import_hospitality_pack,
)

FIXTURE = Path(__file__).parents[1].parent / "fixtures/hospitality/media-pack-v1"


@pytest.mark.skipif(not os.getenv("STAYLEAD_TEST_DATABASE_URL"), reason="isolated Sprint 3 PostgreSQL DSN not configured")
def test_complete_pack_publication_replay_immutability_and_scoped_media_reads(tmp_path: Path):
    import shutil
    from datetime import UTC, datetime

    from staylead_platform.infrastructure.persistence.pack_repository import (
        PostgresMediaRepository,
    )

    engine = create_database_engine(os.environ["STAYLEAD_TEST_DATABASE_URL"])
    if schema_version(engine) != 3:
        apply_migrations(engine)
    root = tmp_path / "allowed" / "pack"
    root.parent.mkdir()
    shutil.copytree(FIXTURE, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    tag = uuid4().hex[:12]
    manifest["hotel"]["hotel_id"] = f"HTL-{tag}"
    manifest["hotel"]["slug"] = f"sprint3-{tag}"
    source_map = {}
    for source in manifest["sources"]:
        old, new = source["source_id"], f"source-{tag}"
        source["source_id"] = new
        source_map[old] = new
    fact_map = {}
    for fact in manifest["facts"]:
        old, new = fact["fact_id"], f"{tag}-{fact['fact_id']}"
        fact["fact_id"] = new
        fact_map[old] = new
        fact["source_refs"] = [{"source_id": source_map[r["source_id"]], "version": r["version"]} for r in fact["source_refs"]]
    for media in manifest["media"]:
        media["media_id"] = f"{tag}-{media['media_id']}"
        media["source_id"] = source_map[media["source_id"]]
        media["fact_ids"] = [fact_map[fid] for fid in media["fact_ids"]]
        if media.get("captions_media_id"):
            media["captions_media_id"] = f"{tag}-{media['captions_media_id']}"
    manifest["sources"][0]["valid_to"] = "2030-12-31"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False))

    allowed = root.parent
    # Force a database-level globally unique source-ID failure after hotel/pack inserts
    # have begun. The transaction must roll all publication rows back.
    collision_source = source_map[next(iter(source_map))]
    with engine.begin() as connection:
        connection.execute(insert(knowledge_sources).values(
            source_id=collision_source, hotel_id=f"HTL-OTHER-{tag}", version="1",
            scope="hotel-specific", guest_approved=True, valid_from="2025-01-01",
            valid_to="2035-12-31", source={"source_id": collision_source},
        ))
    try:
        with pytest.raises(IntegrityError):
            import_hospitality_pack(engine, root, allowed_root=allowed)
        assert get_hotel_by_slug(engine, manifest["hotel"]["slug"]) is None
        with engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(knowledge_packs).where(
                knowledge_packs.c.hotel_id == manifest["hotel"]["hotel_id"],
            )) == 0
            assert connection.scalar(select(func.count()).select_from(knowledge_facts).where(
                knowledge_facts.c.hotel_id == manifest["hotel"]["hotel_id"],
            )) == 0
            assert connection.scalar(select(func.count()).select_from(knowledge_media).where(
                knowledge_media.c.hotel_id == manifest["hotel"]["hotel_id"],
            )) == 0
    finally:
        with engine.begin() as connection:
            connection.execute(delete(knowledge_sources).where(knowledge_sources.c.source_id == collision_source))

    first = import_hospitality_pack(engine, root, allowed_root=allowed)
    assert first["status"] == "imported"
    assert get_hotel_by_slug(engine, manifest["hotel"]["slug"])["hotel_id"] == manifest["hotel"]["hotel_id"]
    media_repo = PostgresMediaRepository(engine)
    cited = {fact_map["fact-room-balcony"]}
    descriptors = media_repo.list_eligible_media(manifest["hotel"]["hotel_id"], cited, datetime.now(UTC))
    assert len(descriptors) == 1 and descriptors[0].media_id == f"{tag}-media-room"
    asset = media_repo.read_eligible_asset(manifest["hotel"]["hotel_id"], descriptors[0].media_id, datetime.now(UTC))
    assert asset is not None and len(asset.content) == asset.descriptor.byte_size
    assert media_repo.read_eligible_asset("HTL-WRONG", descriptors[0].media_id, datetime.now(UTC)) is None

    assert import_hospitality_pack(engine, root, allowed_root=allowed)["status"] == "noop"
    with engine.connect() as connection:
        counts = [connection.scalar(select(func.count()).select_from(table).where(table.c.hotel_id == manifest["hotel"]["hotel_id"]))
                  for table in (knowledge_packs, knowledge_sources, knowledge_facts, knowledge_media)]
    assert counts == [1, 1, len(manifest["facts"]), len(manifest["media"])]

    manifest["facts"][0]["valid_to"] = "2040-12-31"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False))
    with pytest.raises(ValueError, match="immutable"):
        import_hospitality_pack(engine, root, allowed_root=allowed)

    manifest["hotel"]["config_version"] = "changed"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False))
    with pytest.raises(ValueError, match="immutable"):
        import_hospitality_pack(engine, root, allowed_root=allowed)
    assert get_hotel_by_slug(engine, manifest["hotel"]["slug"])["config_version"] == "1"
    engine.dispose()
