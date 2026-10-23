"""Explicit trusted local command for importing a complete synthetic hotel pack."""

import argparse
import json
import os
from pathlib import Path

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    CURRENT_SCHEMA_VERSION,
    schema_version,
)
from staylead_platform.infrastructure.source_connectors.hospitality_pack import (
    import_hospitality_pack,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import one reviewed complete Hospitality data pack")
    parser.add_argument("pack_dir", help="Directory beneath STAYLEAD_KNOWLEDGE_PACK_ROOT")
    args = parser.parse_args()
    allowed_root = os.environ.get("STAYLEAD_KNOWLEDGE_PACK_ROOT")
    if not allowed_root:
        raise SystemExit("STAYLEAD_KNOWLEDGE_PACK_ROOT must name the allowlisted local pack root.")
    engine = create_database_engine(Settings().database_url)
    if schema_version(engine) != CURRENT_SCHEMA_VERSION:
        raise SystemExit("Apply the explicit PostgreSQL schema migration before importing packs.")
    result = import_hospitality_pack(engine, Path(args.pack_dir), allowed_root=allowed_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
