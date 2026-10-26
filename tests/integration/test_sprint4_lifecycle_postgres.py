"""Sprint 4 source lifecycle contracts against an isolated PostgreSQL database."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select
from staylead_platform.domains.hospitality.registration.pack_schema import validate_pack
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.knowledge_repository import (
    PostgresKnowledgeFactRepository,
)
from staylead_platform.infrastructure.persistence.pack_repository import (
    PostgresMediaRepository,
)
from staylead_platform.infrastructure.persistence.store import (
    IdempotencyConflict,
    ScopeError,
    StaleSource,
    VersionConflict,
    apply_migrations,
    complete_request,
    create_session,
    get_active_snapshot,
    get_hotel,
    hotels,
    knowledge_facts,
    knowledge_media,
    knowledge_packs,
    knowledge_sources,
    lifecycle_operations,
    messages,
    replace_source_snapshot,
    requests,
    reserve_request,
    schema_version,
    sessions,
    transition_source,
    validate_evidence_current,
)
from staylead_platform.infrastructure.source_connectors.hospitality_pack import (
    import_hospitality_pack,
    refresh_hospitality_source,
)
from staylead_platform.platform.contracts.knowledge import EvidenceBinding

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/hospitality/media-pack-v1"


def test_complete_request_rechecks_expiry_after_hotel_lock(monkeypatch, tmp_path: Path):
    """A wait across the UTC date boundary must roll back the answer commit."""
    dsn = os.getenv("STAYLEAD_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated Sprint 4 PostgreSQL DSN not configured")
    engine = create_database_engine(dsn)
    apply_migrations(engine)
    tag = uuid4().hex[:10].upper()
    root, manifest = _prepare(tmp_path / "expiry", tag)
    hotel_id = manifest["hotel"]["hotel_id"]
    source_a = manifest["sources"][0]
    source_a["valid_to"] = "2026-10-23"
    for fact in manifest["facts"]:
        if fact["source_refs"][0]["source_id"] == source_a["source_id"]:
            fact["valid_to"] = "2026-10-23"
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    try:
        import_hospitality_pack(engine, root, allowed_root=root.parent)
        before = datetime(2026, 10, 23, 23, 59, 59, tzinfo=UTC)
        after = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
        snapshot = get_active_snapshot(engine, hotel_id, now=before)
        source = next(ref for ref in snapshot.sources if ref.source_id == source_a["source_id"])
        fact = next(item for item in PostgresKnowledgeFactRepository(
            engine, clock=lambda: before,
        ).list_guest_facts(hotel_id) if item.provenance["source_id"] == source.source_id)
        session_id, request_id = str(uuid4()), f"expiry-{tag}"
        create_session(engine, session_id, hotel_id, datetime(2035, 1, 1, tzinfo=UTC))
        assert reserve_request(engine, session_id=session_id, hotel_id=hotel_id,
                               request_id=request_id, question="When is breakfast?") is None
        first_clock = threading.Event()
        clock_calls = 0

        def controlled_clock():
            nonlocal clock_calls
            clock_calls += 1
            if clock_calls == 1:
                first_clock.set()
                return before
            return after

        import staylead_platform.infrastructure.persistence.store as store_module
        monkeypatch.setattr(store_module, "utcnow", controlled_clock)
        outcome: list[Exception | dict] = []

        def complete():
            try:
                outcome.append(complete_request(
                    engine, session_id=session_id, hotel_id=hotel_id, request_id=request_id,
                    question="When is breakfast?", answer="Breakfast hours are available.",
                    evidence=[{"fact_id": fact.fact_id}], expected_generation=snapshot.generation,
                    evidence_bindings=[EvidenceBinding(source, fact_ids=(fact.fact_id,))],
                ))
            except StaleSource as exc:
                outcome.append(exc)

        with engine.begin() as connection:
            connection.execute(select(hotels).where(hotels.c.hotel_id == hotel_id).with_for_update())
            worker = threading.Thread(target=complete)
            worker.start()
            assert first_clock.wait(2)
            time.sleep(0.15)  # allow complete_request to queue on the held hotel row
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert len(outcome) == 1 and isinstance(outcome[0], StaleSource)
        with engine.connect() as connection:
            assert connection.scalar(select(sessions.c.state_version).where(
                sessions.c.session_id == session_id,
            )) == 0
            assert connection.scalar(select(requests.c.status).where(
                requests.c.request_id == request_id,
            )) == "processing"
            assert connection.scalar(select(messages.c.message_id).where(
                messages.c.session_id == session_id,
            )) is None
    finally:
        with engine.begin() as connection:
            connection.execute(delete(messages).where(messages.c.hotel_id == hotel_id))
            connection.execute(delete(requests).where(requests.c.hotel_id == hotel_id))
            connection.execute(delete(sessions).where(sessions.c.hotel_id == hotel_id))
            connection.execute(delete(lifecycle_operations).where(lifecycle_operations.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_media).where(knowledge_media.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_facts).where(knowledge_facts.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_sources).where(knowledge_sources.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_packs).where(knowledge_packs.c.hotel_id == hotel_id))
            connection.execute(delete(hotels).where(hotels.c.hotel_id == hotel_id))
        engine.dispose()


def _prepare(root: Path, tag: str) -> tuple[Path, dict]:
    shutil.copytree(FIXTURE, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["hotel"]["hotel_id"] = f"HTL-{tag}"
    manifest["hotel"]["slug"] = f"s4-{tag.lower()}"
    source_ids = {}
    for index, source in enumerate(manifest["sources"]):
        old, new = source["source_id"], f"SRC-{tag}-{index}"
        source["source_id"] = new
        source_ids[old] = new
    facts_by_old = {}
    for fact in manifest["facts"]:
        old, new = fact["fact_id"], f"F-{tag}-{fact['fact_id']}"
        fact["fact_id"] = new
        facts_by_old[old] = new
        fact["source_refs"] = [{"source_id": source_ids[r["source_id"]], "version": r["version"]}
                               for r in fact["source_refs"]]
    media_ids = {}
    for media in manifest["media"]:
        old, new = media["media_id"], f"M-{tag}-{media['media_id']}"
        media_ids[old] = new
        media["media_id"] = new
        media["source_id"] = source_ids[media["source_id"]]
        media["fact_ids"] = [facts_by_old[fid] for fid in media["fact_ids"]]
        if media.get("captions_media_id"):
            media["captions_media_id"] = f"M-{tag}-{media['captions_media_id']}"
    # A second independent source proves source A operations preserve source B.
    original_fact = dict(manifest["facts"][0])
    source_b = dict(manifest["sources"][0])
    source_b.update(source_id=f"SRC-{tag}-B", version="b1", title="Independent parking source")
    fact_b = dict(original_fact)
    fact_b.update(
        fact_id=f"F-{tag}-PARKING", topic="parking", subject="hotel", field="parking",
        value="Free parking", source_refs=[{"source_id": source_b["source_id"], "version": "b1"}],
    )
    manifest["sources"].append(source_b)
    manifest["facts"].append(fact_b)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False))
    return root, manifest


def _selected_a(root: Path, manifest: dict) -> Path:
    selected = root.parent / "replacement"
    shutil.copytree(root, selected)
    selected_manifest = dict(manifest)
    source_a = manifest["sources"][0]
    selected_manifest["sources"] = [dict(source_a)]
    selected_manifest["facts"] = [fact for fact in manifest["facts"]
                                  if fact["source_refs"][0]["source_id"] == source_a["source_id"]]
    selected_manifest["media"] = [media for media in manifest["media"]
                                  if media["source_id"] == source_a["source_id"]]
    allowed_paths = {"manifest.json", *(item["asset_path"] for item in selected_manifest["media"])}
    for path in list(selected.rglob("*")):
        if path.is_file() and path.relative_to(selected).as_posix() not in allowed_paths:
            path.unlink()
    for directory in sorted((path for path in selected.rglob("*") if path.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    selected_manifest["pack_id"] = manifest["pack_id"]
    selected_manifest["pack_version"] = "replacement"
    (selected / "manifest.json").write_text(json.dumps(selected_manifest, ensure_ascii=False))
    return selected


@pytest.mark.skipif(not os.getenv("STAYLEAD_TEST_DATABASE_URL"), reason="isolated Sprint 4 PostgreSQL DSN not configured")
def test_scoped_refresh_replay_revoke_expiry_and_cas(tmp_path: Path):
    engine = create_database_engine(os.environ["STAYLEAD_TEST_DATABASE_URL"])
    apply_migrations(engine)
    assert schema_version(engine) == 6
    tag = uuid4().hex[:10].upper()
    root, manifest = _prepare(tmp_path / "original", tag)
    allowed = root.parent
    hotel_id = manifest["hotel"]["hotel_id"]
    source_a, source_b = manifest["sources"]
    try:
        import_hospitality_pack(engine, root, allowed_root=allowed)
        before = get_active_snapshot(engine, hotel_id, now=datetime(2026, 10, 23, tzinfo=UTC))
        ref_a = next(ref for ref in before.sources if ref.source_id == source_a["source_id"])
        ref_b = next(ref for ref in before.sources if ref.source_id == source_b["source_id"])
        config_before = get_hotel(engine, hotel_id)["public_config"]
        with pytest.raises(ScopeError):
            refresh_hospitality_source(
                engine, root, allowed_root=allowed, hotel_id=hotel_id,
                source_id=source_a["source_id"], expected_generation=before.generation,
                expected_version=ref_a.source_version, expected_source_hash=ref_a.source_hash,
                operation_id=f"invalid-{tag}",
            )
        failed = get_active_snapshot(engine, hotel_id, now=datetime(2026, 10, 23, tzinfo=UTC))
        failed_a = next(ref for ref in failed.sources if ref.source_id == source_a["source_id"])
        assert failed_a.status == "refresh_failed" and failed_a.source_hash == ref_a.source_hash
        assert failed.generation == before.generation
        assert validate_evidence_current(engine, hotel_id, [EvidenceBinding(ref_a)],
                                         datetime(2026, 10, 23, tzinfo=UTC)).eligible is True

        replacement = _selected_a(root, manifest)
        changed = json.loads((replacement / "manifest.json").read_text())
        changed["sources"][0]["version"] = "a2"
        changed["sources"][0]["title"] = "Updated breakfast guide"
        for fact in changed["facts"]:
            fact["source_refs"][0]["version"] = "a2"
        for media in changed["media"]:
            media["source_version"] = "a2"
        changed["facts"][0]["value"] = "Breakfast 08:00–11:00"
        media_fact_ids = {fid for media in changed["media"] for fid in media["fact_ids"]}
        omitted = next(fact for fact in changed["facts"] if fact["fact_id"] not in media_fact_ids)
        changed["facts"].remove(omitted)
        (replacement / "manifest.json").write_text(json.dumps(changed, ensure_ascii=False))
        validated_replacement = validate_pack(replacement)
        # Facts in every active source count toward the aggregate publication bound.
        with engine.begin() as connection:
            template = connection.execute(select(knowledge_facts).where(
                knowledge_facts.c.hotel_id == hotel_id,
                knowledge_facts.c.source_id == source_b["source_id"],
            )).mappings().first()
            dummy_rows = []
            for index in range(396):
                row = dict(template)
                row["fact_id"] = f"X-{tag}-{index}"
                fact_value = dict(row["fact"])
                fact_value["fact_id"] = row["fact_id"]
                row["fact"] = fact_value
                dummy_rows.append(row)
            connection.execute(insert(knowledge_facts), dummy_rows)
        with pytest.raises(ValueError, match="aggregate active hotel facts"):
            replace_source_snapshot(
                engine, hotel_id=hotel_id, source_id=source_a["source_id"],
                expected_generation=before.generation, expected_version=ref_a.source_version,
                expected_source_hash=ref_a.source_hash, operation_id=f"over-limit-{tag}",
                pack=validated_replacement, now=datetime(2026, 10, 23, tzinfo=UTC),
            )
        with engine.begin() as connection:
            connection.execute(delete(knowledge_facts).where(
                knowledge_facts.c.hotel_id == hotel_id,
                knowledge_facts.c.fact_id.like(f"X-{tag}-%"),
            ))
        operation = f"refresh-{tag}"
        result = replace_source_snapshot(
            engine, hotel_id=hotel_id, source_id=source_a["source_id"],
            expected_generation=before.generation, expected_version=ref_a.source_version,
            expected_source_hash=ref_a.source_hash, operation_id=operation,
            pack=validated_replacement, now=datetime(2026, 10, 23, tzinfo=UTC),
        )
        assert result["status"] == "applied" and result["generation"] == before.generation + 1
        replay = replace_source_snapshot(
            engine, hotel_id=hotel_id, source_id=source_a["source_id"],
            expected_generation=before.generation, expected_version=ref_a.source_version,
            expected_source_hash=ref_a.source_hash, operation_id=operation,
            pack=validated_replacement, now=datetime(2026, 10, 23, tzinfo=UTC),
        )
        assert replay["status"] == "noop" and replay["current"]["generation"] == result["generation"]
        different = dict(validated_replacement)
        different["canonical_hash"] = "0" * 64
        with pytest.raises(IdempotencyConflict):
            replace_source_snapshot(
                engine, hotel_id=hotel_id, source_id=source_a["source_id"],
                expected_generation=before.generation, expected_version=ref_a.source_version,
                expected_source_hash=ref_a.source_hash, operation_id=operation,
                pack=different, now=datetime(2026, 10, 23, tzinfo=UTC),
            )
        assert get_hotel(engine, hotel_id)["public_config"] == config_before
        facts = PostgresKnowledgeFactRepository(engine, clock=lambda: datetime(2026, 10, 23, tzinfo=UTC)).list_guest_facts(hotel_id)
        assert omitted["fact_id"] not in {fact.fact_id for fact in facts}
        assert f"F-{tag}-PARKING" in {fact.fact_id for fact in facts}
        after = get_active_snapshot(engine, hotel_id, now=datetime(2026, 10, 23, tzinfo=UTC))
        refreshed_a = next(ref for ref in after.sources if ref.source_id == source_a["source_id"])
        preserved_b = next(ref for ref in after.sources if ref.source_id == source_b["source_id"])
        assert (preserved_b.source_version, preserved_b.source_hash) == (ref_b.source_version, ref_b.source_hash)
        assert validate_evidence_current(engine, hotel_id, [EvidenceBinding(ref_a)],
                                         datetime(2026, 10, 23, tzinfo=UTC)).eligible is False
        media_repo = PostgresMediaRepository(engine)
        active_a_facts = {fact.fact_id for fact in facts
                          if fact.provenance["source_id"] == source_a["source_id"]}
        descriptors = media_repo.list_eligible_media(
            hotel_id, active_a_facts, datetime(2026, 10, 23, tzinfo=UTC),
        )
        assert {item.kind for item in descriptors} == {"image", "video"}
        for descriptor in descriptors:
            asset = media_repo.read_eligible_asset(
                hotel_id, descriptor.media_id, datetime(2026, 10, 23, tzinfo=UTC),
                expected_generation=descriptor.source_generation,
                expected_source_id=descriptor.source_id,
                expected_source_version=descriptor.source_version,
                expected_source_hash=descriptor.source_hash,
                expected_media_sha256=descriptor.sha256,
            )
            assert asset is not None and asset.descriptor.sha256 == descriptor.sha256
            if descriptor.captions_media_id:
                captions = media_repo.read_eligible_asset(
                    hotel_id, descriptor.captions_media_id, datetime(2026, 10, 23, tzinfo=UTC),
                    expected_generation=descriptor.source_generation,
                    expected_source_id=descriptor.source_id,
                    expected_source_version=descriptor.source_version,
                    expected_source_hash=descriptor.source_hash,
                    expected_media_sha256=descriptor.captions_sha256,
                )
                assert captions is not None and captions.mime_type == "text/vtt"
        assert import_hospitality_pack(engine, root, allowed_root=allowed)["status"] == "noop"
        assert get_active_snapshot(engine, hotel_id).generation == after.generation
        assert next(ref for ref in get_active_snapshot(engine, hotel_id).sources
                    if ref.source_id == source_a["source_id"]).source_hash == refreshed_a.source_hash

        expired = get_active_snapshot(engine, hotel_id, now=datetime(2040, 1, 1, tzinfo=UTC))
        assert all(ref.status == "expired" for ref in expired.sources)
        assert validate_evidence_current(engine, hotel_id, [EvidenceBinding(refreshed_a)],
                                         datetime(2040, 1, 1, tzinfo=UTC)).eligible is False
        for descriptor in descriptors:
            assert media_repo.read_eligible_asset(
                hotel_id, descriptor.media_id, datetime(2040, 1, 1, tzinfo=UTC),
                expected_generation=descriptor.source_generation,
                expected_source_id=descriptor.source_id,
                expected_source_version=descriptor.source_version,
                expected_source_hash=descriptor.source_hash,
                expected_media_sha256=descriptor.sha256,
            ) is None

        revoked = transition_source(
            engine, hotel_id=hotel_id, source_id=source_a["source_id"],
            expected_generation=after.generation, expected_version=refreshed_a.source_version,
            expected_source_hash=refreshed_a.source_hash, operation_id=f"revoke-{tag}",
            action="revoke", now=datetime(2026, 10, 23, tzinfo=UTC),
        )
        assert revoked["lifecycle_status"] == "revoked"
        current = get_active_snapshot(engine, hotel_id, now=datetime(2026, 10, 23, tzinfo=UTC))
        revoked_a = next(ref for ref in current.sources if ref.source_id == source_a["source_id"])
        assert revoked_a.status == "revoked"
        assert validate_evidence_current(engine, hotel_id, [EvidenceBinding(refreshed_a)],
                                         datetime(2026, 10, 23, tzinfo=UTC)).eligible is False
        assert import_hospitality_pack(engine, root, allowed_root=allowed)["status"] == "noop"
        assert next(ref for ref in get_active_snapshot(engine, hotel_id).sources
                    if ref.source_id == source_a["source_id"]).status == "revoked"


        # A same-token concurrent publish has exactly one winner.
        replacement2 = root.parent / "replacement-b"
        shutil.copytree(root, replacement2)
        changed2 = dict(manifest)
        source_b_copy = dict(source_b)
        source_b_copy["version"] = "bump"
        changed2["sources"] = [source_b_copy]
        changed2["facts"] = [dict(fact) for fact in manifest["facts"]
                              if fact["source_refs"][0]["source_id"] == source_b["source_id"]]
        changed2["media"] = []
        changed2["pack_version"] = "replacement-b"
        for fact in changed2["facts"]:
            fact["source_refs"][0]["version"] = "bump"
        for path in list(replacement2.rglob("*")):
            if path.is_file() and path.relative_to(replacement2).as_posix() != "manifest.json":
                path.unlink()
        for directory in sorted((path for path in replacement2.rglob("*") if path.is_dir()), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
        (replacement2 / "manifest.json").write_text(json.dumps(changed2, ensure_ascii=False))
        pack2 = validate_pack(replacement2)
        current_b = next(ref for ref in current.sources if ref.source_id == source_b["source_id"])
        def publish(operation_id: str):
            return replace_source_snapshot(
                engine, hotel_id=hotel_id, source_id=source_b["source_id"],
                expected_generation=current.generation, expected_version=current_b.source_version,
                expected_source_hash=current_b.source_hash, operation_id=operation_id,
                pack=pack2, now=datetime(2026, 10, 23, tzinfo=UTC),
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(publish, f"cas-{tag}-{index}") for index in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except VersionConflict:
                outcomes.append("conflict")
        assert sum(outcome != "conflict" for outcome in outcomes) == 1
    finally:
        with engine.begin() as connection:
            connection.execute(delete(lifecycle_operations).where(
                lifecycle_operations.c.hotel_id == hotel_id,
            ))
            connection.execute(delete(knowledge_media).where(knowledge_media.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_facts).where(knowledge_facts.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_sources).where(knowledge_sources.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_packs).where(knowledge_packs.c.hotel_id == hotel_id))
            from staylead_platform.infrastructure.persistence.store import hotels
            connection.execute(delete(hotels).where(hotels.c.hotel_id == hotel_id))
        engine.dispose()


@pytest.mark.skipif(not os.getenv("STAYLEAD_TEST_DATABASE_URL"), reason="isolated Sprint 4 PostgreSQL DSN not configured")
def test_revoked_source_facts_do_not_consume_active_fact_cap(tmp_path: Path):
    engine = create_database_engine(os.environ["STAYLEAD_TEST_DATABASE_URL"])
    apply_migrations(engine)
    tag = uuid4().hex[:10].upper()
    root, manifest = _prepare(tmp_path / "cap", tag)
    hotel_id = manifest["hotel"]["hotel_id"]
    source_a, source_b = manifest["sources"]
    operation_time = datetime(2026, 10, 23, tzinfo=UTC)
    try:
        import_hospitality_pack(engine, root, allowed_root=root.parent)
        snapshot = get_active_snapshot(engine, hotel_id, now=operation_time)
        ref_a = next(ref for ref in snapshot.sources if ref.source_id == source_a["source_id"])
        ref_b = next(ref for ref in snapshot.sources if ref.source_id == source_b["source_id"])
        transition_source(
            engine, hotel_id=hotel_id, source_id=source_b["source_id"], action="revoke",
            expected_generation=snapshot.generation, expected_version=ref_b.source_version,
            expected_source_hash=ref_b.source_hash, operation_id=f"revoke-{tag}", now=operation_time,
        )
        after_revoke = get_active_snapshot(engine, hotel_id, now=operation_time)
        ref_a = next(ref for ref in after_revoke.sources if ref.source_id == source_a["source_id"])

        replacement = root.parent / "replacement-400"
        replacement.mkdir()
        replacement_manifest = dict(manifest)
        replacement_manifest["sources"] = [dict(source_a)]
        template = dict(next(fact for fact in manifest["facts"]
                             if fact["source_refs"][0]["source_id"] == source_a["source_id"]))
        replacement_manifest["facts"] = []
        for index in range(400):
            fact = dict(template)
            fact["fact_id"] = f"CAP-{tag}-{index}"
            fact["source_refs"] = [{"source_id": source_a["source_id"],
                                    "version": source_a["version"]}]
            replacement_manifest["facts"].append(fact)
        replacement_manifest["media"] = []
        (replacement / "manifest.json").write_text(json.dumps(replacement_manifest, ensure_ascii=False))
        pack = validate_pack(replacement)
        result = replace_source_snapshot(
            engine, hotel_id=hotel_id, source_id=source_a["source_id"],
            expected_generation=after_revoke.generation, expected_version=ref_a.source_version,
            expected_source_hash=ref_a.source_hash, operation_id=f"refresh-{tag}",
            pack=pack, now=operation_time,
        )
        assert result["status"] == "applied"
        assert len(PostgresKnowledgeFactRepository(
            engine, clock=lambda: operation_time,
        ).list_guest_facts(hotel_id)) == 400
    finally:
        with engine.begin() as connection:
            connection.execute(delete(messages).where(messages.c.hotel_id == hotel_id))
            connection.execute(delete(requests).where(requests.c.hotel_id == hotel_id))
            connection.execute(delete(sessions).where(sessions.c.hotel_id == hotel_id))
            connection.execute(delete(lifecycle_operations).where(lifecycle_operations.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_media).where(knowledge_media.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_facts).where(knowledge_facts.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_sources).where(knowledge_sources.c.hotel_id == hotel_id))
            connection.execute(delete(knowledge_packs).where(knowledge_packs.c.hotel_id == hotel_id))
            connection.execute(delete(hotels).where(hotels.c.hotel_id == hotel_id))
        engine.dispose()
