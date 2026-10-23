"""Trusted local CLI for source snapshot refresh, revoke, delete, and state inspection."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import get_active_snapshot
from staylead_platform.infrastructure.source_connectors.hospitality_pack import (
    refresh_hospitality_source,
    transition_hospitality_source,
)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hotel-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--expected-generation", required=True, type=int)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-source-hash", required=True)
    parser.add_argument("--operation-id", required=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Trusted local Hospitality source lifecycle")
    subparsers = parser.add_subparsers(dest="command", required=True)
    refresh = subparsers.add_parser("refresh", help="atomically replace one source snapshot")
    _common(refresh)
    refresh.add_argument("--pack-root", required=True, type=Path)
    refresh.add_argument("--allowed-root", required=True, type=Path)
    for action in ("revoke", "delete"):
        command = subparsers.add_parser(action, help=f"{action} one selected source")
        _common(command)
    snapshot = subparsers.add_parser("snapshot", help="show current source versions and lifecycle")
    snapshot.add_argument("--hotel-id", required=True)
    args = parser.parse_args()
    engine = create_database_engine(Settings().database_url)
    try:
        if args.command == "refresh":
            result = refresh_hospitality_source(
                engine, args.pack_root, allowed_root=args.allowed_root,
                hotel_id=args.hotel_id, source_id=args.source_id,
                expected_generation=args.expected_generation, expected_version=args.expected_version,
                expected_source_hash=args.expected_source_hash, operation_id=args.operation_id,
            )
        elif args.command in {"revoke", "delete"}:
            result = transition_hospitality_source(
                engine, hotel_id=args.hotel_id, source_id=args.source_id,
                expected_generation=args.expected_generation, expected_version=args.expected_version,
                expected_source_hash=args.expected_source_hash, operation_id=args.operation_id,
                action=args.command,
            )
        else:
            current = get_active_snapshot(engine, args.hotel_id)
            result = asdict(current) if current is not None else {"status": "missing", "hotel_id": args.hotel_id}
        print(json.dumps(result, sort_keys=True, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
