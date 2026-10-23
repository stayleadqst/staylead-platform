import hashlib
import json
import shutil
from pathlib import Path

import pytest
from staylead_platform.domains.hospitality.registration import pack_schema
from staylead_platform.domains.hospitality.registration.pack_schema import (
    PackValidationError,
    validate_pack,
)

FIXTURE = Path(__file__).parents[1].parent / "fixtures/hospitality/media-pack-v1"


def copy_pack(tmp_path: Path) -> Path:
    destination = tmp_path / "pack"
    shutil.copytree(FIXTURE, destination)
    return destination


def load_manifest(root: Path) -> dict:
    return json.loads((root / "manifest.json").read_text())


def save_manifest(root: Path, value: dict) -> None:
    (root / "manifest.json").write_text(json.dumps(value))


def test_pack_has_stable_digest_and_full_media_metadata():
    first = validate_pack(FIXTURE)
    second = validate_pack(FIXTURE)
    assert first["canonical_hash"] == second["canonical_hash"]
    assert {m["kind"] for m in first["media"]} == {"image", "video", "captions"}
    clip = next(m for m in first["media"] if m["kind"] == "video")
    assert clip["duration_seconds"] >= 2.9
    assert clip["end_seconds"] <= clip["duration_seconds"]


def test_total_pack_size_includes_manifest_and_is_checked_before_asset_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    root = copy_pack(tmp_path)
    manifest_size = (root / "manifest.json").stat().st_size
    asset_size = sum((root / item["asset_path"]).stat().st_size
                     for item in load_manifest(root)["media"])
    monkeypatch.setattr(pack_schema, "MAX_TOTAL", manifest_size + asset_size - 1)
    with pytest.raises(PackValidationError, match="total size limit"):
        validate_pack(root)


def test_manifest_larger_than_pack_limit_is_rejected_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    root = copy_pack(tmp_path)
    size = (root / "manifest.json").stat().st_size
    monkeypatch.setattr(pack_schema, "MAX_TOTAL", size - 1)
    with pytest.raises(PackValidationError, match="Manifest exceeds"):
        validate_pack(root)


def test_canonical_digest_changes_for_input_hidden_by_effective_validity_clamp(tmp_path: Path):
    root1 = copy_pack(tmp_path)
    root2 = tmp_path / "second-clamp"
    shutil.copytree(FIXTURE, root2)
    for root, fact_end in ((root1, "2030-12-31"), (root2, "2040-12-31")):
        manifest = load_manifest(root)
        manifest["sources"][0]["valid_to"] = "2030-12-31"
        manifest["facts"][0]["valid_to"] = fact_end
        save_manifest(root, manifest)
    first, second = validate_pack(root1), validate_pack(root2)
    assert first["facts"][0]["valid_to"] == second["facts"][0]["valid_to"] == "2030-12-31"
    assert first["canonical_hash"] != second["canonical_hash"]


@pytest.mark.parametrize("mutation", ["bad-hash", "wrong-mime", "no-approval", "wrong-time", "oracle"])
def test_invalid_pack_is_rejected_before_publication(tmp_path: Path, mutation: str):
    root = copy_pack(tmp_path)
    manifest = load_manifest(root)
    clip = next(m for m in manifest["media"] if m["kind"] == "video")
    if mutation == "bad-hash":
        clip["sha256"] = "0" * 64
    elif mutation == "wrong-mime":
        clip["mime_type"] = "video/quicktime"
    elif mutation == "no-approval":
        clip["guest_approved_whole_file"] = False
    elif mutation == "wrong-time":
        clip["end_seconds"] = 999
    else:
        manifest["expected_visible_labels"] = ["secret oracle"]
    save_manifest(root, manifest)
    with pytest.raises(PackValidationError):
        validate_pack(root)


def test_asset_escape_and_invalid_vtt_are_rejected(tmp_path: Path):
    root = copy_pack(tmp_path)
    manifest = load_manifest(root)
    manifest["media"][0]["asset_path"] = "../outside.png"
    save_manifest(root, manifest)
    with pytest.raises(PackValidationError, match="path"):
        validate_pack(root)
    second = tmp_path / "second"
    second.mkdir()
    root = copy_pack(second)
    captions = root / "assets/pool.vtt"
    captions.write_bytes(b"not webvtt")
    manifest = load_manifest(root)
    entry = next(m for m in manifest["media"] if m["kind"] == "captions")
    entry["byte_size"] = captions.stat().st_size
    entry["sha256"] = hashlib.sha256(captions.read_bytes()).hexdigest()
    save_manifest(root, manifest)
    with pytest.raises(PackValidationError, match="WebVTT"):
        validate_pack(root)


