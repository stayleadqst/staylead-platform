"""Hospitality projection and grounded shortlist policy for the local-guide pilot."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from staylead_platform.domains.hospitality.registration.local_guide_pack import (
    HOTEL_ID,
    LocalGuidePack,
    LocalGuidePackValidationError,
    parse_local_guide_pack,
)
from staylead_platform.platform.contracts.knowledge import (
    ActiveKnowledgeSnapshot,
    KnowledgeFact,
    KnowledgeFactRepository,
)
from staylead_platform.platform.contracts.local_guide import LocalGuideRequest, LocalGuideResult


class LocalGuideOperatorRepository(Protocol):
    def list_operator_facts(self, hotel_id: str) -> tuple[KnowledgeFact, ...]: ...


@dataclass(frozen=True)
class GuidePreview:
    hotel_id: str
    snapshot_generation: int | None
    synthetic: bool
    lifecycle_status: str
    venues: tuple[dict[str, Any], ...]
    providers: tuple[dict[str, Any], ...]
    directional_routes: tuple[dict[str, Any], ...]
    gaps: tuple[str, ...]
    conflicts: tuple[dict[str, Any], ...]
    source_refs: tuple[dict[str, Any], ...]


def _records(facts: tuple[KnowledgeFact, ...] | list[KnowledgeFact], topic: str) -> dict[str, dict[str, list[KnowledgeFact]]]:
    grouped: dict[str, dict[str, list[KnowledgeFact]]] = defaultdict(lambda: defaultdict(list))
    for fact in facts:
        if fact.topic == topic:
            grouped[fact.subject][fact.field].append(fact)
    return grouped


def _source_ref(fact: KnowledgeFact) -> dict[str, Any]:
    source = fact.provenance
    return {
        "hotel_id": fact.hotel_id, "source_id": source.get("source_id"),
        "source_version": source.get("source_version"), "source_hash": source.get("source_hash"),
        "source_generation": source.get("source_generation"), "section": source.get("section"),
        "fact_id": fact.fact_id, "checked_at": fact.conditions.get("source_checked_at"),
        "synthetic": bool(fact.conditions.get("synthetic", True)),
        "status": fact.status,
    }


def _record_value(fields: dict[str, list[KnowledgeFact]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, facts in fields.items():
        ordered = sorted(facts, key=lambda fact: fact.fact_id)
        unique = {repr(fact.value) for fact in ordered}
        if len(unique) == 1:
            values[field] = ordered[0].value
        else:
            values[field] = {"status": "conflict", "values": [fact.value for fact in ordered]}
    return values


def _field_provenance(fields: dict[str, list[KnowledgeFact]]) -> dict[str, tuple[dict[str, Any], ...]]:
    return {
        field: tuple({
            "fact_id": fact.fact_id, "status": fact.status,
            "valid_from": fact.valid_from, "valid_to": fact.valid_to,
            **_source_ref(fact),
        } for fact in sorted(records, key=lambda item: item.fact_id))
        for field, records in fields.items()
    }


def _preview_conflicts(facts: tuple[KnowledgeFact, ...]) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, str, str], list[KnowledgeFact]] = defaultdict(list)
    for fact in facts:
        grouped[(fact.topic, fact.subject, fact.field)].append(fact)
    return tuple({
        "topic": key[0], "subject_id": key[1], "field": key[2],
        "fact_ids": tuple(fact.fact_id for fact in values),
        "values": tuple(fact.value for fact in values),
        "source_refs": tuple(_source_ref(fact) for fact in values),
    } for key, values in grouped.items()
        if len({repr(item.value) for item in values}) > 1)


def _hard_need_status(field_value: Any, need: str, *, kind: str) -> str:
    """Resolve only a precisely scoped catalog assertion; broad labels prove no hard need."""
    if kind == "accessibility" and need == "step_free":
        return {
            "step_free_entry_supported": "supported",
            "step_free_entry_unsupported": "unsupported",
        }.get(field_value, "unknown")
    if kind == "allergy" and need == "peanut":
        return {
            "peanut_cross_contact_supported": "supported",
            "peanut_cross_contact_unsupported": "unsupported",
        }.get(field_value, "unknown")
    # A general access/allergy label cannot establish a differently scoped capability.
    return "unknown"


def current_local_guide_facts(
    repository: KnowledgeFactRepository, hotel_id: str, *, limit: int = 400,
    timeout_seconds: float | None = None,
) -> tuple[KnowledgeFact, ...]:
    """Return only current guest-approved guide facts through the M1 guest port."""
    if hotel_id != HOTEL_ID:
        return ()
    return tuple(fact for fact in repository.list_guest_facts(
        hotel_id, limit=min(max(limit, 1), 400), timeout_seconds=timeout_seconds,
    )
                 if fact.topic.startswith("local_guide."))


class HospitalityLocalGuide:
    """Read-only M1 projection plus deterministic suitability-aware shortlist policy."""

    def __init__(
        self, fact_repository: KnowledgeFactRepository,
        snapshot_reader: Callable[[str, datetime, float | None], ActiveKnowledgeSnapshot | None],
        operator_repository: LocalGuideOperatorRepository | None = None,
    ) -> None:
        self._fact_repository = fact_repository
        self._snapshot_reader = snapshot_reader
        self._operator_repository = operator_repository

    def preview(self, hotel_id: str, *, now: datetime | None = None) -> GuidePreview:
        checked = (now or datetime.now(UTC)).astimezone(UTC)
        if hotel_id != HOTEL_ID:
            return GuidePreview(hotel_id, None, True, "out_of_scope", (), (), (),
                                ("This preview is outside the synthetic pilot property.",), (), ())
        snapshot = self._snapshot_reader(hotel_id, checked, None)
        if snapshot is None:
            return GuidePreview(hotel_id, None, True, "not_imported", (), (), (),
                                ("No local-guide snapshot has been imported.",), (), ())
        facts = (self._operator_repository.list_operator_facts(hotel_id)
                 if self._operator_repository is not None
                 else tuple(self._fact_repository.list_guest_facts(hotel_id, limit=400)))
        facts = tuple(fact for fact in facts if fact.topic.startswith("local_guide."))
        venues = tuple({"venue_id": subject, **_record_value(fields), "field_provenance": _field_provenance(fields)}
                       for subject, fields in _records(facts, "local_guide.venue").items())
        providers = tuple({"provider_id": subject, **_record_value(fields), "field_provenance": _field_provenance(fields)}
                          for subject, fields in _records(facts, "local_guide.provider").items())
        routes = tuple({"route_id": subject, **_record_value(fields), "field_provenance": _field_provenance(fields)}
                       for subject, fields in _records(facts, "local_guide.route").items())
        refs = tuple({
            "source_id": item.source_id, "version": item.source_version, "hash": item.source_hash,
            "generation": item.hotel_generation, "status": item.status,
            "guest_approved": item.guest_approved, "valid_from": item.valid_from, "valid_to": item.valid_to,
            "last_failure": item.last_failure, "last_success_at": item.last_success_at,
        } for item in snapshot.sources)
        guide_sources = [item for item in refs if item["source_id"].startswith("S8-GUIDE-")]
        if not guide_sources:
            state = "not_imported"
        elif any(item["status"] == "revoked" for item in guide_sources):
            state = "revoked" if not any(item["guest_approved"] for item in guide_sources) else "partial"
        elif all(item["guest_approved"] for item in guide_sources):
            state = "active"
        else:
            state = "staged"
        gaps: list[str] = []
        if len(venues) != 6:
            gaps.append("Venue count is incomplete; missing records remain unknown.")
        if len(providers) != 2:
            gaps.append("Provider count is incomplete; missing providers remain unknown.")
        if len(routes) != 4:
            gaps.append("Route coverage is incomplete; missing directions remain unknown.")
        for venue in venues:
            hours = venue.get("hours")
            if isinstance(hours, dict) and hours.get("status") == "unknown":
                gaps.append(f"{venue['venue_id']}: hours are unknown.")
            if venue.get("accessibility") == "unknown":
                gaps.append(f"{venue['venue_id']}: accessibility suitability is unknown.")
            if venue.get("allergy_suitability") == "unknown":
                gaps.append(f"{venue['venue_id']}: allergy suitability is unknown.")
        known_edges = {(route.get("from"), route.get("to")) for route in routes}
        for origin, destination in (("HTL-S8-DEMO", "ATT-02"), ("ATT-01", "HTL-S8-DEMO")):
            if (origin, destination) not in known_edges:
                gaps.append(f"{origin} to {destination}: route is unknown; no reverse direction is inferred.")
        return GuidePreview(hotel_id, snapshot.generation, True, state, venues, providers, routes,
                            tuple(gaps), _preview_conflicts(facts), refs)

    async def recommend(self, request: LocalGuideRequest) -> LocalGuideResult:
        if request.hotel_id != HOTEL_ID:
            return LocalGuideResult(request.hotel_id, 0, unknowns=("No approved local guide is available for this property.",))
        timeout = request.timeout_seconds
        snapshot = await asyncio.to_thread(self._snapshot_reader, request.hotel_id, request.now, timeout)
        if snapshot is None:
            return LocalGuideResult(request.hotel_id, 0, unknowns=("No approved local guide is available.",))
        facts = await asyncio.to_thread(current_local_guide_facts, self._fact_repository, request.hotel_id,
                                        timeout_seconds=timeout)
        current_sources = {ref.source_id: ref for ref in snapshot.sources
                           if ref.guest_approved and ref.status in {"approved", "refresh_failed"}}
        facts = tuple(fact for fact in facts if fact.provenance.get("source_id") in current_sources)
        grouped = _records(facts, "local_guide.venue")
        prefs = request.brief_data.get("local_guide_preferences", {})
        if not isinstance(prefs, dict):
            prefs = {}
        interests = {value.casefold() for value in prefs.get("interests", []) if isinstance(value, str)}
        hard_budget = prefs.get("budget_strength") == "hard"
        budget = prefs.get("budget_amount") if isinstance(prefs.get("budget_amount"), int) else None
        budget_currency = prefs.get("budget_currency")
        budget_basis = prefs.get("budget_basis")
        hard_access_needs = tuple(prefs.get("hard_accessibility_needs", ()))
        allergy_requirements = tuple(prefs.get("allergy_requirements", ()))
        child_safety_required = bool(prefs.get("child_safety_required"))
        requested_kinds = set(prefs.get("venue_kinds", ()))
        selected: list[tuple[int, str, dict[str, Any], tuple[KnowledgeFact, ...]]] = []
        for venue_id, field_map in grouped.items():
            record = _record_value(field_map)
            if record.get("closed") is True or not record.get("name"):
                continue
            if requested_kinds and record.get("kind") not in requested_kinds:
                continue
            price = record.get("price") if isinstance(record.get("price"), dict) else {}
            amount = price.get("amount")
            budget_unknown = False
            if hard_budget:
                comparable = (isinstance(amount, int) and not isinstance(amount, bool)
                              and price.get("currency") == budget_currency == "VND"
                              and price.get("basis") == budget_basis == "per_person")
                if not comparable or budget is None:
                    budget_unknown = True
                elif amount > budget:
                    continue
            access_statuses = tuple(_hard_need_status(record.get("accessibility"), need, kind="accessibility")
                                    for need in hard_access_needs)
            if "unsupported" in access_statuses:
                continue
            allergy_statuses = tuple(_hard_need_status(record.get("allergy_suitability"), need, kind="allergy")
                                     for need in allergy_requirements)
            if "unsupported" in allergy_statuses:
                continue
            child_safety = record.get("child_safety")
            child_status = {
                "child_safety_checked_supported": "supported",
                "child_safety_checked_unsupported": "unsupported",
            }.get(child_safety, "unknown")
            if child_safety_required and child_status == "unsupported":
                continue
            score = len(interests.intersection({str(v).casefold() for v in record.get("categories", [])}))
            if prefs.get("pace") == "relaxed" and isinstance(record.get("duration_minutes"), int):
                score += 1 if record["duration_minutes"] <= 60 else 0
            unknowns = []
            unknown_codes: list[str] = []
            if any(status == "unknown" for status in access_statuses):
                unknowns.append("The specific accessibility capability is not confirmed; verify the requested access feature before visiting.")
                unknown_codes.append("accessibility_unconfirmed")
            if any(status == "unknown" for status in allergy_statuses):
                unknowns.append("Allergen-specific cross-contact controls are not confirmed; verify ingredients and controls with the venue.")
                unknown_codes.append("allergy_unconfirmed")
            if child_safety_required and child_status == "unknown":
                unknowns.append("Child safety suitability is not confirmed; verify the relevant safety details with the venue.")
                unknown_codes.append("child_safety_unconfirmed")
            if budget_unknown:
                unknowns.append("The budget cannot be checked against a confirmed per-person VND price; verify the amount and basis.")
                unknown_codes.append("budget_unconfirmed")
            hours = record.get("hours")
            if isinstance(hours, dict) and hours.get("status") in {"unknown", "conflict"}:
                unknowns.append("Hours are unknown or conflicted; confirm current hours before visiting.")
                unknown_codes.append("hours_unconfirmed")
            venue_facts = tuple(fact for records in field_map.values() for fact in records)
            record["_unknowns"] = tuple(unknowns)
            record["_unknown_codes"] = tuple(unknown_codes)
            record["_hard_unknown"] = bool(
                budget_unknown
                or "unknown" in access_statuses
                or "unknown" in allergy_statuses
                or child_safety_required and child_status == "unknown"
            )
            selected.append((score, venue_id, record, venue_facts))
        selected.sort(key=lambda item: (-item[0], item[1]))
        selected = selected[:3]
        claims: list[dict[str, Any]] = []
        fact_ids: list[str] = []
        source_ref_facts: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        unknowns: list[str] = []
        conflicts = _preview_conflicts(facts)
        conflict_keys = {(item["subject_id"], item["field"]) for item in conflicts}
        for score, venue_id, record, venue_facts in selected:
            ids = tuple(fact.fact_id for fact in venue_facts if fact.status in {"confirmed", "unknown", "needs_confirmation"})
            fact_ids.extend(ids)
            for fact in venue_facts:
                source = _source_ref(fact)
                source_ref_facts[(str(source["source_id"]), str(source["source_version"]))].append(source)
            reasons = [f"interest:{item}" for item in sorted(interests.intersection(
                {str(v).casefold() for v in record.get("categories", [])}))]
            price = record.get("price", {})
            claims.append({
                "venue_id": venue_id, "name": record["name"], "kind": record.get("kind"),
                "fit_status": "unknown" if record["_hard_unknown"] else "fit",
                "reason_codes": tuple(reasons or ("available_catalog_match",)),
                "tradeoff_codes": ("sponsored_disclosed",) if record.get("sponsored") else (),
                "sponsored": bool(record.get("sponsored")), "sponsor_label": record.get("sponsor_label"),
                "price": price, "duration_minutes": record.get("duration_minutes"),
                "hours_status": record.get("hours", {}).get("status") if isinstance(record.get("hours"), dict) else "unknown",
                "conflict_fields": tuple(field for subject, field in conflict_keys if subject == venue_id),
                "unknowns": record["_unknowns"], "unknown_codes": record["_unknown_codes"], "fact_ids": ids,
            })
            unknowns.extend(record["_unknowns"])
        conflict_messages = tuple(
            f"{item['subject_id']} {item['field']} conflict must be resolved before relying on it."
            for item in conflicts if item["subject_id"] in {claim["venue_id"] for claim in claims}
        )
        return LocalGuideResult(
            hotel_id=request.hotel_id, generation=snapshot.generation,
            selected_venue_ids=tuple(claim["venue_id"] for claim in claims),
            fact_ids=tuple(dict.fromkeys(fact_ids)), supported_claims=tuple(claims),
            unknowns=tuple(dict.fromkeys(unknowns)), conflicts=conflict_messages,
            source_refs=tuple({
                "hotel_id": items[0]["hotel_id"], "source_id": key[0],
                "source_version": key[1], "source_hash": items[0]["source_hash"],
                "source_generation": items[0]["source_generation"],
                "fact_ids": tuple(sorted({item["fact_id"] for item in items})),
                "sections": tuple(sorted({item["section"] for item in items})),
                "checked_at": items[0]["checked_at"], "synthetic": all(item["synthetic"] for item in items),
                "status": items[0]["status"],
            } for key, items in source_ref_facts.items()),
            metadata={"synthetic": True, "locale": request.locale, "brief_version": request.brief_version},
        )


__all__ = [
    "GuidePreview", "HospitalityLocalGuide", "LocalGuidePack", "LocalGuidePackValidationError",
    "current_local_guide_facts", "parse_local_guide_pack",
]
