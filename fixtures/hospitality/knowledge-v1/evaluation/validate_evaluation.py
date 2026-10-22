#!/usr/bin/env python3
"""Validate hospitality evaluation fixture structure and source grounding."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def values_by_id(records: Any, key: str, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        errors.append(f"{label} must be a JSON array")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get(key), str):
            errors.append(f"{label}[{index}] must be an object with string {key}")
            continue
        identifier = record[key]
        if identifier in result:
            errors.append(f"duplicate {label} identifier: {identifier}")
        result[identifier] = record
    return result


def load_cases(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"cannot read cases file {path}: {exc}")
        return cases
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(case, dict):
            errors.append(f"{path}:{number}: each JSONL line must be an object")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{path}:{number}: missing non-empty case_id")
        elif case_id in seen:
            errors.append(f"{path}:{number}: duplicate case_id {case_id}")
        else:
            seen.add(case_id)
        case["_line"] = number
        cases.append(case)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, help="knowledge-v1 directory (defaults to parent of evaluation)")
    parser.add_argument("--cases", type=Path, help="JSONL cases file (defaults to evaluation/cases.jsonl)")
    parser.add_argument("--media-manifest", type=Path, help="media manifest JSON (auto-discovered when omitted)")
    args = parser.parse_args()

    evaluation_dir = Path(__file__).resolve().parent
    root = (args.fixture_root or evaluation_dir.parent).resolve()
    cases_path = (args.cases or evaluation_dir / "cases.jsonl").resolve()
    errors: list[str] = []

    try:
        facts = values_by_id(read_json(root / "facts.json"), "fact_id", "facts", errors)
        sources = values_by_id(read_json(root / "sources.json"), "source_id", "sources", errors)
        properties = read_json(root / "properties.json")
        lifecycle_data = read_json(root / "lifecycle_scenarios.json")
    except OSError as exc:
        print(f"ERROR: cannot load core knowledge inputs: {exc}", file=sys.stderr)
        return 2

    media_path = args.media_manifest
    if media_path is None:
        standard_manifest = root / "media" / "media_manifest.json"
        matches = [standard_manifest] if standard_manifest.is_file() else []
        matches += list(root.glob("media/**/manifest.json"))
        media_path = matches[0] if matches else None
    media: dict[str, dict[str, Any]] = {}
    rejected_media: dict[str, dict[str, Any]] = {}
    if media_path is not None:
        try:
            manifest = read_json(media_path)
            records = manifest.get("media_records", []) if isinstance(manifest, dict) else manifest
            media = values_by_id(records, "media_id", "media_records", errors)
            rejects = manifest.get("expected_reject", []) if isinstance(manifest, dict) else []
            rejected_media = values_by_id(rejects, "media_id", "expected_reject", errors)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot load media manifest {media_path}: {exc}")

    cases = load_cases(cases_path, errors)
    lifecycle = values_by_id(
        lifecycle_data.get("scenarios", []) if isinstance(lifecycle_data, dict) else [],
        "scenario_id", "lifecycle scenarios", errors
    )
    hotel_ids = {fact.get("hotel_id") for fact in facts.values()}
    hotel_ids.discard(None)
    coverage: dict[str, int] = {}
    language_coverage: set[str] = set()
    categories: dict[str, int] = {}

    for case in cases:
        line = case.get("_line", "?")
        prefix = f"{cases_path}:{line}"
        hotel_id = case.get("hotel_id")
        if hotel_id not in hotel_ids:
            errors.append(f"{prefix}: unknown hotel_id {hotel_id!r}")
        category = case.get("category")
        if isinstance(category, str):
            categories[category] = categories.get(category, 0) + 1
        languages = case.get("languages", [])
        if not isinstance(languages, list) or not all(isinstance(lang, str) for lang in languages):
            errors.append(f"{prefix}: languages must be an array of strings")
        else:
            language_coverage.update(languages)
        turns = case.get("turns")
        if not isinstance(turns, list) or not turns or any(
            not isinstance(turn, dict) or turn.get("role") not in {"user", "assistant", "tool"}
            or not isinstance(turn.get("content"), str)
            for turn in turns
        ):
            errors.append(f"{prefix}: turns must be non-empty role/content objects")
        if not isinstance(case.get("expected_outcome"), dict) or not case["expected_outcome"].get("type"):
            errors.append(f"{prefix}: expected_outcome must be an object with a type")
        if case.get("status") not in {"oracle-authored", "reviewed"}:
            errors.append(f"{prefix}: status must identify an authored oracle, not imply a system pass")
        array_fields = (
            "languages", "required_fact_ids", "source_evidence_refs", "expected_constraints",
            "state_delta", "tool_expectations", "clarification_expectations", "unknowns",
            "forbidden_claims", "catalog_expectations", "media_expectations", "lifecycle_scenario_ids",
            "timeline_expectations",
        )
        for field in array_fields:
            if not isinstance(case.get(field), list):
                errors.append(f"{prefix}: {field} must be an array")
        for delta in case.get("state_delta", []) if isinstance(case.get("state_delta"), list) else []:
            if not isinstance(delta, dict) or not isinstance(delta.get("operation"), str):
                errors.append(f"{prefix}: each non-empty state_delta entry must be an operation object")
            elif any(isinstance(value, str) and len(value) == 1 for value in delta.values()):
                errors.append(f"{prefix}: state_delta contains a stray single-character value")
        outcome_type = case.get("expected_outcome", {}).get("type") if isinstance(case.get("expected_outcome"), dict) else None
        if isinstance(outcome_type, str) and outcome_type.lower() in {"pass", "passed", "success", "completed"}:
            errors.append(f"{prefix}: expected_outcome.type must describe the oracle action, not a system result")

        required_ids = case.get("required_fact_ids", [])
        if not isinstance(required_ids, list):
            errors.append(f"{prefix}: required_fact_ids must be an array")
            required_ids = []
        referenced_facts: set[str] = set()
        for fact_id in required_ids:
            fact = facts.get(fact_id)
            if fact is None:
                errors.append(f"{prefix}: unknown required fact_id {fact_id!r}")
                continue
            referenced_facts.add(fact_id)
            if fact.get("hotel_id") != hotel_id:
                errors.append(f"{prefix}: cross-hotel fact reference {fact_id} belongs to {fact.get('hotel_id')}")
            if fact.get("approved") is not True or fact.get("visibility") != "guest":
                errors.append(f"{prefix}: required fact {fact_id} is not approved guest-facing evidence")
            coverage[fact_id] = coverage.get(fact_id, 0) + 1

        expected_facts = case.get("expected_facts", {})
        if not isinstance(expected_facts, dict):
            errors.append(f"{prefix}: expected_facts must map fact IDs to typed values")
        else:
            for fact_id, expected_value in expected_facts.items():
                fact = facts.get(fact_id)
                if fact is None:
                    errors.append(f"{prefix}: expected value cites unknown fact_id {fact_id}")
                elif fact.get("hotel_id") != hotel_id:
                    errors.append(f"{prefix}: expected value cites cross-hotel fact {fact_id}")
                elif fact.get("value") != expected_value:
                    errors.append(f"{prefix}: expected value for {fact_id} does not match authored fact value")
                if fact_id not in referenced_facts:
                    errors.append(f"{prefix}: expected_facts entry {fact_id} is absent from required_fact_ids")

        evidence = case.get("source_evidence_refs", [])
        if not isinstance(evidence, list):
            errors.append(f"{prefix}: source_evidence_refs must be an array")
            evidence = []
        for source_id in evidence:
            source = sources.get(source_id)
            if source is None:
                errors.append(f"{prefix}: unknown source_id {source_id!r}")
            elif source.get("hotel_id") not in {hotel_id, None}:
                errors.append(f"{prefix}: cross-hotel source reference {source_id}")
            elif source.get("guest_approved") is False:
                errors.append(f"{prefix}: source reference {source_id} is not guest-approved evidence")

        catalog_expectations = case.get("catalog_expectations", [])
        if not isinstance(catalog_expectations, list):
            errors.append(f"{prefix}: catalog_expectations must be an array")
            catalog_expectations = []
        for expectation in catalog_expectations:
            if not isinstance(expectation, dict):
                errors.append(f"{prefix}: catalog expectation must be an object")
                continue
            collection = expectation.get("collection")
            key = expectation.get("key")
            key_field = expectation.get("key_field")
            expected = expectation.get("expected")
            if collection in {"room_rates_reference"}:
                candidates = properties.get(collection, [])
                matches = [item for item in candidates if item.get(key_field) == key]
            elif collection in {"room_types", "routes", "venues"}:
                candidates = properties.get(collection, {}).get(hotel_id, [])
                matches = [item for item in candidates if item.get(key_field) == key]
            else:
                errors.append(f"{prefix}: unsupported catalog collection {collection!r}")
                continue
            if len(matches) != 1:
                errors.append(f"{prefix}: catalog reference {collection}/{key} is missing or ambiguous")
            elif matches[0].get("hotel_id", hotel_id) != hotel_id:
                errors.append(f"{prefix}: cross-hotel catalog reference {collection}/{key}")
            elif not isinstance(expected, dict) or any(matches[0].get(field) != value for field, value in expected.items()):
                errors.append(f"{prefix}: expected catalog values for {collection}/{key} do not match properties.json")

        timelines = case.get("timeline_expectations", [])
        if not isinstance(timelines, list):
            errors.append(f"{prefix}: timeline_expectations must be an array")
            timelines = []
        for timeline in timelines:
            if not isinstance(timeline, dict):
                errors.append(f"{prefix}: timeline expectation must be an object")
                continue
            def minutes(clock: Any) -> int:
                parsed = datetime.strptime(str(clock), "%H:%M")
                return parsed.hour * 60 + parsed.minute

            try:
                property_timezone = next(
                    item.get("timezone") for item in properties.get("properties", [])
                    if item.get("hotel_id") == hotel_id
                )
                if timeline.get("timezone") != property_timezone:
                    errors.append(f"{prefix}: timeline timezone does not match property timezone")
                rest = timeline["rest"]
                if minutes(rest["end"]) <= minutes(rest["start"]):
                    errors.append(f"{prefix}: timeline rest block is empty or reversed")
                outbound = timeline["outbound"]
                expected_ready = minutes(outbound["departure"]) + int(outbound["travel_minutes"]) + int(outbound["buffer_minutes"])
                if expected_ready != minutes(outbound["ready_at"]):
                    errors.append(f"{prefix}: outbound travel plus buffer does not match ready_at")
                visit = timeline["visit"]
                if minutes(visit["start"]) != minutes(outbound["ready_at"]):
                    errors.append(f"{prefix}: visit start does not follow outbound travel and buffer")
                if minutes(visit["end"]) - minutes(visit["start"]) != int(timeline["visit_duration_minutes"]):
                    errors.append(f"{prefix}: visit duration does not match the authored venue duration")
                return_leg = timeline["return"]
                if minutes(return_leg["departure"]) != minutes(visit["end"]):
                    errors.append(f"{prefix}: return departure does not follow the visit")
                expected_home = minutes(return_leg["departure"]) + int(return_leg["travel_minutes"]) + int(return_leg["buffer_minutes"])
                if expected_home != minutes(return_leg["ready_at"]):
                    errors.append(f"{prefix}: return travel plus buffer does not match ready_at")
                window_start, window_end = (minutes(value) for value in timeline["venue_window"].split("-", 1))
                if minutes(visit["start"]) < window_start or minutes(visit["end"]) > window_end:
                    errors.append(f"{prefix}: visit falls outside the cited venue window")
                venue_id = timeline.get("venue_id")
                if venue_id:
                    venue = next(
                        (item for item in properties.get("venues", {}).get(hotel_id, []) if item.get("venue_id") == venue_id),
                        None,
                    )
                    if venue is None:
                        errors.append(f"{prefix}: timeline references unknown venue {venue_id}")
                    elif timeline.get("weekday") in venue.get("closed_days", []):
                        errors.append(f"{prefix}: itinerary visit is on the venue's authored closed day")
            except (KeyError, TypeError, ValueError, StopIteration):
                errors.append(f"{prefix}: malformed timeline expectation or clock value")

        lifecycle_ids = case.get("lifecycle_scenario_ids", [])
        if not isinstance(lifecycle_ids, list):
            errors.append(f"{prefix}: lifecycle_scenario_ids must be an array")
            lifecycle_ids = []
        for scenario_id in lifecycle_ids:
            scenario = lifecycle.get(scenario_id)
            if scenario is None:
                errors.append(f"{prefix}: unknown lifecycle scenario_id {scenario_id!r}")
            elif scenario.get("hotel_id") != hotel_id:
                errors.append(f"{prefix}: cross-hotel lifecycle scenario {scenario_id}")
        if lifecycle_ids and case.get("state_delta") in (None, [], {}):
            errors.append(f"{prefix}: lifecycle case must specify its expected state_delta")

        media_expectations = case.get("media_expectations", [])
        if not isinstance(media_expectations, list):
            errors.append(f"{prefix}: media_expectations must be an array")
            media_expectations = []
        for expectation in media_expectations:
            if not isinstance(expectation, dict):
                errors.append(f"{prefix}: media expectation must be an object")
                continue
            media_id = expectation.get("media_id")
            if expectation.get("rejected") is True:
                record = rejected_media.get(media_id)
                if record is None:
                    errors.append(f"{prefix}: unknown/unapproved media rejection fixture {media_id!r}")
                    continue
                if record.get("approved_for_guest") is not False:
                    errors.append(f"{prefix}: rejection fixture {media_id} is not marked unapproved")
                asset = root / "media" / str(record.get("asset_path", ""))
                if record.get("asset_path") and not asset.is_file():
                    errors.append(f"{prefix}: rejected media fixture missing: {asset}")
                continue
            record = media.get(media_id)
            if record is None:
                errors.append(f"{prefix}: unknown manifest media_id {media_id!r}")
                continue
            if record.get("hotel_id") != hotel_id:
                errors.append(f"{prefix}: cross-hotel media reference {media_id}")
            asset = root / "media" / str(record.get("asset_path", ""))
            if record.get("asset_path") and not asset.is_file():
                errors.append(f"{prefix}: media asset missing: {asset}")
            duration = record.get("duration_seconds")
            for segment in expectation.get("segments", []):
                try:
                    start, end = float(segment["start_s"]), float(segment["end_s"])
                except (KeyError, TypeError, ValueError):
                    errors.append(f"{prefix}: media segment needs numeric start_s/end_s")
                    continue
                if start < 0 or end <= start or (isinstance(duration, (int, float)) and end > duration):
                    errors.append(f"{prefix}: invalid time segment {media_id} {start:g}-{end:g}s")
                if isinstance(duration, (int, float)):
                    known_scenes = [
                        scene for scene in record.get("scenes", [])
                        if scene.get("start_s") == start and scene.get("end_s") == end
                    ]
                    if not known_scenes:
                        errors.append(f"{prefix}: video segment {media_id} {start:g}-{end:g}s does not match a manifest scene")
                    elif not set(segment.get("expected_visible_labels", [])).issubset(set(known_scenes[0].get("expected_visible_labels", []))):
                        errors.append(f"{prefix}: expected video labels are not in the referenced manifest scene")
            image_labels = expectation.get("expected_visible_labels", [])
            if image_labels and not set(image_labels).issubset(set(record.get("expected_visible_labels", []))):
                errors.append(f"{prefix}: expected image labels are not in the referenced manifest record")

    expected_hotels = {"HTL-CITY01", "HTL-BEACH02", "HTL-RETREAT03"}
    if not expected_hotels.issubset(hotel_ids):
        errors.append(f"core facts missing hotel namespaces: {sorted(expected_hotels - hotel_ids)}")
    if not expected_hotels.issubset({case.get("hotel_id") for case in cases}):
        errors.append("evaluation cases do not cover all three hotels")
    for code in {"vi", "en", "fr", "ja", "ar", "hi"}:
        if code not in language_coverage:
            errors.append(f"evaluation cases missing requested language coverage: {code}")
    if len(cases) < 150:
        errors.append(f"only {len(cases)} cases; target is approximately 150-200 meaningful cases")
    if len(media) == 0:
        errors.append("media manifest was not found or contains no media records")

    print(f"Cases: {len(cases)}; grounded fact IDs: {len(coverage)}; categories: {len(categories)}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Evaluation fixtures are structurally consistent with the authored sources.")
    print("This result does not indicate that a guest-facing system has been executed or passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