@pytest.mark.parametrize("bad_vtt,wrong_binding", [
    (b"WEBVTT\n\n00:00:bad --> 00:00:02.500\nInvalid cue\n", False),
    (b"WEBVTT\n00:00:00.500 --> 00:00:02.500\nMissing separator\n", False),
    (b"WEBVTT\n\ncue-without-timing", False),
    (b"WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nBeyond approved span\n", False),
    (None, True),
])
def test_captions_must_parse_and_match_approved_clip_span_and_scope(
    tmp_path: Path, bad_vtt: bytes | None, wrong_binding: bool,
):
    root = copy_pack(tmp_path)
    manifest = load_manifest(root)
    vtt = next(m for m in manifest["media"] if m["kind"] == "captions")
    if wrong_binding:
        vtt["fact_ids"] = ["fact-room-balcony"]
    else:
        raw = bad_vtt
        (root / vtt["asset_path"]).write_bytes(raw)
        vtt["byte_size"] = len(raw)
        vtt["sha256"] = hashlib.sha256(raw).hexdigest()
    save_manifest(root, manifest)
    with pytest.raises(PackValidationError):
        validate_pack(root)


def test_fact_validity_is_intersected_with_approved_source():
    pack = validate_pack(FIXTURE)
    source_end = pack["sources"][0]["valid_to"]
    assert all(fact["valid_to"] <= source_end for fact in pack["facts"])
    assert next(f for f in pack["facts"] if f["fact_id"] == "fact-pool-view")["valid_from"] == pack["sources"][0]["valid_from"]


def test_fact_overflow_rejected_without_truncation(tmp_path: Path):
    root = copy_pack(tmp_path)
    manifest = load_manifest(root)
    template = manifest["facts"][0]
    manifest["facts"] = [dict(template, fact_id=f"overflow-{index}") for index in range(401)]
    save_manifest(root, manifest)
    with pytest.raises(PackValidationError, match="400"):
        validate_pack(root)


def test_exact_400_guest_facts_are_accepted(tmp_path: Path):
    root = copy_pack(tmp_path)
    manifest = load_manifest(root)
    template = manifest["facts"][0]
    manifest["facts"] = [dict(template, fact_id=f"boundary-{index}") for index in range(400)]
    for media in manifest["media"]:
        media["fact_ids"] = ["boundary-0"]
    save_manifest(root, manifest)
    assert len(validate_pack(root)["facts"]) == 400


@pytest.mark.parametrize("mutation", ["foreign-fact", "source-version", "source-approval", "validity", "unknown-field", "bad-media-id", "bad-dot-id", "multi-source"])
def test_unscoped_or_unapproved_records_are_rejected(tmp_path: Path, mutation: str):
    root = copy_pack(tmp_path)
    manifest = load_manifest(root)
    if mutation == "foreign-fact":
        manifest["media"][0]["fact_ids"] = ["foreign-fact-id"]
    elif mutation == "source-version":
        manifest["media"][0]["source_version"] = "999"
    elif mutation == "source-approval":
        manifest["sources"][0]["guest_approved"] = False
    elif mutation == "validity":
        manifest["facts"][0]["valid_from"] = "2035-12-31"
        manifest["facts"][0]["valid_to"] = "2025-01-01"
    elif mutation == "bad-media-id":
        manifest["media"][0]["media_id"] = "media/room"
    elif mutation == "bad-dot-id":
        manifest["media"][0]["media_id"] = ".."
    elif mutation == "multi-source":
        manifest["facts"][0]["source_refs"].append({"source_id": "source-hotel-guide", "version": "1"})
    else:
        manifest["facts"][0]["internal_only"] = True
    save_manifest(root, manifest)
    with pytest.raises(PackValidationError):
        validate_pack(root)


def test_symlink_asset_is_rejected(tmp_path: Path):
    root = copy_pack(tmp_path)
    original = root / "assets/room.png"
    original.unlink()
    original.symlink_to(root / "assets/pool.vtt")
    with pytest.raises(PackValidationError, match="Symlink"):
        validate_pack(root)
