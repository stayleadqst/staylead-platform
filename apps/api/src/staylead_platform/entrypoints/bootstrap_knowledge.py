"""Explicit local fixture bootstrap; never invoked by API startup."""

import argparse
import json
from pathlib import Path

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import schema_version
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import import_fixture_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the approved synthetic hospitality fixture")
    parser.add_argument("--fixture-root", required=True, help="Server-side knowledge-v1 directory")
    args = parser.parse_args()
    engine = create_database_engine(Settings().database_url)
    if schema_version(engine) != 2:
        raise SystemExit("Apply the explicit PostgreSQL migration before fixture bootstrap.")
    report = import_fixture_pack(engine, Path(args.fixture_root))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
