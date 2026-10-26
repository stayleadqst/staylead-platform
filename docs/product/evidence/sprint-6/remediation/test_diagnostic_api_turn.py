from __future__ import annotations

import importlib.util
import hashlib
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
