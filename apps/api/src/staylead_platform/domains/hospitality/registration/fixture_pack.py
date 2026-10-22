"""Pure Hospitality mapping and validation for the authored knowledge-v1 fixture pack."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PACK_ID = "staylead-hospitality-knowledge-v1"
HOTELS = {
    "harbor-city-demo": "HTL-CITY01",
    "lagoon-family-demo": "HTL-BEACH02",
    "pine-ridge-demo": "HTL-RETREAT03",
}
ALLOWED_STATUS = {"confirmed", "unknown", "needs_confirmation"}


class FixtureImportError(ValueError):
    pass


@dataclass(frozen=True)
class BootstrapHotel:
    hotel_id: str
    slug: str
    config_version: str
    public_config: dict[str, Any]
    synthetic: bool
    facts: tuple[dict[str, Any], ...]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureImportError(f"Invalid fixture file: {path.name}") from exc


def parse_fixture_pack(fixture_root: str | Path, *, reference_date: date | None = None) -> tuple[BootstrapHotel, ...]:
    root = Path(fixture_root).resolve()
    if root.name != "knowledge-v1" or not root.is_dir():
        raise FixtureImportError("Fixture root must be the configured knowledge-v1 directory.")
    manifest = _read_json(root / "manifest.json")
    if manifest.get("pack_id") != PACK_ID or manifest.get("synthetic") is not True:
        raise FixtureImportError("Unsupported fixture pack.")
    properties_doc = _read_json(root / "properties.json")
    source_records = _read_json(root / "sources.json")
    fact_records = _read_json(root / "facts.json")
    if not all(isinstance(value, list) for value in (properties_doc.get("properties"), source_records, fact_records)):
        raise FixtureImportError("Fixture schema is invalid.")
    today = (reference_date or date.today()).isoformat()
    sources = {source.get("source_id"): source for source in source_records if isinstance(source, dict)}
    property_rows = {prop.get("hotel_id"): prop for prop in properties_doc["properties"] if isinstance(prop, dict)}
    prepared: list[BootstrapHotel] = []
    for slug, hotel_id in HOTELS.items():
        prop = property_rows.get(hotel_id)
        if not prop or not all(prop.get(key) for key in ("name", "address", "timezone", "currency")):
            raise FixtureImportError(f"Required public property fields are missing for {hotel_id}.")
        hotel_sources = {
            source_id: source for source_id, source in sources.items()
            if source.get("hotel_id") == hotel_id and source.get("scope") == "hotel-specific"
            and source.get("guest_approved") is True
            and source.get("valid_from", "9999") <= today <= source.get("valid_to", "0000")
        }
        selected: list[dict[str, Any]] = []
        for fact in fact_records:
            if not isinstance(fact, dict) or fact.get("hotel_id") != hotel_id:
                continue
            if fact.get("approved") is not True or fact.get("visibility") != "guest":
                continue
            if fact.get("status") not in ALLOWED_STATUS:
                continue
            if not fact.get("fact_id") or not fact.get("topic") or not fact.get("subject") or not fact.get("field"):
                raise FixtureImportError(f"Malformed fact for {hotel_id}.")
            if not (fact.get("valid_from", "9999") <= today <= fact.get("valid_to", "0000")):
                continue
            refs = fact.get("source_refs")
            if not isinstance(refs, list) or not refs:
                raise FixtureImportError(f"Missing source provenance for {fact['fact_id']}.")
            referenced_sources: list[dict[str, Any]] = []
            for ref in refs:
                source = hotel_sources.get(ref.get("source_id"))
                if not source or source.get("version") != ref.get("version") or source.get("hotel_id") != hotel_id:
                    raise FixtureImportError(f"Unapproved source reference for {fact['fact_id']}.")
                referenced_sources.append(source)
            # A fact can only be served while both it and every source that backs
            # it are valid. Persist the intersection so runtime checks stay simple.
            effective_from = max([fact.get("valid_from", "0000"), *(
                source.get("valid_from", "0000") for source in referenced_sources
            )])
            effective_to = min([fact.get("valid_to", "9999"), *(
                source.get("valid_to", "9999") for source in referenced_sources
            )])
            if effective_from > effective_to:
                continue
            prepared_fact = dict(fact)
            prepared_fact["valid_from"] = effective_from
            prepared_fact["valid_to"] = effective_to
            selected.append(prepared_fact)
        if not selected:
            raise FixtureImportError(f"No eligible guest facts for {hotel_id}.")
        config = {
            key: prop[key] for key in ("hotel_id", "name", "address", "description", "timezone", "currency")
            if key in prop
        }
        config.update({"synthetic": True, "source_pack": PACK_ID})
        prepared.append(BootstrapHotel(
            hotel_id=hotel_id, slug=slug, config_version=manifest.get("version", "unknown"),
            public_config=config, synthetic=True, facts=tuple(selected),
        ))
    return tuple(prepared)
