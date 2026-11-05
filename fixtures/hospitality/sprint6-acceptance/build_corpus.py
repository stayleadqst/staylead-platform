"""Build a temporary Sprint 6 synthetic corpus using the normal pack parser.

This acceptance-only builder copies the existing knowledge-v1 pack into
``/private/tmp/staylead-sprint6-corpus/knowledge-v1``, adds the separately
authored Sprint 6 URL source/fact, and validates the result through the normal
``parse_fixture_pack`` trust boundary. It never edits the baseline pack, starts
a server, opens a database, makes an HTTP request, or invokes a model.

Run from the repository root::

    PYTHONPATH=apps/api/src apps/api/.venv/bin/python \
      fixtures/hospitality/sprint6-acceptance/build_corpus.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
BASELINE = REPO / "fixtures/hospitality/knowledge-v1"
OVERLAY = Path(__file__).resolve().parent
OUTPUT = Path("/private/tmp/staylead-sprint6-corpus/knowledge-v1")
SOURCE_ID = "SRC-HTL-CITY01-S6-URL"
FACT_ID = "F-HTL-CITY01-S6-URL-001"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build() -> dict[str, Any]:
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to replace existing temporary corpus: {OUTPUT}")
    shutil.copytree(BASELINE, OUTPUT, copy_function=shutil.copy2)
    source = _read(OVERLAY / "source.json")
    fact = _read(OVERLAY / "fact.json")
    if source["source_id"] != SOURCE_ID or fact["fact_id"] != FACT_ID:
        raise SystemExit("S6 overlay IDs do not match the pinned acceptance IDs.")
    if not source["synthetic"] or not source["guest_approved"] or fact["approved"] is not True:
        raise SystemExit("S6 overlay must remain an explicitly synthetic guest acceptance fixture.")
    (OUTPUT / source["path"]).write_bytes((OVERLAY / "source.txt").read_bytes())

    sources = _read(OUTPUT / "sources.json")
    facts = _read(OUTPUT / "facts.json")
    if any(item.get("source_id") == SOURCE_ID for item in sources):
        raise SystemExit("S6 source ID already exists in the copied corpus.")
    if any(item.get("fact_id") == FACT_ID for item in facts):
        raise SystemExit("S6 fact ID already exists in the copied corpus.")
    sources.append(source)
    facts.append(fact)
    _write(OUTPUT / "sources.json", sources)
    _write(OUTPUT / "facts.json", facts)

    pack_manifest = _read(OUTPUT / "manifest.json")
    pack_manifest["source_count"] += 1
    pack_manifest["active_fact_count"] += 1
    for row in pack_manifest["properties"]:
        if row["hotel_id"] == "HTL-CITY01":
            row["active_fact_count"] += 1
    pack_manifest["files"].append("sources/guest/sprint6-acceptance.txt")
    pack_manifest["sprint6_acceptance_overlay"] = {
        "source_id": SOURCE_ID,
        "fact_id": FACT_ID,
        "classification": "synthetic acceptance-only; not real hotel/operator approval",
    }
    _write(OUTPUT / "manifest.json", pack_manifest)

    from staylead_platform.domains.hospitality.registration.fixture_pack import (
        parse_fixture_pack,
    )

    imported = parse_fixture_pack(OUTPUT, reference_date=date(2026, 12, 1))
    city = next(item for item in imported if item.hotel_id == "HTL-CITY01")
    guest_ids = {item["fact_id"] for item in city.facts}
    if FACT_ID not in guest_ids or "F-HTL-CITY01-038" in guest_ids or "F-HTL-CITY01-101" in guest_ids:
        raise SystemExit("Normal importer boundary failed to include the S6 URL or exclude internal URLs.")
    overlay_source = next(item for item in city.sources if item["source_id"] == SOURCE_ID)
    source_path = OUTPUT / overlay_source["path"]
    return {
        "result": "passed",
        "validation": "staylead_platform.domains.hospitality.registration.fixture_pack.parse_fixture_pack",
        "server_started": False,
        "database_opened": False,
        "provider_calls": 0,
        "external_network_calls": 0,
        "baseline_modified": False,
        "baseline_manifest_sha256": _sha256(BASELINE / "manifest.json"),
        "baseline_source_registry_sha256": _sha256(BASELINE / "sources.json"),
        "baseline_guest_source_document_sha256": _sha256(BASELINE / "sources/guest/htl-city01.txt"),
        "baseline_fact_corpus_sha256": _sha256(BASELINE / "facts.json"),
        "overlay": {
            "source_id": SOURCE_ID,
            "fact_id": FACT_ID,
            "url": fact["value"],
            "synthetic": True,
            "real_hotel_or_operator_approval": False,
            "source_sha256": _sha256(source_path),
            "source_record_sha256": _sha256(OUTPUT / "sources.json"),
            "guest_source_document_sha256": _sha256(OUTPUT / "sources/guest/htl-city01.txt"),
            "fact_corpus_sha256": _sha256(OUTPUT / "facts.json"),
            "manifest_sha256": _sha256(OUTPUT / "manifest.json"),
        },
        "internal_url_facts_excluded": ["F-HTL-CITY01-038", "F-HTL-CITY01-101"],
        "imported_city_guest_fact_count": len(city.facts),
        "output_root": str(OUTPUT),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
