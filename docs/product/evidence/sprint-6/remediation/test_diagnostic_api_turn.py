from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("diagnostic_api_turn.py")
SPEC = importlib.util.spec_from_file_location("diagnostic_api_turn", SCRIPT)
assert SPEC and SPEC.loader
DIAGNOSTIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGNOSTIC)


def valid_state(turn: int = 7) -> dict[str, object]:
    return {
        "run_id": DIAGNOSTIC.RUN_ID,
        "guest_turns": turn - 1,
        "codex_requests": 12,
        "max_codex_requests": 18,
        "max_guest_turns": 9,
        "max_calls_per_turn": 2,
        "authorized_for_live_calls": True,
    }


@pytest.mark.parametrize("turn", [7, 8, 9])
def test_preflight_allows_only_sequential_pinned_diagnostic_turns(turn: int) -> None:
    DIAGNOSTIC._preflight_turn(turn, valid_state(turn))


def test_turns_seven_to_nine_validate_the_incremented_prior_session_count() -> None:
    prior_turns = 6
    for turn in (7, 8, 9):
        DIAGNOSTIC._preflight_turn(turn, valid_state(turn))
        DIAGNOSTIC._verify_prior_turn_count(prior_turns, turn - 1)
        prior_turns += 1
    assert prior_turns == 9


@pytest.mark.parametrize(("actual", "expected"), [(6, 7), (8, 7), (7, 8), (9, 8)])
def test_db_session_turn_count_must_match_selected_turn(actual: int, expected: int) -> None:
    with pytest.raises(ValueError):
        DIAGNOSTIC._verify_prior_turn_count(actual, expected)


@pytest.mark.parametrize(
    ("turn", "state"),
    [
        (6, valid_state(6)),
        (7, valid_state(8)),
        (7, {**valid_state(), "run_id": "other-run"}),
        (7, {**valid_state(), "codex_requests": 18}),
        (7, {**valid_state(), "max_calls_per_turn": 3}),
    ],
)
def test_preflight_rejects_wrong_identity_sequence_or_exhausted_caps(turn, state) -> None:
    with pytest.raises(ValueError):
        DIAGNOSTIC._preflight_turn(turn, state)


def test_namespace_six_sequence_turns_three_through_nine_without_reset() -> None:
    settings = DIAGNOSTIC._namespace_settings("remediation-6")
    assert settings["anchor_turn"] == 2
    assert settings["first_turn"] == 3
    assert settings["run_id"] == "s6-codex-20261026-remediation-6"
    state = valid_state(3)
    state["run_id"] = settings["run_id"]
    state["codex_requests"] = 4
    for turn in range(3, 10):
        state["guest_turns"] = turn - 1
        before = state.copy()
        DIAGNOSTIC._preflight_turn(turn, state, "remediation-6")
        assert state == before
        state["guest_turns"] = turn
        state["codex_requests"] += 1
    assert state["guest_turns"] == 9
    assert state["codex_requests"] == 11


def test_namespace_six_anchor_fingerprint_uses_only_its_turn_two_events(tmp_path: Path) -> None:
    events = [
        {"run_id": "s6-codex-20261026-remediation-4", "guest_turn": 6,
         "stage": "provider_call_started", "turn_request_id_sha256": "a" * 16},
        {"run_id": "s6-codex-20261026-remediation-6", "guest_turn": 3,
         "stage": "provider_call_started", "turn_request_id_sha256": "b" * 16},
        {"run_id": "s6-codex-20261026-remediation-6", "guest_turn": 2,
         "stage": "provider_call_started", "turn_request_id_sha256": "c" * 16},
        {"run_id": "s6-codex-20261026-remediation-6", "guest_turn": 2,
         "stage": "provider_call_started", "turn_request_id_sha256": "c" * 16},
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    assert DIAGNOSTIC._anchor_request_hash(path, "s6-codex-20261026-remediation-6", 2) == "c" * 16


def test_namespace_six_diagnostic_artifacts_are_isolated_from_namespace_four() -> None:
    ns4 = DIAGNOSTIC._result_path("remediation-4", 7)
    ns6 = [DIAGNOSTIC._result_path("remediation-6", turn) for turn in range(3, 10)]
    assert ns4.name == "diagnostic-api-turn-07.json"
    assert [path.name for path in ns6] == [
        f"namespace6-diagnostic-api-turn-{turn:02d}.json" for turn in range(3, 10)
    ]
    assert len(set(ns6 + [ns4])) == 8


def test_result_creation_is_private_exclusive_and_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "namespace6-diagnostic-api-turn-03.json"
    DIAGNOSTIC._write_result(path, {"status": "in_progress"}, exclusive=True)
    original = path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        DIAGNOSTIC._write_result(path, {"status": "replacement"}, exclusive=True)
    assert path.read_bytes() == original


def test_saved_response_is_allowlisted_and_drops_credentials_and_unknown_fields() -> None:
    result = DIAGNOSTIC.safe_response({
        "status": "completed",
        "answer": "Exact answer text",
        "access_token": "must-not-appear",
        "unknown_field": {"raw": "must-not-appear"},
        "evidence": [{"fact_id": "F-1", "source_id": "S-1", "raw": "drop"}],
        "guest_brief": {
            "brief_version": 5,
            "dates": {"check_in": "2026-12-10", "check_out": "2026-12-15"},
            "party": {"adults": 2, "children": [
                {"age": 7, "member_id": "private-id"},
            ]},
            "pending_fields": [],
            "session_id": "private-session",
        },
        "trace": {"answer_validation": "fully_validated", "guest_claims_rejected": 0, "prompt": "drop"},
    })
    serialized = str(result)
    assert "must-not-appear" not in serialized
    assert "private-id" not in serialized
    assert "private-session" not in serialized
    assert result["answer"] == "Exact answer text"
    assert result["evidence"] == [{"fact_id": "F-1", "source_id": "S-1"}]
    assert result["trace"] == {"answer_validation": "fully_validated", "guest_claims_rejected": 0}
    assert result["guest_brief"]["party"]["children"] == [
        {"age": 7, "member_id_sha256": hashlib.sha256(b"private-id").hexdigest()[:16]}
    ]
