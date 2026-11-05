from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from staylead_platform.domains.hospitality.registration.local_guide import (
    HospitalityLocalGuide,
)
from staylead_platform.domains.hospitality.registration.local_guide_pack import (
    parse_local_guide_pack,
)
from staylead_platform.platform.contracts.knowledge import (
    ActiveKnowledgeSnapshot,
    KnowledgeFact,
    SourceVersionRef,
)
from staylead_platform.platform.contracts.local_guide import LocalGuideRequest

ROOT = Path(__file__).resolve().parents[2] / "fixtures/hospitality/sprint8-local-guide-v1"
NOW = datetime(2026, 10, 28, 9, tzinfo=UTC)


class FakeFactRepository:
    def __init__(self, facts: list[KnowledgeFact]) -> None:
        self.facts = facts

    def list_guest_facts(self, hotel_id: str, *, limit: int = 400, timeout_seconds: float | None = None) -> list[KnowledgeFact]:
        day = NOW.date().isoformat()
        return [fact for fact in self.facts if fact.hotel_id == hotel_id and fact.valid_from <= day <= fact.valid_to][:limit]

    def get_guest_facts(self, hotel_id: str, fact_ids: set[str], *, timeout_seconds: float | None = None) -> list[KnowledgeFact]:
        return [fact for fact in self.facts if fact.hotel_id == hotel_id and fact.fact_id in fact_ids]


class FakeOperatorRepository:
    def __init__(self, facts: list[KnowledgeFact]) -> None:
        self.facts = facts

    def list_operator_facts(self, hotel_id: str) -> tuple[KnowledgeFact, ...]:
        return tuple(fact for fact in self.facts if fact.hotel_id == hotel_id)


def _service() -> HospitalityLocalGuide:
    pack = parse_local_guide_pack(ROOT)
    refs = []
    for source in pack.pack["sources"]:
        refs.append(SourceVersionRef(
            hotel_id="HTL-S8-DEMO", source_id=source["source_id"], hotel_generation=4,
            source_version=source["version"], source_hash="a" * 64, status="approved",
            guest_approved=True, valid_from=source["valid_from"], valid_to=source["valid_to"],
        ))
    facts = []
    for item in pack.pack["facts"]:
        facts.append(KnowledgeFact(
            fact_id=item["fact_id"], hotel_id=item["hotel_id"], topic=item["topic"],
            subject=item["subject"], field=item["field"], value=item["value"],
            conditions=item["conditions"], status=item["status"], valid_from=item["valid_from"],
            valid_to=item["valid_to"], provenance={
                "source_id": item["source_refs"][0]["source_id"],
                "source_version": item["source_refs"][0]["version"], "source_hash": "a" * 64,
                "source_generation": 4, "section": item["section"],
            },
        ))
    repo = FakeFactRepository(facts)
    return HospitalityLocalGuide(
        repo, lambda hotel_id, at, timeout: ActiveKnowledgeSnapshot(hotel_id, 4, tuple(refs)), FakeOperatorRepository(facts),
    )


def _request(preferences: dict[str, Any]) -> LocalGuideRequest:
    return LocalGuideRequest("HTL-S8-DEMO", "recommend nearby places", "en", 1,
                             {"local_guide_preferences": preferences}, NOW)


def test_two_priorities_use_same_catalog_and_disclose_tradeoffs() -> None:
    service = _service()
    quiet_budget = asyncio.run(service.recommend(_request({"interests": ["quiet", "budget"]})))
    culture_social = asyncio.run(service.recommend(_request({"interests": ["culture", "social"]})))
    assert quiet_budget.selected_venue_ids[:2] == ("DIN-01", "ATT-02")
    assert culture_social.selected_venue_ids[:2] == ("DIN-02", "ATT-01")
    river_table = next(item for item in culture_social.supported_claims if item["venue_id"] == "DIN-02")
    assert river_table["sponsored"] is True
    assert "sponsored_disclosed" in river_table["tradeoff_codes"]
    assert "hours" in river_table["conflict_fields"]
    assert any("Hours are unknown or conflicted" in item for item in culture_social.unknowns)
    assert culture_social.generation == 4
    assert culture_social.source_refs[0]["fact_ids"]
    assert all(ref["source_hash"] == "a" * 64 and ref["source_generation"] == 4 for ref in culture_social.source_refs)


def test_dining_only_shortlist_never_returns_attractions() -> None:
    result = asyncio.run(_service().recommend(_request({"venue_kinds": ["dining"], "interests": ["quiet"]})))
    assert result.selected_venue_ids
    assert all(item.startswith("DIN-") for item in result.selected_venue_ids)


