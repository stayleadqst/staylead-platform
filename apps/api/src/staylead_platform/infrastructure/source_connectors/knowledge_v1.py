"""Read-only filesystem connector for the single supported hospitality fixture format."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from staylead_platform.domains.hospitality.registration.fixture_pack import parse_fixture_pack
from staylead_platform.infrastructure.persistence.store import save_bootstrap


def import_fixture_pack(engine: Engine, fixture_root: str | Path) -> dict[str, Any]:
    prepared = parse_fixture_pack(fixture_root)
    imported_at = datetime.now(UTC)
    report: dict[str, Any] = {
        "pack_id": "staylead-hospitality-knowledge-v1",
        "reference_date": datetime.now(UTC).date().isoformat(),
        "hotels": {},
    }
    for item in prepared:
        facts = []
        for fact in item.facts:
            reference = fact["source_refs"][0]
            facts.append({
                "fact_id": fact["fact_id"], "hotel_id": item.hotel_id,
                "source_id": reference["source_id"], "source_version": reference["version"],
                "section": reference["section"], "fact_version": fact["version"],
                "status": fact["status"], "valid_from": fact["valid_from"],
                "valid_to": fact["valid_to"], "fact": fact, "imported_at": imported_at,
            })
        count = save_bootstrap(
            engine, hotel_id=item.hotel_id, slug=item.slug,
            config_version=item.config_version, public_config=item.public_config,
            synthetic=item.synthetic, facts=facts, sources=list(item.sources),
        )
        report["hotels"][item.hotel_id] = {
            "slug": item.slug, "config_version": item.config_version, "guest_facts": count,
        }
    return report
