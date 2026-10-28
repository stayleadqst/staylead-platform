from datetime import date
from pathlib import Path

from staylead_platform.domains.hospitality.registration.fixture_pack import (
    parse_fixture_pack,
)


def test_fixture_projection_contains_only_guest_approved_current_facts() -> None:
    root = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1"
    hotels = parse_fixture_pack(root, reference_date=date(2026, 10, 22))

    assert {hotel.hotel_id for hotel in hotels} == {"HTL-CITY01", "HTL-BEACH02", "HTL-RETREAT03"}
    assert all(hotel.synthetic for hotel in hotels)
    assert all(hotel.public_config["source_pack"] == "staylead-hospitality-knowledge-v1" for hotel in hotels)
    assert all(hotel.sources for hotel in hotels)
    sources_by_hotel = {hotel.hotel_id: {source["source_id"]: source for source in hotel.sources}
                        for hotel in hotels}
    assert all(source["guest_approved"] is True and source["scope"] == "hotel-specific"
               for hotel in hotels for source in hotel.sources)
    assert all(ref["source_id"] in sources_by_hotel[hotel.hotel_id]
               and sources_by_hotel[hotel.hotel_id][ref["source_id"]]["version"] == ref["version"]
               for hotel in hotels for fact in hotel.facts for ref in fact["source_refs"])
    assert all(fact["approved"] and fact["visibility"] == "guest" for hotel in hotels for fact in hotel.facts)
    assert not any(fact["fact_id"] == "F-HTL-CITY01-004" for hotel in hotels for fact in hotel.facts)
    assert sum(len(hotel.facts) for hotel in hotels) == 345
    assert all(sum(fact["field"] == "room_type" for fact in hotel.facts) == 3 for hotel in hotels)
    assert all(sum(fact["field"] == "reference_rate" for fact in hotel.facts) == 3 for hotel in hotels)
