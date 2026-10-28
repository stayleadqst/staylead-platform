"""Strict parser for the synthetic Sprint 8 local-guide source pack."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PACK_ID = "staylead-hospitality-local-guide-v1"
PACK_ROOT = "sprint8-local-guide-v1"
PACK_ROOTS = {PACK_ROOT, "sprint8-local-guide-v2-primary", "sprint8-local-guide-v2-secondary"}
HOTEL_ID = "HTL-S8-DEMO"
PACK_FILES = ("sources.json", "venues.json", "providers.json", "routes.json")


class LocalGuidePackValidationError(ValueError):
    """A local-guide pack is malformed, out of scope, or exceeds pilot limits."""


@dataclass(frozen=True)
class LocalGuidePack:
    pack: dict[str, Any]
    venues: tuple[dict[str, Any], ...]
    providers: tuple[dict[str, Any], ...]
    routes: tuple[dict[str, Any], ...]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _read(root: Path, name: str) -> Any:
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise LocalGuidePackValidationError(f"Required local-guide file is missing: {name}.")
    try:
        if path.stat().st_size > 64_000:
            raise LocalGuidePackValidationError(f"Local-guide file exceeds the 64 KB limit: {name}.")
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LocalGuidePackValidationError(f"Invalid local-guide file: {name}.") from exc


def _date(value: Any, label: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LocalGuidePackValidationError(f"{label} must be an ISO date.") from exc
    if parsed.isoformat() != value:
        raise LocalGuidePackValidationError(f"{label} must be a canonical ISO date.")
    return value


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalGuidePackValidationError(f"{label} is required.")
    return value


def _record_rows(
    records: list[dict[str, Any]], *, topic: str, identifier: str, sources: dict[str, dict[str, Any]],
    hotel_id: str, checked_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise LocalGuidePackValidationError(f"{topic} records must be objects.")
        subject = _required_string(record.get(identifier), identifier)
        source_id = _required_string(record.get("source_id"), "source_id")
        source = sources.get(source_id)
        if source is None:
            raise LocalGuidePackValidationError(f"{subject} references an unknown source.")
        section = _required_string(record.get("section"), "section")
        from_date = _date(record.get("valid_from", source["valid_from"]), "valid_from")
        to_date = _date(record.get("valid_to", source["valid_to"]), "valid_to")
        if from_date > to_date or from_date < source["valid_from"] or to_date > source["valid_to"]:
            raise LocalGuidePackValidationError(f"{subject} validity exceeds its source validity.")
        explicit_field = record.get("field")
        if explicit_field is not None:
            field_values = {explicit_field: record.get("value")}
        else:
            ignored = {identifier, "source_id", "section", "valid_from", "valid_to"}
            field_values = {key: value for key, value in record.items() if key not in ignored}
        if not field_values or any(not isinstance(key, str) or not key for key in field_values):
            raise LocalGuidePackValidationError(f"{subject} has no typed field values.")
        for field_name, value in field_values.items():
            fact_id = f"F-{hotel_id}-{subject}-{field_name}-{source_id}"
            semantic_unknown = value is None or value == "unknown"
            semantic_conflict = isinstance(value, dict) and value.get("status") == "conflict"
            fact = {
                "fact_id": fact_id, "hotel_id": hotel_id, "topic": topic,
                "subject": subject, "field": field_name, "value": value,
                "conditions": {"synthetic": True, "source_checked_at": checked_at},
                "status": "needs_confirmation" if semantic_conflict else "unknown" if semantic_unknown else "confirmed",
                "valid_from": from_date, "valid_to": to_date,
                "source_refs": [{"source_id": source_id, "version": source["version"]}],
                "section": section, "fact_version": "1", "approved": True,
                "visibility": "guest", "synthetic": True,
            }
            rows.append(fact)
    return rows


def _validate_records(hotel: dict[str, Any], venues: list[Any], providers: list[Any], routes: list[Any],
                      source_ids: set[str]) -> None:
    venue_fields = {
        "venue_id", "kind", "name", "categories", "price", "duration_minutes", "accessibility",
        "allergy_suitability", "child_safety", "hours", "closed", "closed_reason", "sponsored",
        "sponsor_label", "location", "timezone", "source_id", "section", "valid_from", "valid_to",
    }
    seen_venues: set[str] = set()
    for item in venues:
        if not isinstance(item, dict):
            raise LocalGuidePackValidationError("Venue records must be objects.")
        if "field" in item:
            if set(item) != {"venue_id", "field", "value", "source_id", "section"} or item["field"] != "hours":
                raise LocalGuidePackValidationError("Only the typed hours conflict override is supported.")
            if item["venue_id"] != "DIN-02" or item["source_id"] != "S8-GUIDE-SECONDARY":
                raise LocalGuidePackValidationError("The hours override is outside the approved conflict case.")
            hours_value = item["value"]
            if (not isinstance(hours_value, dict) or set(hours_value) != {"status", "text"}
                    or hours_value.get("status") not in {"conflict", "confirmed"}
                    or not isinstance(hours_value.get("text"), str) or not hours_value["text"]):
                raise LocalGuidePackValidationError("An hours override must remain typed as conflict or synthetic-confirmed.")
            continue
        if not venue_fields - {"valid_from", "valid_to"} <= set(item) or set(item) - venue_fields:
            raise LocalGuidePackValidationError("Venue fields do not match the local-guide schema.")
        venue_id = _required_string(item["venue_id"], "venue_id")
        kind = _required_string(item["kind"], "venue.kind")
        source_id = _required_string(item["source_id"], "venue.source_id")
        if venue_id in seen_venues or source_id not in source_ids:
            raise LocalGuidePackValidationError("Venue IDs and sources must be unique and in scope.")
        seen_venues.add(venue_id)
        if kind not in {"dining", "attraction"} or not _required_string(item.get("name"), "venue.name"):
            raise LocalGuidePackValidationError("Venue kind and name are required.")
        if kind == "dining" and not venue_id.startswith("DIN-") or kind == "attraction" and not venue_id.startswith("ATT-"):
            raise LocalGuidePackValidationError("Venue ID prefix does not match its kind.")
        if not isinstance(item["categories"], list) or not item["categories"] or any(
            not isinstance(value, str) or not value.strip() for value in item["categories"]
        ):
            raise LocalGuidePackValidationError("Venue categories must be nonempty text values.")
        price = item["price"]
        if (not isinstance(price, dict) or set(price) != {"amount", "currency", "basis"}
                or isinstance(price["amount"], bool) or not isinstance(price["amount"], int) or price["amount"] < 0
                or price["currency"] != hotel["currency"] or price["basis"] != "per_person"):
            raise LocalGuidePackValidationError("Venue price must state an integer per-person amount and currency.")
        if isinstance(item["duration_minutes"], bool) or not isinstance(item["duration_minutes"], int) or item["duration_minutes"] <= 0:
            raise LocalGuidePackValidationError("Venue duration must be a positive number of minutes.")
        if not isinstance(item["accessibility"], str) or item["accessibility"] not in {
            "step_free_entry_supported", "step_free_entry_unsupported", "unknown",
        }:
            raise LocalGuidePackValidationError("Accessibility evidence must name the step-free-entry capability or remain unknown.")
        if not isinstance(item["allergy_suitability"], str) or item["allergy_suitability"] not in {
            "peanut_cross_contact_supported", "peanut_cross_contact_unsupported", "unknown",
        }:
            raise LocalGuidePackValidationError("Allergy evidence must name peanut cross-contact controls or remain unknown.")
        if not isinstance(item["child_safety"], str) or item["child_safety"] not in {
            "child_safety_checked_supported", "child_safety_checked_unsupported", "unknown",
        }:
            raise LocalGuidePackValidationError("Child-safety evidence must be scoped and explicit or remain unknown.")
        hours = item["hours"]
        if (not isinstance(hours, dict) or set(hours) != {"status", "text"}
                or not isinstance(hours["status"], str) or hours["status"] not in {"confirmed", "unknown", "conflict"}
                or (hours["status"] == "unknown") != (hours["text"] is None)
                or hours["text"] is not None and not isinstance(hours["text"], str)):
            raise LocalGuidePackValidationError("Hours must be confirmed, unknown, or conflicted without guessing.")
        if not isinstance(item["closed"], bool) or not isinstance(item["sponsored"], bool):
            raise LocalGuidePackValidationError("Closure and sponsorship must be explicit booleans.")
        if item["sponsored"] != bool(item.get("sponsor_label")):
            raise LocalGuidePackValidationError("A sponsored venue needs a visible sponsor label.")
        if item["closed"] != bool(item.get("closed_reason")):
            raise LocalGuidePackValidationError("A closed venue needs an explicit closure reason.")
        if (not isinstance(item["location"], dict) or set(item["location"]) != {"label"}
                or not isinstance(item["location"]["label"], str) or not item["location"]["label"]
                or item["timezone"] != hotel["timezone"]):
            raise LocalGuidePackValidationError("Venue location and property timezone are required.")
    if len(seen_venues) != 6 or sum(1 for row in venues if isinstance(row, dict) and row.get("kind") == "dining") != 3 \
            or sum(1 for row in venues if isinstance(row, dict) and row.get("kind") == "attraction") != 3:
        raise LocalGuidePackValidationError("The catalog must contain three dining venues and three attractions.")
    provider_fields = {"provider_id", "name", "seats_excluding_driver", "luggage_capacity", "child_seat", "access",
                       "conditions", "availability", "source_id", "section"}
    for item in providers:
        if not isinstance(item, dict) or set(item) != provider_fields:
            raise LocalGuidePackValidationError("Provider fields do not match the local-guide schema.")
        _required_string(item["provider_id"], "provider_id")
        _required_string(item["source_id"], "provider.source_id")
        if item["source_id"] not in source_ids:
            raise LocalGuidePackValidationError("Provider source is outside the synthetic property.")
        if not _required_string(item["name"], "provider.name"):
            raise LocalGuidePackValidationError("Provider name is required.")
        seats = item["seats_excluding_driver"]
        if isinstance(seats, bool) or not isinstance(seats, int) or seats < 0:
            raise LocalGuidePackValidationError("Seats must be a nonnegative count excluding the driver.")
        if item["luggage_capacity"] != "unknown" and (
            isinstance(item["luggage_capacity"], bool) or not isinstance(item["luggage_capacity"], int)
            or item["luggage_capacity"] < 0
        ):
            raise LocalGuidePackValidationError("Luggage capacity must be a nonnegative count or unknown.")
        if (not isinstance(item["child_seat"], str) or item["child_seat"] not in {"supported", "unsupported", "unknown"}
                or not isinstance(item["access"], str) or item["access"] not in {
            "supported", "unsupported", "unknown",
        } or not isinstance(item["availability"], str) or item["availability"] != "unknown"):
            raise LocalGuidePackValidationError("Provider suitability and availability must use explicit supported/unknown states.")
        if not isinstance(item["conditions"], list) or any(not isinstance(v, str) for v in item["conditions"]):
            raise LocalGuidePackValidationError("Provider conditions must be a list of text records.")
    if {item.get("provider_id") for item in providers if isinstance(item, dict)} != {"TR-01", "TR-02"}:
        raise LocalGuidePackValidationError("The provider catalog must contain exactly TR-01 and TR-02.")
    route_fields = {"route_id", "provider_id", "mode", "from", "to", "duration_minutes", "time_source", "source_id", "section"}
    for item in routes:
        if not isinstance(item, dict) or set(item) != route_fields:
            raise LocalGuidePackValidationError("Route fields do not match the local-guide schema.")
        for key in ("route_id", "provider_id", "mode", "from", "to", "time_source", "source_id", "section"):
            _required_string(item[key], f"route.{key}")
        if item["source_id"] not in source_ids:
            raise LocalGuidePackValidationError("Route source is outside the synthetic property.")
    venue_ids = {item["venue_id"] for item in venues if isinstance(item, dict) and "field" not in item}
    endpoints = {("HTL-S8-DEMO", "DIN-01"), ("DIN-01", "HTL-S8-DEMO"),
                 ("HTL-S8-DEMO", "ATT-01"), ("ATT-02", "HTL-S8-DEMO")}
    seen_endpoints: set[tuple[str, str]] = set()
    for route in routes:
        edge = (route["from"], route["to"])
        if (route["provider_id"] not in {item["provider_id"] for item in providers}
                or edge not in endpoints or edge in seen_endpoints
                or route["mode"] not in {"walk", "taxi"}
                or isinstance(route["duration_minutes"], bool) or not isinstance(route["duration_minutes"], int)
                or route["duration_minutes"] <= 0
                or route["from"] not in venue_ids | {"HTL-S8-DEMO"}
                or route["to"] not in venue_ids | {"HTL-S8-DEMO"}
                or not isinstance(route["time_source"], str)
                or not route["time_source"].startswith("synthetic checked ")):
            raise LocalGuidePackValidationError("Route direction, mode, duration, or time source is invalid.")
        seen_endpoints.add(edge)
    if seen_endpoints != endpoints:
        raise LocalGuidePackValidationError("The four required route legs must be directional and explicit.")


def parse_local_guide_pack(
    pack_root: str | Path, *, reference_date: date | None = None,
) -> LocalGuidePack:
    root = Path(pack_root).resolve(strict=True)
    if root.name not in PACK_ROOTS or not root.is_dir():
        raise LocalGuidePackValidationError("Pack root must be one of the configured local-guide fixture directories.")
    manifest = _read(root, "manifest.json")
    expected_keys = {"format", "schema_version", "pack_id", "pack_version", "synthetic", "checked_at", "hotel", "files"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise LocalGuidePackValidationError("Manifest fields do not match local-guide schema v1.")
    if (manifest["format"] != "staylead-hospitality-local-guide" or manifest["schema_version"] != 1
            or manifest["pack_id"] != PACK_ID or manifest["synthetic"] is not True
            or manifest["files"] != list(PACK_FILES)):
        raise LocalGuidePackValidationError("Unsupported or non-synthetic local-guide pack.")
    checked_at = _date(manifest["checked_at"], "checked_at")
    if reference_date is not None and checked_at > reference_date.isoformat():
        raise LocalGuidePackValidationError("A source cannot be checked in the future.")
    hotel = manifest["hotel"]
    hotel_fields = {"hotel_id", "slug", "config_version", "name", "address", "timezone", "currency"}
    if not isinstance(hotel, dict) or set(hotel) != hotel_fields or hotel.get("hotel_id") != HOTEL_ID:
        raise LocalGuidePackValidationError("The pilot property identity is invalid.")
    if hotel.get("slug") != "lotus-pilot-demo" or hotel.get("currency") != "VND":
        raise LocalGuidePackValidationError("The pilot property configuration is invalid.")
    source_rows = _read(root, "sources.json")
    if not isinstance(source_rows, list) or not source_rows:
        raise LocalGuidePackValidationError("At least one synthetic source is required.")
    sources: dict[str, dict[str, Any]] = {}
    for source in source_rows:
        required = {"source_id", "version", "scope", "guest_approved", "valid_from", "valid_to", "checked_at", "title", "url", "provenance"}
        if not isinstance(source, dict) or set(source) != required:
            raise LocalGuidePackValidationError("Source fields do not match local-guide schema v1.")
        source_id = _required_string(source.get("source_id"), "source_id")
        if source_id in sources or source["scope"] != "hotel-specific" or source["guest_approved"] is not False:
            raise LocalGuidePackValidationError("Sources must be unique, hotel-scoped, and staged for operator activation.")
        start, end = _date(source["valid_from"], "source.valid_from"), _date(source["valid_to"], "source.valid_to")
        if start > end or _date(source["checked_at"], "source.checked_at") != checked_at:
            raise LocalGuidePackValidationError("Source dates must match the checked synthetic snapshot.")
        label = source["provenance"].get("label") if isinstance(source["provenance"], dict) else None
        if not isinstance(label, str) or "synthetic" not in label.casefold():
            raise LocalGuidePackValidationError("Source provenance must disclose the synthetic scope.")
        if not isinstance(source["url"], str) or not source["url"].startswith("https://example.invalid/"):
            raise LocalGuidePackValidationError("Synthetic source links must use the reserved example.invalid host.")
        sources[source_id] = {**source, "hotel_id": HOTEL_ID}
    rows: dict[str, list[dict[str, Any]]] = {name: _read(root, name) for name in PACK_FILES[1:]}
    if any(not isinstance(value, list) for value in rows.values()):
        raise LocalGuidePackValidationError("Venue, provider, and route files must contain arrays.")
    venues, providers, routes = rows["venues.json"], rows["providers.json"], rows["routes.json"]
    if len([v for v in venues if v.get("kind") in {"dining", "attraction"}]) != 6 or len(providers) != 2 or len(routes) != 4:
        raise LocalGuidePackValidationError("The pilot data must contain 6 venues, 2 providers, and 4 directional routes.")
    venue_ids = {v.get("venue_id") for v in venues if isinstance(v, dict)}
    if not {"DIN-01", "DIN-02", "DIN-03", "ATT-01", "ATT-02", "ATT-03"} <= venue_ids:
        raise LocalGuidePackValidationError("Required venue IDs are missing.")
    if {p.get("provider_id") for p in providers} != {"TR-01", "TR-02"}:
        raise LocalGuidePackValidationError("Required provider IDs are missing.")
    _validate_records(hotel, venues, providers, routes, set(sources))
    route_ids = {route.get("route_id") for route in routes if isinstance(route, dict)}
    if route_ids != {"LEG-01", "LEG-02", "LEG-03", "LEG-04"}:
        raise LocalGuidePackValidationError("The pilot route IDs are not the four approved directional legs.")
    hotel_id = HOTEL_ID
    facts = []
    for filename, topic, identifier in (
        ("venues.json", "local_guide.venue", "venue_id"),
        ("providers.json", "local_guide.provider", "provider_id"),
        ("routes.json", "local_guide.route", "route_id"),
    ):
        facts.extend(_record_rows(rows[filename], topic=topic, identifier=identifier,
                                  sources=sources, hotel_id=hotel_id, checked_at=checked_at))
    fact_ids = [fact["fact_id"] for fact in facts]
    if len(fact_ids) != len(set(fact_ids)) or len(facts) > 400:
        raise LocalGuidePackValidationError("Local-guide facts must be unique and within the M1 serving limit.")
    start_date = min(source["valid_from"] for source in sources.values())
    end_date = max(source["valid_to"] for source in sources.values())
    pack_manifest = {**manifest, "sources": source_rows}
    digest = hashlib.sha256(_canonical(pack_manifest) + b"\n" + _canonical(facts)).hexdigest()
    pack = {
        "pack_id": PACK_ID, "pack_version": manifest["pack_version"], "schema_version": 1,
        "canonical_hash": digest, "manifest": pack_manifest,
        "hotel": {"hotel_id": hotel_id, "slug": hotel["slug"], "config_version": hotel["config_version"],
                  "public_config": {key: hotel[key] for key in ("hotel_id", "name", "address", "timezone", "currency")}
                                  | {"synthetic": True, "source_pack": PACK_ID}},
        "sources": list(sources.values()), "facts": facts, "media": [],
    }
    # Bootstrap imports stage records with current source and fact provenance but no guest visibility.
    if reference_date is not None and not start_date <= reference_date.isoformat() <= end_date:
        raise LocalGuidePackValidationError("Checked date must fall within the source validity window.")
    return LocalGuidePack(pack, tuple(v for v in venues if "field" not in v), tuple(providers), tuple(routes))
