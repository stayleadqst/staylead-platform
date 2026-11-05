"""Sprint 6 language preference persistence and revision races."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations,
    commit_language_preference,
    create_session,
    get_language_preference,
)

TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to an isolated Sprint 6 PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    assert apply_migrations(database) == 8
    yield database
    database.dispose()


def test_language_preference_is_session_scoped_idempotent_and_cas_guarded(engine) -> None:
    session_id = str(uuid.uuid4())
    hotel_id = f"HTL-{uuid.uuid4().hex[:12]}"
    create_session(engine, session_id, hotel_id, datetime.now(UTC) + timedelta(hours=1))
    assert get_language_preference(engine, session_id=session_id, hotel_id=hotel_id) is None
    assert get_language_preference(engine, session_id=session_id, hotel_id="HTL-other") is None

    first = commit_language_preference(
        engine, session_id=session_id, hotel_id=hotel_id, language_tag="fr-FR",
        source="inferred", expected_revision=0,
    )
    assert (first["language_tag"], first["source"], first["revision"]) == ("fr-FR", "inferred", 1)
    repeated = commit_language_preference(
        engine, session_id=session_id, hotel_id=hotel_id, language_tag="fr-FR",
        source="explicit", expected_revision=1,
    )
    assert (repeated["revision"], repeated["source"]) == (1, "explicit")

    stale_writer = commit_language_preference(
        engine, session_id=session_id, hotel_id=hotel_id, language_tag="ja",
        source="explicit", expected_revision=0,
    )
    assert (stale_writer["language_tag"], stale_writer["source"], stale_writer["revision"]) == ("fr-FR", "explicit", 1)
    assert get_language_preference(engine, session_id=session_id, hotel_id=hotel_id) == stale_writer
    restarted = create_database_engine(TEST_DSN)
    try:
        assert get_language_preference(restarted, session_id=session_id, hotel_id=hotel_id) == stale_writer
    finally:
        restarted.dispose()