def test_hard_unknowns_are_never_certified_as_fit() -> None:
    service = _service()
    result = asyncio.run(service.recommend(_request({
        "interests": ["budget"], "hard_accessibility_needs": ["step_free"],
        "allergy_requirements": ["peanut"], "budget_amount": 150000,
        "budget_currency": "VND", "budget_basis": "per_person", "budget_strength": "hard",
    })))
    assert "DIN-01" in result.selected_venue_ids
    lotus = next(item for item in result.supported_claims if item["venue_id"] == "DIN-01")
    assert lotus["fit_status"] == "unknown"
    assert any("Allergen-specific cross-contact controls are not confirmed" in item for item in lotus["unknowns"])
    garden = next(item for item in result.supported_claims if item["venue_id"] == "ATT-02")
    assert garden["fit_status"] == "unknown"
    assert any("specific accessibility capability is not confirmed" in item for item in garden["unknowns"])


def test_unknown_codes_stay_with_the_venue_that_has_the_unknown_fact() -> None:
    result = asyncio.run(_service().recommend(_request({
        "interests": ["quiet", "nature", "budget"], "pace": "relaxed",
        "budget_amount": 150000, "budget_currency": "VND", "budget_basis": "per_person",
        "budget_strength": "hard",
    })))
    by_id = {claim["venue_id"]: claim for claim in result.supported_claims}
    assert "DIN-01" in by_id and "ATT-02" in by_id
    assert "hours_unconfirmed" not in by_id["DIN-01"]["unknown_codes"]
    assert "hours_unconfirmed" in by_id["ATT-02"]["unknown_codes"]


def test_known_unsupported_access_is_excluded_and_hard_budget_is_comparable() -> None:
    service = _service()
    # The synthetic catalog explicitly confirms step-free entry at DIN-01. Hard budget uses VND/person only.
    accepted = asyncio.run(service.recommend(_request({
        "interests": ["budget"], "hard_accessibility_needs": ["step_free"],
        "budget_amount": 150000, "budget_currency": "VND", "budget_basis": "per_person",
        "budget_strength": "hard",
    })))
    assert "DIN-01" in accepted.selected_venue_ids
    assert next(item for item in accepted.supported_claims if item["venue_id"] == "DIN-01")["fit_status"] == "fit"
    # A budget without a comparable amount/currency/basis cannot be declared a fit.
    unknown_budget = asyncio.run(service.recommend(_request({
        "interests": ["budget"], "budget_amount": 150000, "budget_strength": "hard",
    })))
    lotus = next(item for item in unknown_budget.supported_claims if item["venue_id"] == "DIN-01")
    assert lotus["fit_status"] == "unknown"
    assert any("budget cannot be checked" in item for item in lotus["unknowns"])


def test_guest_catalog_excludes_expired_and_operator_preview_preserves_conflicts() -> None:
    service = _service()
    preview = service.preview("HTL-S8-DEMO", now=NOW)
    assert len(preview.venues) == 6
    assert len(preview.providers) == 2
    assert len(preview.directional_routes) == 4
    assert any(item["subject_id"] == "DIN-02" and item["field"] == "hours" for item in preview.conflicts)
    assert preview.lifecycle_status == "active"


def test_known_unsupported_access_is_excluded_from_final_candidates() -> None:
    service = _service()
    facts = service._fact_repository.facts
    service._fact_repository.facts = [
        fact.__class__(**{**fact.__dict__, "value": "step_free_entry_unsupported"})
        if fact.subject == "DIN-01" and fact.field == "accessibility" else fact
        for fact in facts
    ]
    result = asyncio.run(service.recommend(_request({
        "interests": ["budget"], "hard_accessibility_needs": ["step_free"],
    })))
    assert "DIN-01" not in result.selected_venue_ids


def test_specific_access_evidence_does_not_certify_other_access_or_allergy_needs() -> None:
    service = _service()
    result = asyncio.run(service.recommend(_request({
        "hard_accessibility_needs": ["wheelchair_access"], "allergy_requirements": ["peanut"],
    })))
    lotus = next(item for item in result.supported_claims if item["venue_id"] == "DIN-01")
    assert lotus["fit_status"] == "unknown"
    assert any("specific accessibility capability is not confirmed" in item for item in lotus["unknowns"])
    assert any("Allergen-specific cross-contact controls are not confirmed" in item for item in lotus["unknowns"])
