#!/usr/bin/env python3
"""Validate structural integrity and safety boundaries of knowledge-v1."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOTEL_IDS = {"HTL-CITY01", "HTL-BEACH02", "HTL-RETREAT03"}
REQUIRED_TOPICS = {"identity","checkin","checkout","booking","cancel","payments","invoice","rooms","child","guardian","access","food","dietary","allergies","wifi","pool","spa","gym","laundry","parking","pets","smoking","noise","workspace","transport","localguide","safety","security","privacy","lostfound","housekeeping","maintenance","complaints","language","contact","outage","weather","unavailability"}

def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def fail(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)

def main() -> int:
    errors: list[str] = []
    facts = load("facts.json")
    sources = load("sources.json")
    properties = load("properties.json")
    manifest = load("manifest.json")
    lifecycle = load("lifecycle_scenarios.json")
    source_by_id = {s["source_id"]: s for s in sources}
    fail(errors, len(source_by_id) == len(sources), "source_id values must be unique")
    fail(errors, not list((ROOT/"sources").glob("htl-*.txt")), "stale mixed-audience source files remain at sources root")
    fact_ids = [f.get("fact_id") for f in facts]
    fail(errors, len(fact_ids) == len(set(fact_ids)), "fact_id values must be unique")
    fact_keys=[(f.get("hotel_id"),f.get("topic"),f.get("subject"),f.get("field")) for f in facts]
    fail(errors, len(fact_keys)==len(set(fact_keys)), "active corpus has duplicate semantic fact keys")
    counts = Counter(f.get("hotel_id") for f in facts)
    fail(errors, set(counts) == HOTEL_IDS, "active facts must cover exactly the three declared hotel IDs")
    for hid in HOTEL_IDS:
        fail(errors, counts[hid] >= 100, f"{hid} has fewer than 100 active atomic facts")
    for f in facts:
        for key in ("fact_id","hotel_id","topic","subject","field","value","conditions","status","source_refs","visibility","approved","version","valid_from","valid_to","synthetic"):
            fail(errors, key in f, f"{f.get('fact_id','<unknown>')} missing {key}")
        fail(errors, f.get("hotel_id") in HOTEL_IDS, f"unknown property on {f.get('fact_id')}")
        fail(errors, f.get("visibility") in ("guest","internal"), f"invalid visibility on {f.get('fact_id')}")
        fail(errors, f.get("approved") is (f.get("visibility") == "guest"), f"approved must mark synthetic publication eligibility and match visibility on {f.get('fact_id')}")
        fail(errors, f.get("synthetic") is True, f"active fact is not marked synthetic: {f.get('fact_id')}")
        fail(errors, f.get("status") in ("confirmed","unknown","needs_confirmation"), f"lifecycle state leaked into active corpus: {f.get('fact_id')}")
        fail(errors, f.get("valid_from") <= f.get("valid_to"), f"invalid validity interval on {f.get('fact_id')}")
        fail(errors, bool(f.get("source_refs")), f"no source refs on {f.get('fact_id')}")
        for ref in f.get("source_refs", []):
            src = source_by_id.get(ref.get("source_id"))
            fail(errors, src is not None, f"missing source {ref.get('source_id')} for {f.get('fact_id')}")
            if src:
                fail(errors, src.get("hotel_id") == f.get("hotel_id"), f"cross-property source reference on {f.get('fact_id')}")
                fail(errors, src.get("version") == ref.get("version"), f"source version mismatch on {f.get('fact_id')}")
                fail(errors, src.get("section") == ref.get("section"), f"source section mismatch on {f.get('fact_id')}")
                fail(errors, src.get("guest_approved") is (f.get("visibility") == "guest"), f"source approval scope mismatch on {f.get('fact_id')}")
                doc = ROOT / src["path"]
                fail(errors, doc.exists(), f"source document missing: {src['path']}")
                if doc.exists():
                    fail(errors, f"[{f['fact_id']}]" in doc.read_text(encoding="utf-8"), f"fact not represented in source text: {f['fact_id']}")
                    if f.get("visibility")=="guest":
                        fail(errors, "INTERNAL-ONLY" not in doc.read_text(encoding="utf-8"), f"guest fact points to internal-only source file: {f['fact_id']}")
        if isinstance(f.get("value"), str):
            if "example.invalid" in f["value"] or "example.com" in f["value"]:
                fail(errors, "NONFUNCTIONAL" in f["value"], f"sample URL lacks nonfunctional label: {f['fact_id']}")
    for hid in HOTEL_IDS:
        topics = {f["topic"] for f in facts if f["hotel_id"] == hid}
        fail(errors, REQUIRED_TOPICS <= topics, f"{hid} misses required support coverage: {sorted(REQUIRED_TOPICS-topics)}")
    prop = {p["hotel_id"]: p for p in properties["properties"]}
    fail(errors, set(prop) == HOTEL_IDS, "property catalog does not match hotel IDs")
    room_ids = {}
    for hid, rooms in properties["room_types"].items():
        fail(errors, hid in HOTEL_IDS, f"unknown room catalog property {hid}")
        ids = {r["room_type_id"] for r in rooms}
        room_ids[hid] = ids
        fail(errors, 3 <= len(rooms) <= 4, f"expected 3-4 room types for {hid}")
        for room in rooms:
            fail(errors, room["quantity_reference"] > 0, f"nonpositive reference room quantity {room['room_type_id']}")
            fail(errors, room["max_occupancy"] > 0 and bool(room["beds"]), f"missing capacity/beds in {room['room_type_id']}")
            fail(errors, bool(room.get("age_and_sharing")) and bool(room.get("guardian")), f"missing child/guardian rule in {room['room_type_id']}")
            fail(errors, room.get("source_refs") and all(x["source_id"] in source_by_id for x in room["source_refs"]), f"room missing catalog source refs: {room['room_type_id']}")
            rule=room.get("age_policy",{})
            fail(errors, rule.get("guardian_required_below_age_exclusive")==18 and rule.get("guardian_min_age_inclusive")==18, f"guardian age boundary missing for {room['room_type_id']}")
            fail(errors, rule.get("child_rate_age_max_exclusive")==12, f"child pricing age boundary missing for {room['room_type_id']}")
            age_cases={x.get("age_years"):x for x in rule.get("boundary_cases",[])}
            fail(errors, {0,5,6,11,12,17,18} <= set(age_cases), f"age boundary examples incomplete for {room['room_type_id']}")
            if age_cases:
                fail(errors, all(age_cases[a].get("guardian_required") is (a<18) for a in (0,5,6,11,12,17,18)), f"guardian boundary outcomes inconsistent for {room['room_type_id']}")
                fail(errors, age_cases[12]["guest_class"]=="adult_rate_age" and age_cases[17]["guardian_required"] is True and age_cases[18]["guardian_required"] is False, f"child pricing/minor guardian rules conflated for {room['room_type_id']}")
            fail(errors, room.get("children_count_toward_max_occupancy") is True and room.get("sleeping_positions",0)==sum(b.get("count",0)*b.get("occupant_capacity",0) for b in room.get("beds",[])), f"occupancy/sleeping-position rules missing for {room['room_type_id']}")
    rates = properties["room_rates_reference"]
    fail(errors, len(rates) == 9, "expected 3 reference rate rows per hotel")
    for rate in rates:
        fail(errors, rate["hotel_id"] in HOTEL_IDS and rate["room_type_id"] in room_ids.get(rate["hotel_id"], set()), f"rate points to unknown room {rate}")
        fail(errors, isinstance(rate["amount"], int) and rate["amount"] > 0 and rate["currency"] == "VND", f"invalid VND reference rate {rate}")
        fail(errors, rate.get("price_basis") and rate["tax"] and rate["status"] == "reference_only" and not rate["is_quote"] and not rate["is_live_availability"], f"reference rate lacks basis/status caveats {rate}")
        fail(errors, rate.get("source_refs") and all(x["source_id"] in source_by_id for x in rate["source_refs"]), f"rate missing catalog source refs {rate.get('rate_id')}")
        basis=rate.get("price_basis",{})
        fail(errors, basis.get("unit")=="room_night" and isinstance(basis.get("included_occupants"),int) and basis.get("included_occupants")==basis.get("included_adults",-1)+basis.get("included_children",-1), f"rate inclusion basis is not calculator-readable {rate.get('rate_id')}")
        fail(errors, rate.get("child_charge_amount") is None and rate.get("child_charge_status"), f"unknown child charge must remain typed unknown {rate.get('rate_id')}")
        fail(errors, "do not add that venue's reference breakfast price" in rate.get("inclusion_scope",""), f"breakfast inclusion scope could double-count venue price {rate.get('rate_id')}")
    for hid, venues in properties["venues"].items():
        fail(errors, hid in HOTEL_IDS and len(venues)==8, f"expected 8 authored venues for {hid}")
        cost_states=set()
        for v in venues:
            fail(errors, v.get("source_refs") and all(x["source_id"] in source_by_id for x in v["source_refs"]), f"venue missing catalog source refs {v.get('venue_id')}")
            fail(errors, v["timezone"] == "Asia/Ho_Chi_Minh" and bool(re.fullmatch(r"\d\d:\d\d-\d\d:\d\d",v["window"])), f"invalid venue hours/timezone {v['venue_id']}")
            fail(errors, v["duration_minutes"] > 0 and v["seats_reference"] > 0 and bool(v["capacity_excludes"]), f"incomplete venue capacity {v['venue_id']}")
            cost=v.get("reference_cost",{})
            cost_states.add(cost.get("status"))
            fail(errors, cost.get("currency")=="VND" and cost.get("amount_unit")=="whole VND" and cost.get("basis") in {"per_person_per_meal","per_person_per_order","per_person_per_visit","per_item"}, f"invalid venue cost basis/currency {v['venue_id']}")
            fail(errors, cost.get("reference_date")=="2026-10-22" and cost.get("is_quote") is False and cost.get("synthetic") is True and bool(cost.get("inclusions")), f"venue cost missing synthetic reference metadata {v['venue_id']}")
            if cost.get("status")=="unknown":
                fail(errors, cost.get("amount") is None, f"unknown venue price must be null {v['venue_id']}")
            elif cost.get("status")=="known_reference":
                fail(errors, isinstance(cost.get("amount"),int) and cost["amount"]>=0, f"known venue price must be a whole nonnegative VND amount {v['venue_id']}")
                if cost.get("amount")==0:
                    text=" ".join(cost["inclusions"]).lower()
                    fail(errors, "miễn phí" in text or "không thu phí" in text, f"zero venue price lacks explicit free admission wording {v['venue_id']}")
            else:
                fail(errors, False, f"invalid venue cost status {v['venue_id']}")
        fail(errors, {"known_reference","unknown"}<=cost_states, f"venue cost references need known and unknown cases for {hid}")
        fail(errors, any(v["reference_cost"].get("amount")==0 for v in venues), f"each hotel needs an explicit free venue reference for {hid}")
        fail(errors, any(isinstance(v["reference_cost"].get("amount"),int) and v["reference_cost"]["amount"]>0 for v in venues), f"each hotel needs a paid venue reference for {hid}")
    for hid, providers in properties["service_providers"].items():
        fail(errors, hid in HOTEL_IDS and len(providers)==4, f"expected 4 authored sample providers for {hid}")
        for provider in providers:
            fail(errors, provider.get("source_refs") and all(x["source_id"] in source_by_id for x in provider["source_refs"]), f"provider missing catalog source refs {provider.get('provider_id')}")
            fail(errors, provider.get("timezone")=="Asia/Ho_Chi_Minh" and provider.get("fee_currency")=="VND" and bool(provider.get("fee_basis")), f"provider schedule/fee basis incomplete {provider.get('provider_id')}")
            fail(errors, provider.get("fee_amount") is not None or "unknown" in provider.get("status",""), f"provider unknown fee improperly omitted {provider.get('provider_id')}")
    for hid, routes in properties["routes"].items():
        fail(errors, hid in HOTEL_IDS and len(routes)==19, f"expected 19 authored route legs for {hid}")
        for route in routes:
            fail(errors, route.get("source_refs") and all(x["source_id"] in source_by_id for x in route["source_refs"]), f"route missing catalog source refs {route.get('route_id')}")
            fail(errors, route["duration_minutes"] > 0 and route["buffer_minutes"] >= 0 and route["legs"], f"incomplete route timing/legs {route['route_id']}")
            fail(errors, "seats_excluding_driver" in route and "luggage" in route and "child_seat" in route and "accessible" in route, f"route lacks seats/luggage/child/access notes {route['route_id']}")
            fail(errors, isinstance(route["fare_reference_vnd"],int) and route["fare_reference_vnd"] >= 0, f"invalid route fare reference {route['route_id']}")
        route_by_id={r["route_id"]:r for r in routes}
        hotel_name=prop[hid]["name"]
        for venue in properties["venues"].get(hid,[]):
            out_id=f"{hid}-VENUE-{venue['venue_id']}-OUT"
            return_id=f"{hid}-VENUE-{venue['venue_id']}-RETURN"
            out=route_by_id.get(out_id); back=route_by_id.get(return_id)
            fail(errors, out is not None and back is not None, f"venue missing explicit outbound/return leg: {hid} {venue['venue_id']}")
            if out and back:
                fail(errors, out.get("from")==hotel_name and out.get("to")==venue["name"], f"outbound route endpoints mismatch {out_id}")
                fail(errors, back.get("from")==venue["name"] and back.get("to")==hotel_name, f"return route endpoints mismatch {return_id}")
    for src in sources:
        if src["source_id"].endswith("-CATALOG"):
            doc=ROOT/src["path"]
            fail(errors, doc.exists(), f"catalog source missing: {src['path']}")
            if doc.exists():
                body=doc.read_text(encoding="utf-8")
                hid=src["hotel_id"]
                for collection in (properties["room_types"].get(hid,[]),[r for r in rates if r["hotel_id"]==hid],properties["venues"].get(hid,[]),properties["service_providers"].get(hid,[]),properties["routes"].get(hid,[])):
                    for entity in collection:
                        entity_id=entity.get("room_type_id",entity.get("rate_id",entity.get("venue_id",entity.get("provider_id",entity.get("route_id")))))
                        fail(errors, f"[{entity_id}]" in body, f"catalog entity missing from human-readable source: {entity_id}")
        elif src["section"]=="Ghi chú nội bộ":
            doc=ROOT/src["path"]
            fail(errors, doc.exists(), f"internal source missing: {src['path']}")
            guest_path=ROOT/f"sources/guest/{src['hotel_id'].lower()}.txt"
            if doc.exists() and guest_path.exists():
                internal_fact_ids=[f["fact_id"] for f in facts if f["hotel_id"]==src["hotel_id"] and f["visibility"]=="internal"]
                guest_text=guest_path.read_text(encoding="utf-8")
                fail(errors, not any(fid in guest_text for fid in internal_fact_ids), f"internal fact leaked into guest source document for {src['hotel_id']}")
    # Deliberate differences are required to exercise strict hotel isolation.
    by_key = {(f["hotel_id"],f["subject"],f["field"]): f for f in facts}
    fail(errors, by_key[("HTL-CITY01","policy","pets")]["value"] != by_key[("HTL-BEACH02","policy","pets")]["value"], "pet policies must deliberately differ by property")
    fail(errors, by_key[("HTL-CITY01","amenity","pool")]["value"] != by_key[("HTL-BEACH02","amenity","pool")]["value"], "pool availability must differ by property")
    fail(errors, by_key[("HTL-CITY01","dining","breakfast")]["value"] != by_key[("HTL-RETREAT03","dining","breakfast")]["value"], "breakfast policies must differ by property")
    lifecycle_ids = set()
    for case in lifecycle["scenarios"]:
        records = case.get("records", [case.get("record", {})])
        for record in records:
            lifecycle_ids.add(record.get("fact_id"))
    fail(errors, not (set(fact_ids) & lifecycle_ids), "lifecycle fixture IDs overlap active fact IDs")
    fail(errors, "scenarios" in lifecycle and all(x["hotel_id"] in HOTEL_IDS for x in lifecycle["scenarios"]), "invalid lifecycle scenario property")
    fail(errors, manifest["active_fact_count"] == len(facts) and manifest["source_count"] == len(sources), "manifest counts are stale")
    fail(errors, set(manifest.get("languages",[]))=={"vi","en"}, "manifest language scope is inaccurate")
    fail(errors, manifest["properties"] and {x["hotel_id"] for x in manifest["properties"]} == HOTEL_IDS, "manifest property set mismatch")
    if errors:
        print("Knowledge pack validation failed:")
        for error in errors:
            print("-", error)
        return 1
    print(f"OK: {len(facts)} active facts across {len(HOTEL_IDS)} hotels; {len(sources)} source records; {len(lifecycle['scenarios'])} isolated lifecycle scenarios.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
