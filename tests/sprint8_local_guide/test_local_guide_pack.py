from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from staylead_platform.domains.hospitality.registration.local_guide_pack import (
    LocalGuidePackValidationError,
    parse_local_guide_pack,
)

ROOT = Path(__file__).resolve().parents[2] / "fixtures/hospitality/sprint8-local-guide-v1"


def test_synthetic_pack_maps_to_current_m1_fact_contract() -> None:
    pack = parse_local_guide_pack(ROOT)
    assert pack.pack["hotel"]["hotel_id"] == "HTL-S8-DEMO"
    assert len(pack.venues) == 6
    assert len(pack.providers) == 2
    assert len(pack.routes) == 4
    assert len(pack.pack["facts"]) == 129
    facts = pack.pack["facts"]
    assert all(fact["approved"] is True and fact["visibility"] == "guest" for fact in facts)
    assert all(fact["conditions"]["synthetic"] is True for fact in facts)
    assert {fact["status"] for fact in facts} >= {"unknown", "needs_confirmation", "confirmed"}
    old_fort = [fact for fact in facts if fact["subject"] == "ATT-03"]
    assert old_fort and all(fact["valid_to"] == "2026-10-01" for fact in old_fort)
    assert {route["from"] + "->" + route["to"] for route in pack.routes} == {
        "HTL-S8-DEMO->DIN-01", "DIN-01->HTL-S8-DEMO",
        "HTL-S8-DEMO->ATT-01", "ATT-02->HTL-S8-DEMO",
    }
    assert all(provider["availability"] == "unknown" for provider in pack.providers)


def test_server_selected_refresh_revisions_parse_as_versioned_synthetic_packs() -> None:
    fixtures = Path(__file__).resolve().parents[2] / "fixtures/hospitality"
    primary = parse_local_guide_pack(fixtures / "sprint8-local-guide-v2-primary")
    secondary = parse_local_guide_pack(fixtures / "sprint8-local-guide-v2-secondary")
    assert primary.pack["sources"][0]["version"] == "2.0"
    lotus = next(item for item in primary.venues if item["venue_id"] == "DIN-01")
    assert lotus["price"]["amount"] == 110000
    river_hours = [item for item in secondary.pack["facts"]
                   if item["subject"] == "DIN-02" and item["field"] == "hours"]
    assert river_hours[0]["value"] == {"status": "confirmed", "text": "Synthetic checked hours 11:00-21:00"}


def test_pack_rejects_hours_override_with_missing_text(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "fixtures/hospitality/sprint8-local-guide-v2-secondary"
    target = tmp_path / source.name
    shutil.copytree(source, target)
    path = target / "venues.json"
    venues = json.loads(path.read_text(encoding="utf-8"))
    override = next(item for item in venues if item.get("field") == "hours")
    override["value"] = {"status": "confirmed", "text": None}
    path.write_text(json.dumps(venues), encoding="utf-8")
    with pytest.raises(LocalGuidePackValidationError, match="hours override"):
        parse_local_guide_pack(target)


def _copy_pack(tmp_path: Path) -> Path:
    target = tmp_path / ROOT.name
    shutil.copytree(ROOT, target)
    return target


def test_pack_rejects_untyped_or_injected_venue_fields(tmp_path: Path) -> None:
    target = _copy_pack(tmp_path)
    path = target / "venues.json"
    venues = json.loads(path.read_text(encoding="utf-8"))
    venues[0]["hotel_approved"] = True
    path.write_text(json.dumps(venues), encoding="utf-8")
    with pytest.raises(LocalGuidePackValidationError, match="Venue fields"):
        parse_local_guide_pack(target)


def test_pack_rejects_capacity_that_does_not_exclude_driver(tmp_path: Path) -> None:
    target = _copy_pack(tmp_path)
    path = target / "providers.json"
    providers = json.loads(path.read_text(encoding="utf-8"))
    providers[0]["seats_excluding_driver"] = True
    path.write_text(json.dumps(providers), encoding="utf-8")
    with pytest.raises(LocalGuidePackValidationError, match="[Ss]eats"):
        parse_local_guide_pack(target)


def test_pack_rejects_synthetic_metadata_without_provenance_label(tmp_path: Path) -> None:
    target = _copy_pack(tmp_path)
    path = target / "sources.json"
    sources = json.loads(path.read_text(encoding="utf-8"))
    sources[0]["provenance"] = {}
    path.write_text(json.dumps(sources), encoding="utf-8")
    with pytest.raises(LocalGuidePackValidationError, match="provenance"):
        parse_local_guide_pack(target)


def test_pack_rejects_oversized_data_file(tmp_path: Path) -> None:
    target = _copy_pack(tmp_path)
    (target / "routes.json").write_text(" " * 64_001, encoding="utf-8")
    with pytest.raises(LocalGuidePackValidationError, match="64 KB"):
        parse_local_guide_pack(target)
