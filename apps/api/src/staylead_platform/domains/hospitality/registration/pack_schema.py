"""Strict validation for an immutable, local Hospitality knowledge pack v1."""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

MAX_TOTAL = 64 * 1024 * 1024
MAX_FACTS = 400
LIMITS = {"image": 5 * 1024 * 1024, "video": 20 * 1024 * 1024, "captions": 256 * 1024}
MIMES = {"image": "image/png", "video": "video/mp4", "captions": "text/vtt"}
TOP_KEYS = {"format", "schema_version", "pack_id", "pack_version", "hotel", "sources", "facts", "media"}
FORBIDDEN = {"expected_visible_labels", "oracle", "expected_labels"}


class PackValidationError(ValueError):
    pass


def _reject_oracle(value: Any) -> None:
    if isinstance(value, dict):
        if FORBIDDEN.intersection(value):
            raise PackValidationError("Evaluation oracle fields are not allowed in serving packs.")
        for item in value.values():
            _reject_oracle(item)
    elif isinstance(value, list):
        for item in value:
            _reject_oracle(item)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PackValidationError("Manifest contains a value outside canonical JSON.") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _required(obj: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    if not isinstance(obj, dict) or any(k not in obj or obj[k] is None for k in keys):
        raise PackValidationError(f"{label} is missing required fields.")


def _only(obj: dict[str, Any], keys: set[str], label: str) -> None:
    if not isinstance(obj, dict) or set(obj) - keys:
        raise PackValidationError(f"{label} contains unsupported fields.")


def _valid_date_range(start: Any, end: Any, label: str) -> None:
    try:
        parsed_start, parsed_end = date.fromisoformat(start), date.fromisoformat(end)
        if (parsed_start.isoformat() != start or parsed_end.isoformat() != end
                or parsed_start > parsed_end):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise PackValidationError(f"{label} validity bounds must be ISO dates in order.") from exc


def _parse_vtt(raw: bytes) -> tuple[tuple[float, float], ...]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackValidationError("WebVTT must be UTF-8.") from exc
    lines = text.splitlines()
    if not lines or lines[0].lstrip("\ufeff") != "WEBVTT":
        raise PackValidationError("WebVTT header is invalid.")
    if len(lines) < 2 or lines[1] != "":
        raise PackValidationError("WebVTT header must be followed by a blank separator line.")

    def timestamp(value: str) -> float:
        pieces = value.split(":")
        if len(pieces) not in {2, 3}:
            raise ValueError
        seconds = pieces[-1]
        if "." not in seconds:
            raise ValueError
        whole, millis = seconds.split(".", 1)
        if not whole.isdigit() or len(millis) != 3 or not millis.isdigit():
            raise ValueError
        minute = int(pieces[-2])
        if minute > 59:
            raise ValueError
        hour = int(pieces[0]) if len(pieces) == 3 else 0
        if len(pieces) == 3 and (len(pieces[0]) < 2 or not pieces[0].isdigit()):
            raise ValueError
        second = int(whole)
        if second > 59:
            raise ValueError
        return hour * 3600 + minute * 60 + second + int(millis) / 1000

    cues: list[tuple[float, float]] = []
    previous_end = -1.0
    index = 1
    timing = re.compile(r"^((?:\d{2,}:)?\d{2}:\d{2}\.\d{3})[ \t]+-->[ \t]+((?:\d{2,}:)?\d{2}:\d{2}\.\d{3})(?:[ \t]+.*)?$")
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line in {"NOTE", "STYLE", "REGION"} or line.startswith("NOTE "):
            raise PackValidationError("WebVTT does not accept unreviewed metadata blocks.")
        if "-->" not in line:
            index += 1  # optional cue identifier preceding the timing line
            if index >= len(lines):
                raise PackValidationError("WebVTT cue identifier has no timing line.")
            line = lines[index].strip()
        match = timing.fullmatch(line)
        if match is None:
            raise PackValidationError("WebVTT cue timing syntax is invalid.")
        try:
            start, end = timestamp(match.group(1)), timestamp(match.group(2))
        except ValueError as exc:
            raise PackValidationError("WebVTT cue timestamp is invalid.") from exc
        if start < previous_end or end <= start:
            raise PackValidationError("WebVTT cues must have ordered, positive time spans.")
        index += 1
        text_lines = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index])
            index += 1
        if not any(text_lines):
            raise PackValidationError("WebVTT cue text is required.")
        cues.append((start, end))
        previous_end = end
    if not cues:
        raise PackValidationError("WebVTT must contain at least one cue.")
    return tuple(cues)


