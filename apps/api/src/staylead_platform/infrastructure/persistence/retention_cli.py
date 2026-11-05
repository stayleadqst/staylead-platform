"""Explicit local entry point for guest-session retention cleanup."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import purge_expired_sessions


def _parse_now(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--now must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--now must include a UTC offset")
    return parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge expired guest sessions and aged quota metadata.")
    parser.add_argument(
        "--now", help="explicit ISO-8601 clock for deterministic local cleanup checks",
    )
    args = parser.parse_args()
    engine = create_database_engine(Settings().database_url)
    try:
        count = purge_expired_sessions(engine, now=_parse_now(args.now))
        print(f"Purged {count} expired guest session(s).")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
