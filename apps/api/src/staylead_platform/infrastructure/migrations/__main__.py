"""Apply pinned database migrations explicitly: python -m ...infrastructure.migrations upgrade"""

import argparse

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import apply_migrations


def main() -> None:
    parser = argparse.ArgumentParser(description="StayLead PostgreSQL migrations")
    parser.add_argument("command", choices=["upgrade"])
    args = parser.parse_args()
    if args.command == "upgrade":
        version = apply_migrations(create_database_engine(Settings().database_url))
        print(f"StayLead database schema version {version} is ready.")


if __name__ == "__main__":
    main()