def _safe_asset(root: Path, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise PackValidationError("Asset path must be a pack-relative POSIX path.")
    partpath = PurePosixPath(raw_path)
    if partpath.is_absolute() or any(part in {"", ".", ".."} for part in partpath.parts):
        raise PackValidationError("Asset path escapes the pack root.")
    current = root
    for part in partpath.parts:
        current = current / part
        if current.is_symlink():
            raise PackValidationError("Symlink assets are not allowed.")
    resolved = current.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file():
        raise PackValidationError("Asset path is outside the configured pack root.")
    return resolved


def _duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True, timeout=15,
        )
        duration = float(result.stdout.strip())
        if duration <= 0:
            raise ValueError
        return duration
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise PackValidationError("Video duration could not be verified with ffprobe.") from exc


def validate_pack(pack_root: str | Path) -> dict[str, Any]:
    root = Path(pack_root).resolve(strict=True)
    if not root.is_dir():
        raise PackValidationError("Pack root must be a directory.")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PackValidationError("Pack manifest is missing or symlinked.")
    try:
        if manifest_path.stat().st_size > MAX_TOTAL:
            raise PackValidationError("Manifest exceeds the total pack size limit.")
        with manifest_path.open("rb") as manifest_file:
            manifest_bytes = manifest_file.read(MAX_TOTAL + 1)
        if len(manifest_bytes) > MAX_TOTAL:
            raise PackValidationError("Manifest exceeds the total pack size limit.")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackValidationError("Manifest must be valid UTF-8 JSON.") from exc
    _reject_oracle(manifest)
    if not isinstance(manifest, dict) or set(manifest) != TOP_KEYS:
        raise PackValidationError("Manifest fields do not match pack schema v1.")
    stored_manifest = json.loads(_canonical(manifest))
    if (manifest["format"] != "staylead-hospitality-pack" or manifest["schema_version"] != 1
            or not manifest["pack_id"] or not manifest["pack_version"]):
        raise PackValidationError("Unsupported knowledge pack format or version.")
    hotel = manifest["hotel"]
    _only(hotel, {"hotel_id", "slug", "config_version", "name", "address", "description", "timezone", "currency"}, "Hotel")
    _required(hotel, ("hotel_id", "slug", "config_version", "name", "address", "timezone", "currency"), "Hotel")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,79}", hotel["hotel_id"]):
        raise PackValidationError("Hotel ID format is invalid.")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", hotel["slug"]):
        raise PackValidationError("Hotel slug format is invalid.")
    sources, facts, media = manifest["sources"], manifest["facts"], manifest["media"]
    if not all(isinstance(v, list) for v in (sources, facts, media)):
        raise PackValidationError("sources, facts and media must be arrays.")
    if not facts or len(facts) > MAX_FACTS:
        raise PackValidationError("A pack must contain 1–400 guest facts.")
    source_map: dict[str, dict[str, Any]] = {}
    for source in sources:
        _only(source, {"source_id", "version", "scope", "guest_approved", "valid_from", "valid_to", "title", "url", "provenance"}, "Source")
        _required(source, ("source_id", "version", "scope", "guest_approved", "valid_from", "valid_to", "title"), "Source")
        if source["source_id"] in source_map or source["scope"] != "hotel-specific" or source["guest_approved"] is not True:
            raise PackValidationError("Sources must be unique, hotel-scoped and guest-approved.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,119}", source["source_id"]):
            raise PackValidationError("Source ID format is invalid.")
        source["hotel_id"] = hotel["hotel_id"]
        _valid_date_range(source["valid_from"], source["valid_to"], "Source")
        source_map[source["source_id"]] = source
    fact_map: dict[str, dict[str, Any]] = {}
    fact_sources: dict[str, set[tuple[str, str]]] = {}
    for fact in facts:
        _only(fact, {"fact_id", "topic", "subject", "field", "value", "status", "valid_from", "valid_to", "source_refs", "section", "fact_version", "conditions", "content"}, "Fact")
        _required(fact, ("fact_id", "topic", "subject", "field", "status", "valid_from", "valid_to", "source_refs"), "Fact")
        if "value" not in fact:
            raise PackValidationError("Fact value is required; null explicitly represents unknown.")
        if fact["fact_id"] in fact_map or fact["status"] not in {"confirmed", "unknown", "needs_confirmation"}:
            raise PackValidationError("Fact IDs must be unique and status supported.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,119}", fact["fact_id"]):
            raise PackValidationError("Fact ID format is invalid.")
        _valid_date_range(fact["valid_from"], fact["valid_to"], "Fact")
        if not isinstance(fact["source_refs"], list) or not fact["source_refs"]:
            raise PackValidationError("Fact provenance or validity bounds are invalid.")
        if len(fact["source_refs"]) != 1:
            raise PackValidationError("Pack schema v1 supports exactly one source version per fact.")
        refs: set[tuple[str, str]] = set()
        for ref in fact["source_refs"]:
            _only(ref, {"source_id", "version"}, "Fact source reference")
            _required(ref, ("source_id", "version"), "Fact source reference")
            source = source_map.get(ref.get("source_id")) if isinstance(ref, dict) else None
            if not source or ref.get("version") != source["version"]:
                raise PackValidationError("Fact references a missing or mismatched source version.")
            refs.add((source["source_id"], source["version"]))
        effective_from = max([date.fromisoformat(fact["valid_from"]), *(
            date.fromisoformat(source_map[sid]["valid_from"]) for sid, _ in refs
        )]).isoformat()
        effective_to = min([date.fromisoformat(fact["valid_to"]), *(
            date.fromisoformat(source_map[sid]["valid_to"]) for sid, _ in refs
        )]).isoformat()
        if effective_from > effective_to:
            raise PackValidationError("Fact and approved source validity intervals do not overlap.")
        fact["valid_from"], fact["valid_to"] = effective_from, effective_to
        fact["hotel_id"] = hotel["hotel_id"]
        fact["approved"] = True
        fact["visibility"] = "guest"
        fact_map[fact["fact_id"]] = fact
        fact_sources[fact["fact_id"]] = refs
    total, assets, durations = len(manifest_bytes), {}, {}
    referenced_paths = {"manifest.json"}
    for item in media:
        _only(item, {"media_id", "kind", "asset_path", "mime_type", "sha256", "byte_size", "source_id", "source_version", "fact_ids", "caption", "alt_text", "guest_approved_whole_file", "start_seconds", "end_seconds", "captions_media_id"}, "Media")
        _required(item, ("media_id", "kind", "asset_path", "mime_type", "sha256", "byte_size", "source_id", "source_version", "fact_ids", "caption", "alt_text", "guest_approved_whole_file"), "Media")
        kind = item["kind"]
        if not isinstance(item["media_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", item["media_id"]):
            raise PackValidationError("Media ID format is invalid.")
        if kind not in MIMES or item["mime_type"] != MIMES[kind] or item["guest_approved_whole_file"] is not True:
            raise PackValidationError("Media kind, MIME or whole-file approval is invalid.")
        source = source_map.get(item["source_id"])
        if not source or source["version"] != item["source_version"]:
            raise PackValidationError("Media source/version is outside this pack.")
        if not isinstance(item["fact_ids"], list) or not item["fact_ids"]:
            raise PackValidationError("Media must bind to one or more approved facts.")
        for fid in item["fact_ids"]:
            if fid not in fact_map or (item["source_id"], item["source_version"]) not in fact_sources[fid]:
                raise PackValidationError("Media fact/source binding is invalid.")
        path = _safe_asset(root, item["asset_path"])
        if item["asset_path"] in referenced_paths:
            raise PackValidationError("Asset paths must be unique within a pack.")
        referenced_paths.add(item["asset_path"])
        declared_size = item["byte_size"]
        if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size < 0:
            raise PackValidationError("Asset size must be a nonnegative integer.")
        asset_limit = min(LIMITS[kind], MAX_TOTAL - total)
        if path.stat().st_size > LIMITS[kind]:
            raise PackValidationError("Asset exceeds its per-kind size limit.")
        if path.stat().st_size > asset_limit:
            raise PackValidationError("Aggregate pack exceeds the 64 MiB total size limit.")
        with path.open("rb") as asset_file:
            raw = asset_file.read(asset_limit + 1)
        if len(raw) > asset_limit:
            raise PackValidationError("Asset exceeds its bounded pack read limit.")
        total += len(raw)
        if len(raw) > LIMITS[kind] or len(raw) != declared_size or _sha(raw) != item["sha256"].lower():
            raise PackValidationError("Asset size or SHA-256 does not match its manifest.")
        if kind == "image":
            if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR" or struct.unpack(">II", raw[16:24]) == (0, 0):
                raise PackValidationError("Image is not a valid PNG header.")
        elif kind == "video":
            if len(raw) < 12 or raw[4:8] != b"ftyp":
                raise PackValidationError("Video is not an MP4 container.")
            durations[item["media_id"]] = _duration(path)
        else:
            item["cue_spans"] = _parse_vtt(raw)
        if item["media_id"] in assets:
            raise PackValidationError("Media IDs must be unique.")
        item.update({"hotel_id": hotel["hotel_id"], "valid_from": source["valid_from"],
                     "valid_to": source["valid_to"], "content": raw})
        assets[item["media_id"]] = item
        if kind in {"image", "video"}:
            try:
                subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                               check=True, capture_output=True, timeout=20)
            except (OSError, subprocess.SubprocessError) as exc:
                raise PackValidationError("Media decoder rejected the asset.") from exc
    seen_files = {"manifest.json"}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise PackValidationError("Symlink directories are not allowed in a pack.")
        for name in files:
            full = Path(directory) / name
            if full.is_symlink():
                raise PackValidationError("Symlink assets are not allowed.")
            seen_files.add(full.relative_to(root).as_posix())
    if seen_files != referenced_paths:
        raise PackValidationError("Aggregate media exceeds the 64 MiB pack limit.")
    linked_captions: set[str] = set()
    for item in media:
        if item["kind"] != "video":
            continue
        start, end = item.get("start_seconds"), item.get("end_seconds")
        duration = durations[item["media_id"]]
        if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or start < 0 or end <= start or end > duration):
            raise PackValidationError("Video time span must fit verified actual duration.")
        caption_id = item.get("captions_media_id")
        if caption_id and (caption_id not in assets or assets[caption_id]["kind"] != "captions"):
            raise PackValidationError("Video captions reference is invalid.")
        if caption_id:
            captions = assets[caption_id]
            if (captions["source_id"] != item["source_id"]
                    or captions["source_version"] != item["source_version"]
                    or not set(captions["fact_ids"]).issubset(set(item["fact_ids"]))):
                raise PackValidationError("Video captions must use the same approved source and facts.")
            if any(start < item["start_seconds"] or end > item["end_seconds"]
                   for start, end in captions["cue_spans"]):
                raise PackValidationError("WebVTT cue times must fit the approved video span.")
            linked_captions.add(caption_id)
        item["duration_seconds"] = duration
    if {m["media_id"] for m in media if m["kind"] == "captions"} != linked_captions:
        raise PackValidationError("Every captions asset must be linked to its matching video.")
    # Identity hashes the unchanged canonical manifest input; effective serving
    # validity is a projection and must not make changed input content a no-op.
    digest = hashlib.sha256(_canonical(stored_manifest) + b"\n" + _canonical([
        {"path": item["asset_path"], "sha256": item["sha256"].lower(), "size_bytes": item["byte_size"]}
        for item in sorted(media, key=lambda v: v["asset_path"])
    ])).hexdigest()
    return {"pack_id": manifest["pack_id"], "pack_version": manifest["pack_version"],
            "schema_version": 1, "manifest": stored_manifest, "canonical_hash": digest,
            "hotel": {"hotel_id": hotel["hotel_id"], "slug": hotel["slug"],
                      "config_version": hotel["config_version"], "public_config": {
                          k: hotel[k] for k in ("hotel_id", "name", "address", "description", "timezone", "currency") if k in hotel
                      } | {"synthetic": True, "source_pack": manifest["pack_id"]}},
            "sources": sources, "facts": facts, "media": media}
