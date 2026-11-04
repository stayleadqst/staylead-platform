"""Deterministic, source-grounded transport comparison for the synthetic pilot."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from staylead_platform.platform.contracts.knowledge import KnowledgeFact

_OFFICIAL_TRANSPORT_CONTACTS = {
    "https://www.grab.com/vn/transport/car/",
    "https://www.greensm.com/vn-vi/greensm-car",
}


def _records(facts: tuple[KnowledgeFact, ...], topic: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, list[KnowledgeFact]]] = {}
    for fact in facts:
        if fact.topic == topic:
            grouped.setdefault(fact.subject, {}).setdefault(fact.field, []).append(fact)
    result: dict[str, dict[str, Any]] = {}
    for subject, fields in grouped.items():
        values: dict[str, Any] = {}
        for name, entries in fields.items():
            distinct = {repr(entry.value) for entry in entries}
            values[name] = entries[0].value if len(distinct) == 1 else None
        result[subject] = values
    return result


def _source_ref(fact: KnowledgeFact) -> dict[str, Any]:
    source = fact.provenance
    return {
        "hotel_id": fact.hotel_id, "source_id": source.get("source_id"),
        "source_version": source.get("source_version"), "source_hash": source.get("source_hash"),
        "source_generation": source.get("source_generation"), "section": source.get("section"),
        "fact_id": fact.fact_id, "synthetic": bool(fact.conditions.get("synthetic", True)),
        "status": fact.status,
    }


def compare_transport(
    facts: tuple[KnowledgeFact, ...], brief_data: Mapping[str, Any], pending_fields: tuple[str, ...],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...], tuple[str, ...]]:
    """Return checked options, contributing fact IDs, and user-facing unknowns."""
    providers = _records(facts, "local_guide.provider")
    routes = _records(facts, "local_guide.route")
    prefs = brief_data.get("transport_preferences")
    prefs = prefs if isinstance(prefs, Mapping) else {}
    party = brief_data.get("party")
    party = party if isinstance(party, Mapping) else {}
    children = party.get("children")
    children = children if isinstance(children, list) else None
    adults = party.get("adults")
    party_pending = bool({"party", "party.adults", "party.children", "party.children.member"} & set(pending_fields))
    passenger_count = (
        adults + len(children) if isinstance(adults, int) and not isinstance(adults, bool)
        and children is not None and not party_pending else None
    )
    pending = set(pending_fields)
    transport_root_pending = "transport_preferences" in pending
    if transport_root_pending:
        pending.update({
            "transport_preferences.mode", "transport_preferences.luggage_count",
            "transport_preferences.child_seat_count", "transport_preferences.access_needs",
        })
    selected_mode = None if transport_root_pending or "transport_preferences.mode" in pending else prefs.get("mode")
    selected_routes = [
        (route_id, route) for route_id, route in routes.items()
        if selected_mode is None or route.get("mode") == selected_mode
    ]
    output: list[dict[str, Any]] = []
    all_fact_ids: list[str] = []
    unknowns = [
        "Provider license, insurance, rental eligibility, and current availability are unknown; confirm them before travel.",
    ]
    for route_id, route in sorted(selected_routes):
        provider_id = route.get("provider_id")
        provider = providers.get(provider_id, {})
        provider_facts = [fact for fact in facts if fact.subject == provider_id and fact.topic == "local_guide.provider"]
        route_facts = [fact for fact in facts if fact.subject == route_id and fact.topic == "local_guide.route"]
        option_facts = provider_facts + route_facts
        fact_ids = tuple(fact.fact_id for fact in option_facts if fact.status in {"confirmed", "unknown", "needs_confirmation"})
        all_fact_ids.extend(fact_ids)
        refs = [_source_ref(fact) for fact in option_facts if fact.fact_id in fact_ids]

        seats = provider.get("seats_excluding_driver")
        seats = seats if isinstance(seats, int) and not isinstance(seats, bool) and seats >= 0 else None
        luggage_capacity = provider.get("luggage_capacity")
        luggage_capacity = luggage_capacity if isinstance(luggage_capacity, int) and not isinstance(luggage_capacity, bool) else None
        luggage_value = None if "transport_preferences.luggage_count" in pending else prefs.get("luggage_count")
        child_value = None if "transport_preferences.child_seat_count" in pending else prefs.get("child_seat_count")
        access_value = None if "transport_preferences.access_needs" in pending else prefs.get("access_needs")
        luggage_required = luggage_value if isinstance(luggage_value, int) and not isinstance(luggage_value, bool) else None
        child_seats = child_value if isinstance(child_value, int) and not isinstance(child_value, bool) else None
        access_needs = access_value
        access_needs = access_needs if isinstance(access_needs, list) else None

        capacity_status = "unknown" if seats is None or passenger_count is None else (
            "not_fit" if passenger_count > seats else "fit"
        )
        luggage_status = "unknown" if luggage_required is None or luggage_capacity is None else (
            "not_fit" if luggage_required > luggage_capacity else "fit"
        )
        child_requirement_pending = transport_root_pending or "transport_preferences.child_seat_count" in pending
        complete_current_party = (
            isinstance(adults, int) and not isinstance(adults, bool)
            and children is not None and not party_pending
        )
        known_zero_child_need = (
            not child_requirement_pending and (
                child_seats == 0 or child_seats is None and complete_current_party and not children
            )
        )
        if known_zero_child_need:
            child_status, child_required = "not_required", 0 if child_seats == 0 else None
        elif child_seats is None:
            child_status, child_required = "unknown", None
        else:
            support = provider.get("child_seat")
            child_required = child_seats
            # A generic support flag does not establish how many seats are available.
            child_status = "not_fit" if support == "unsupported" else "unknown"

        if access_needs == []:
            access_status = "not_required"
        elif not access_needs:
            access_status = "unknown"
        else:
            capabilities = provider.get("access_capabilities")
            capabilities = capabilities if isinstance(capabilities, list) else []
            if any(need not in capabilities for need in access_needs):
                access_status = "unknown"
            else:
                access_status = "fit"
        check_statuses = (capacity_status, luggage_status, child_status, access_status)
        fit_status = "not_fit" if "not_fit" in check_statuses else (
            "unknown" if "unknown" in check_statuses else "fit"
        )

        price = provider.get("price") if isinstance(provider.get("price"), dict) else {}
        amount = price.get("amount") if isinstance(price.get("amount"), int) and not isinstance(price.get("amount"), bool) else None
        basis = price.get("basis") if price.get("basis") in {"per_vehicle_one_way", "per_person_one_way"} else None
        currency = "VND" if price.get("currency") == "VND" and amount is not None else None
        total = amount if basis == "per_vehicle_one_way" else (
            amount * passenger_count if basis == "per_person_one_way" and passenger_count is not None else None
        )
        price_status = "known" if amount is not None and basis and currency and total is not None else "unknown"

        contact_url = provider.get("contact_url") if isinstance(provider.get("contact_url"), str) else None
        if contact_url:
            try:
                parsed_contact = urlsplit(contact_url)
                synthetic_contact = (
                    parsed_contact.scheme == "https" and parsed_contact.hostname == "example.com"
                    and parsed_contact.path.startswith("/synthetic/") and not parsed_contact.query
                    and not parsed_contact.fragment and not parsed_contact.username and not parsed_contact.password
                )
            except ValueError:
                synthetic_contact = False
            if contact_url not in _OFFICIAL_TRANSPORT_CONTACTS and not synthetic_contact:
                contact_url = None
        option_unknowns = [
            "Provider license, insurance, rental eligibility, and current availability are unknown.",
        ]
        for label, status in (("Passenger capacity", capacity_status), ("Luggage capacity", luggage_status),
                              ("Child-seat suitability", child_status), ("Requested accessibility", access_status)):
            if status == "unknown":
                option_unknowns.append(f"{label} is unknown from current approved facts.")
        tradeoffs = [
            provider.get("convenience"), provider.get("vehicle_change"), provider.get("pickup"),
        ]
        output.append({
            "provider_id": provider_id, "name": provider.get("name"), "mode": route.get("mode"),
            "route": {"from": route.get("from"), "to": route.get("to"), "duration_minutes": route.get("duration_minutes")},
            "fit_status": fit_status,
            "checks": {
                "passenger_capacity": {"required": passenger_count, "available": seats, "status": capacity_status},
                "luggage": {"required": luggage_required, "available": luggage_capacity, "status": luggage_status},
                "child_seat": {"required": child_required, "available": provider.get("child_seat"), "status": child_status},
                "access": {"required": access_needs, "available": provider.get("access_capabilities"), "status": access_status},
            },
            "price": {"amount": amount, "total_amount": total, "currency": currency, "basis": basis, "status": price_status},
            "tradeoffs": [item for item in tradeoffs if isinstance(item, str)],
            "unknowns": option_unknowns,
            "contact": {"url": contact_url, "status": "approved" if contact_url else "hotel_verification_fallback",
                         "source_refs": refs if contact_url else []},
            "source_refs": refs, "synthetic": True,
        })
    if not output:
        unknowns.append("No current approved route matches the requested mode; no reverse route is inferred.")
    return tuple(output), tuple(dict.fromkeys(all_fact_ids)), tuple(unknowns)


__all__ = ["compare_transport"]
