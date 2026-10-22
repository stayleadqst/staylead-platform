#!/usr/bin/env python3
"""Validate the local synthetic media fixture manifest and assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIMESTAMP = re.compile(r"^(\d{2}):(\d{2}):(\d{2}\.\d{3})$")
CUE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+"
    r"(\d{2}:\d{2}:\d{2}\.\d{3})(?:\s+.*)?$"
)


class ValidationError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def seconds(value: str) -> float:
    match = TIMESTAMP.fullmatch(value)
    require(match is not None, f"invalid WebVTT timestamp: {value!r}")
    hours, minutes, sec = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(sec)


def safe_asset(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    require(candidate.is_relative_to(root), f"asset path escapes media root: {relative}")
    require(candidate.is_file(), f"missing asset: {relative}")
    return candidate


def verify_integrity(root: Path, record: dict) -> Path:
    path = safe_asset(root, record["asset_path"])
    size = path.stat().st_size
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    require(size == record.get("size_bytes"), f"size mismatch: {record['asset_path']}")
    require(digest == record.get("sha256"), f"SHA-256 mismatch: {record['asset_path']}")
    return path


def verify_png(root: Path, record: dict, decode: bool) -> None:
    require(record.get("raster_media_type") == "image/png",
            f"raster companion must declare image/png: {record['media_id']}")
    metadata = {
        "asset_path": record.get("raster_asset_path"),
        "sha256": record.get("raster_sha256"),
        "size_bytes": record.get("raster_size_bytes"),
    }
    require(all(metadata.values()), f"incomplete raster companion metadata: {record['media_id']}")
    path = verify_integrity(root, metadata)
    data = path.read_bytes()
    require(len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n",
            f"invalid PNG signature: {metadata['asset_path']}")
    require(data[12:16] == b"IHDR", f"missing PNG IHDR: {metadata['asset_path']}")
    width, height = struct.unpack(">II", data[16:24])
    require(width > 0 and height > 0, f"invalid PNG dimensions: {metadata['asset_path']}")
    if decode:
        ffmpeg = shutil.which("ffmpeg")
        require(ffmpeg is not None, "ffmpeg is required to decode PNG companions (--decode)")
        subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
                       check=True, capture_output=True)


def parse_vtt(path: Path) -> list[tuple[float, float, str]]:
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    require(bool(lines) and lines[0].strip() == "WEBVTT", f"missing WEBVTT header: {path}")
    cues = []
    i = 1
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        # A cue identifier is optional in WebVTT.
        timing_index = i if "-->" in lines[i] else i + 1
        require(timing_index < len(lines), f"incomplete WebVTT cue: {path}")
        match = CUE.fullmatch(lines[timing_index].strip())
        require(match is not None, f"invalid WebVTT cue timing: {path}:{timing_index + 1}")
        start, end = (seconds(value) for value in match.groups())
        i = timing_index + 1
        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
        require(start < end and bool(text_lines), f"empty or reversed WebVTT cue: {path}")
        cues.append((start, end, " ".join(text_lines)))
    return cues


def verify_video(path: Path, record: dict, root: Path, decode: bool) -> None:
    probe = shutil.which("ffprobe")
    require(probe is not None, "ffprobe is required to validate MP4 duration and streams")
    result = subprocess.run(
        [probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    require(len(videos) == 1, f"expected one video stream: {record['asset_path']}")
    require(not audios and record.get("audio_present") is False, f"expected silent video: {record['asset_path']}")
    duration = float(info["format"]["duration"])
    expected_duration = float(record["duration_seconds"])
    require(abs(duration - expected_duration) <= 0.02, f"duration mismatch: {record['asset_path']} ({duration}s vs {expected_duration}s)")

    scenes = record.get("scenes", [])
    require(bool(scenes), f"video has no scene metadata: {record['media_id']}")
    previous_end = 0.0
    for scene in scenes:
        start, end = float(scene["start_s"]), float(scene["end_s"])
        require(abs(start - previous_end) <= 0.001 and end > start,
                f"video scenes are not contiguous: {record['media_id']}")
        previous_end = end
    require(abs(previous_end - duration) <= 0.02, f"scene metadata does not cover video: {record['media_id']}")

    caption_path = safe_asset(root, record["captions_path"])
    cues = parse_vtt(caption_path)
    require(len(cues) == len(scenes), f"VTT cue count differs from scene count: {record['media_id']}")
    for index, (cue, scene) in enumerate(zip(cues, scenes)):
        start, end, text = cue
        require(abs(start - float(scene["start_s"])) <= 0.02
                and abs(end - float(scene["end_s"])) <= 0.02,
                f"VTT cue {index + 1} does not match scene timecodes: {record['media_id']}")
        require(text == scene["caption_text"], f"VTT cue text differs from manifest: {record['media_id']} cue {index + 1}")

    transcript_path = safe_asset(root, record["transcript_path"])
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    require(transcript.get("audio_present") is False and transcript.get("asr_output") is False,
            f"transcript metadata must identify authored, non-audio text: {record['media_id']}")
    require(transcript.get("script_text") == [scene["caption_text"] for scene in scenes],
            f"authored script differs from scene captions: {record['media_id']}")

    if decode:
        ffmpeg = shutil.which("ffmpeg")
        require(ffmpeg is not None, "ffmpeg is required for full MP4 decode validation (--decode)")
        subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
                       check=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decode", action="store_true", help="decode every MP4 with ffmpeg")
    args = parser.parse_args()
    manifest_path = HERE / "media_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("media_records", [])
    rejects = manifest.get("expected_reject", [])
    require(bool(records), "manifest has no media_records")
    ids = [record.get("media_id") for record in records + rejects]
    require(len(ids) == len(set(ids)), "duplicate media_id in manifest")

    checked = 0
    for record in records:
        path = verify_integrity(HERE, record)
        if record["media_type"] == "image/svg+xml":
            ET.parse(path)
            verify_png(HERE, record, args.decode)
        elif record["media_type"] == "video/mp4":
            verify_video(path, record, HERE, args.decode)
        else:
            raise ValidationError(f"unsupported media type {record['media_type']!r}: {record['media_id']}")
        checked += 1
    for record in rejects:
        verify_integrity(HERE, record)
        require(record.get("approved_for_guest") is False, f"expected-reject item is approved: {record['media_id']}")
        ET.parse(safe_asset(HERE, record["asset_path"]))
        checked += 1

    raster_count = sum("raster_asset_path" in record for record in records)
    print(f"Validated {checked} manifest assets and {raster_count} PNG companions "
          f"({len(records)} guest-approved, {len(rejects)} expected reject).")
    print("Full media decode: " + ("passed" if args.decode else "skipped; pass --decode to run it"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, OSError, KeyError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, ET.ParseError) as exc:
        print(f"media validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
