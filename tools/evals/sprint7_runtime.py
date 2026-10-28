"""One-shot, opt-in Sprint 7 Codex CLI runtime with persistent hard bounds.

The module is offline on import. It refuses to start without a separately
prepared, private runtime config and an authorized private run-state. Starting
the server consumes the namespace permanently; a started or failed run cannot
be restarted, reset, or resumed. No Sprint 6 state or provider accounting is
read or changed.

Expected private files (mode 0600, both under /private/tmp):
  config: run_id, authority, candidate_sha256, matrix_sha256, database_url,
          session_signing_secret, provider='codex_cli', model='gpt-6.1-sol',
          effort='low', candidate_manifest_path, live_cases_path, oracle_path,
          oracle_sha256
state:  run_id, authority, candidate_sha256, matrix_sha256,
          authorized_for_live_calls=true, status='authorized',
  max_guest_turns=2, max_codex_requests=4, max_calls_per_turn=2,
  reserved_guest_turn_budget=2, reserved_request_budget=4,
  guest_turns=0, codex_requests=0 (fresh namespace; cases 1–2 only)

The authorization record and pinned candidate manifest are supplied by the
coordinator after approval. This runtime intentionally has no init/reset CLI.
"""

from __future__ import annotations

import argparse
import contextvars
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import threading
import time
from pathlib import Path
from typing import Any

RUN_ID = "s7-room-advice-20261028-reacceptance7-sol"
CASE_RUN_ID = "s7-room-advice-20261028-reacceptance7-sol"
PRIOR_RUN_ID = "s7-room-advice-20261028-reacceptance6-sol"
PRIOR_STATE_PATH = Path("/private/tmp/staylead-s7-reacceptance6-sol-state.json")
PRIOR_STATE_SHA256 = "4a238a18eb8a8b1e904f8e3b5188fb06a1974128d3a85e7121651b00b59c5b27"
MAX_GUEST_TURNS = 2
MAX_REQUESTS = 4
START_GUEST_TURNS = 0
START_REQUESTS = 0
APPROVED_CASE_TURNS = (1, 2)
MAX_CALLS_PER_TURN = 2
MAX_OUTPUT_TOKENS = 700
PROVIDER_TIMEOUT_SECONDS = 25.0
TURN_TIMEOUT_SECONDS = 45.0
MODEL = "gpt-6.1-sol"
EFFORT = "low"


class _UnapprovedGuestTurn(RuntimeError):
    """Raised before reservation when a request is not the next pinned utterance."""
LIVE_ENV = "STAYLEAD_LIVE_EVAL"
CONFIG_ENV = "STAYLEAD_S7_RUNTIME_CONFIG"
STATE_ENV = "STAYLEAD_S7_RUN_STATE"
EVENTS_ENV = "STAYLEAD_S7_RUNTIME_EVENTS"
CAPTURE_ENV = "STAYLEAD_S7_CAPTURE_SYNTHETIC_JSON"
TURN: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("sprint7_turn", default=None)
LOCK = threading.RLock()
LEASE_PATH = Path(f"/private/tmp/staylead-s7-{RUN_ID}.process.lock")
LEASE_FD: int | None = None


def _acquire_process_lease() -> None:
    """Prevent duplicate runtimes from racing the same persistent counters."""
    global LEASE_FD
    with LOCK:
        if LEASE_FD is not None:
            return
        path = LEASE_PATH
        if path.is_symlink():
            raise RuntimeError("Unsafe Sprint 7 process lease path.")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise RuntimeError("Another Sprint 7 runtime already holds the process lease.") from exc
        LEASE_FD = fd


def _release_process_lease() -> None:
    global LEASE_FD
    with LOCK:
        if LEASE_FD is None:
            return
        fcntl.flock(LEASE_FD, fcntl.LOCK_UN)
        os.close(LEASE_FD)
        LEASE_FD = None


def _private_file(path: Path) -> dict[str, Any]:
    """Read one private JSON object without following symlinks."""
    if not path.is_absolute() or not str(path).startswith("/private/tmp/"):
        raise RuntimeError("Sprint 7 private files must be under /private/tmp.")
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeError("Sprint 7 private config/state is missing.") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("Sprint 7 private config/state must be a regular 0600 file.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Sprint 7 private config/state is unreadable.") from exc
    if not isinstance(value, dict):
        # Keep malformed private control files on the same fail-closed path.
        raise RuntimeError("Sprint 7 private config/state must be a JSON object.")  # noqa: TRY004
    return value


def _paths() -> tuple[Path, Path, Path]:
    config_value = os.environ.get(CONFIG_ENV)
    state_value = os.environ.get(STATE_ENV)
    if not config_value or not state_value:
        raise RuntimeError(f"Set {CONFIG_ENV} and {STATE_ENV} to approved private files.")
    config = Path(config_value)
    state = Path(state_value)
    events = Path(os.environ.get(EVENTS_ENV, f"/private/tmp/staylead-s7-{RUN_ID}-runtime-events.jsonl"))
    if not config or not state:
        raise RuntimeError(f"Set {CONFIG_ENV} and {STATE_ENV} to approved private files.")
    for item in (config, state, events):
        if not item.is_absolute() or not str(item).startswith("/private/tmp/"):
            raise RuntimeError("Sprint 7 private paths must be under /private/tmp.")
    return config, state, events


def _valid_state(state: dict[str, Any], config: dict[str, Any], *, fresh: bool = False) -> bool:
    return (
        state.get("run_id") == RUN_ID == config.get("run_id")
        and state.get("authority") == config.get("authority")
        and state.get("candidate_sha256") == config.get("candidate_sha256")
        and state.get("matrix_sha256") == config.get("matrix_sha256")
        and re.fullmatch(r"[a-f0-9]{64}", str(state.get("candidate_sha256", ""))) is not None
        and re.fullmatch(r"[a-f0-9]{64}", str(state.get("matrix_sha256", ""))) is not None
        and state.get("authorized_for_live_calls") is True
        and state.get("status") in ({"authorized"} if fresh else {"authorized", "starting", "running", "halted", "completed"})
        and state.get("max_guest_turns") == MAX_GUEST_TURNS
        and state.get("max_codex_requests") == MAX_REQUESTS
        and state.get("max_calls_per_turn") == MAX_CALLS_PER_TURN
        and state.get("reserved_guest_turn_budget") == MAX_GUEST_TURNS
        and state.get("reserved_request_budget") == MAX_REQUESTS
        and _counter(state.get("guest_turns"), MAX_GUEST_TURNS)
        and _counter(state.get("codex_requests"), MAX_REQUESTS)
        and state.get("guest_turns") == state.get("approved_case_turn")
        and state.get("approved_case_turn") == state.get("guest_turns")
        and (not fresh or (state.get("guest_turns") == 0
                           and state.get("codex_requests") == 0
                           and state.get("approved_case_turn") == 0))
        and config.get("prior_allocation") == _prior_allocation_record()
        and config.get("continuation") is None
        and state.get("prior_allocation_state_sha256") == PRIOR_STATE_SHA256
        and isinstance(state.get("authority"), str)
        and bool(state["authority"].strip())
        and config.get("provider") == "codex_cli"
        and config.get("model") == MODEL
        and config.get("effort") == EFFORT
        and isinstance(config.get("database_url"), str)
        and isinstance(config.get("session_signing_secret"), str)
        and bool(config["database_url"] and config["session_signing_secret"])
        and isinstance(config.get("candidate_manifest_path"), str)
        and isinstance(config.get("live_cases_path"), str)
        and isinstance(config.get("oracle_path"), str)
        and isinstance(config.get("oracle_sha256"), str)
        and config["prior_allocation"] == _prior_allocation_record()
    )


def _prior_allocation_record() -> dict[str, Any]:
    return {
        "run_id": PRIOR_RUN_ID,
        "candidate_sha256": "a7b93fae598973c0911e75ed438797c4b0b42544ee5dd7f5ec4206ca17f4d04f",
        "status": "halted", "guest_turns": 1, "codex_requests": 2,
        "state_sha256": PRIOR_STATE_SHA256, "lifetime_requests": 52,
        "unused_guest_slots": 1, "unused_request_slots": 2,
        "unused_slots": "closed; dependent originalturn2 notattempted; no retry/reset/reallocation",
        "actual_outcome": {
            "pine1": "FAIL AC2 unnecessary generic room_advice question despite all relevant saved nonpending requirements",
            "pine2": "Blocked dependency/notattempted",
        },
        "runners": "API62558 SIGTERM exit143; browser35519 SIGTERM then exact ownedPID13138 SIGKILL exit137; no marker01/turn2/retry",
    }


def _verify_closed_prior_allocation(value: Any) -> dict[str, Any]:
    if value != _prior_allocation_record():
        raise RuntimeError("Prior Sprint 7 allocation is not the exact closed immutable receipt.")
    parent = _private_file(PRIOR_STATE_PATH)
    if (_file_sha256(PRIOR_STATE_PATH) != PRIOR_STATE_SHA256
            or parent.get("run_id") != PRIOR_RUN_ID or parent.get("status") != "halted"
            or parent.get("guest_turns") != 1 or parent.get("codex_requests") != 2
            or parent.get("max_guest_turns") != 2 or parent.get("max_codex_requests") != 4):
        raise RuntimeError("Prior Sprint 7 state changed or is not the exact sealed 1/2 allocation.")
    return parent


def _counter(value: Any, limit: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= limit


def _save_state(path: Path, state: dict[str, Any]) -> None:
    """Atomic state replacement; refuse stale temporary files and symlinks."""
    temp = path.with_name(path.name + ".tmp")
    if temp.exists() or temp.is_symlink():
        raise RuntimeError("Sprint 7 state temp file already exists; refusing overwrite.")
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
        temp.replace(path)
        path.chmod(0o600)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def prepare_private_run(
    *, approval_file: Path, candidate_manifest: Path, config_path: Path, state_path: Path,
    database_url: str, session_signing_secret: str,
) -> None:
    """Create a fresh private namespace from approval and a pinned candidate.

    The prior allocation remains closed. This fresh namespace starts at 0/0 and
    verifies the exact prior receipt; no counters transfer from earlier attempts.
    No secrets are read from the environment or printed.
    """
    approval = json.loads(approval_file.read_text(encoding="utf-8"))
    manifest = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    if not isinstance(approval, dict) or not isinstance(manifest, dict):
        # Approval inputs use one fail-closed exception contract for all malformed shapes.
        raise RuntimeError("Approval and candidate manifest must be JSON objects.")  # noqa: TRY004
    if (
        approval.get("run_id") != RUN_ID
        or approval.get("authorized_for_live_calls") is not True
        or approval.get("max_guest_turns") != MAX_GUEST_TURNS
        or approval.get("max_codex_requests") != MAX_REQUESTS
        or approval.get("max_calls_per_turn") != MAX_CALLS_PER_TURN
        or approval.get("model") != MODEL
        or approval.get("effort") != EFFORT
        or approval.get("provider_timeout_seconds") != PROVIDER_TIMEOUT_SECONDS
        or approval.get("turn_timeout_seconds") != TURN_TIMEOUT_SECONDS
        or approval.get("output_cap") != MAX_OUTPUT_TOKENS
        or not isinstance(approval.get("authority"), str)
        or not approval["authority"].strip()
        or approval.get("case_matrix_sha256") != manifest.get("matrix_sha256")
        or approval.get("continuation") is not None
        or manifest.get("continuation") is not None
    ):
        raise RuntimeError("Approval does not authorize this exact Sprint 7 run and cap set.")
    candidate_sha = manifest.get("candidate_sha256")
    matrix_sha = manifest.get("matrix_sha256")
    if (not isinstance(candidate_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", candidate_sha)
            or not isinstance(matrix_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", matrix_sha)
            or manifest.get("run_id") != RUN_ID):
        raise RuntimeError("Candidate manifest is not pinned to the Sprint 7 run.")
    if (_candidate_manifest_digest(manifest) != candidate_sha
            or not isinstance(manifest.get("oracle_sha256"), str)
            or not isinstance(manifest.get("source_files"), dict) or not manifest["source_files"]
            or not manifest.get("live_cases_path") or not manifest.get("oracle_path")
            or manifest.get("prior_allocation") != _prior_allocation_record()
            or approval.get("prior_allocation") != manifest.get("prior_allocation")):
        raise RuntimeError("Candidate manifest does not pin source, case and oracle bytes.")
    _verify_closed_prior_allocation(manifest["prior_allocation"])
    if not database_url or not session_signing_secret:
        raise RuntimeError("Private development database and signing secret are required.")
    for destination in (config_path, state_path):
        if not destination.is_absolute() or not str(destination).startswith("/private/tmp/"):
            raise RuntimeError("Private Sprint 7 config/state must be under /private/tmp.")
        if destination.exists() or destination.is_symlink():
            raise RuntimeError("Refusing to initialize or overwrite an existing Sprint 7 run file.")
    config = {
        "run_id": RUN_ID, "authority": approval["authority"],
        "candidate_sha256": candidate_sha, "matrix_sha256": matrix_sha,
        "provider": "codex_cli", "model": MODEL, "effort": EFFORT,
        "database_url": database_url, "session_signing_secret": session_signing_secret,
        "candidate_manifest_path": str(candidate_manifest),
        "live_cases_path": str(manifest.get("live_cases_path", "")),
        "oracle_path": str(manifest.get("oracle_path", "")),
        "oracle_sha256": manifest.get("oracle_sha256"),
        "prior_allocation": manifest["prior_allocation"],
        "continuation": None,
    }
    _verify_candidate_inputs(config)
    state = {
        "run_id": RUN_ID, "authority": approval["authority"],
        "candidate_sha256": candidate_sha, "matrix_sha256": matrix_sha,
        "authorized_for_live_calls": True, "status": "authorized",
        "max_guest_turns": MAX_GUEST_TURNS, "max_codex_requests": MAX_REQUESTS,
        "max_calls_per_turn": MAX_CALLS_PER_TURN,
        "reserved_guest_turn_budget": MAX_GUEST_TURNS,
        "reserved_request_budget": MAX_REQUESTS,
        "guest_turns": 0, "codex_requests": 0,
        "approved_case_turn": START_GUEST_TURNS,
        "prior_allocation_state_sha256": PRIOR_STATE_SHA256,
    }
    for destination, value in ((config_path, config), (state_path, state)):
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _transition_status(new_status: str, *, detail: str | None = None) -> None:
    if new_status in {"starting", "running"} and LEASE_FD is None:
        raise RuntimeError("Sprint 7 process lease is required before startup.")
    config_path, state_path, _ = _paths()
    with LOCK:
        config = _private_file(config_path)
        state = _private_file(state_path)
        if new_status in {"starting", "running"}:
            _verify_candidate_inputs(config)
        if not _valid_state(state, config, fresh=(new_status == "starting")):
            raise RuntimeError("Sprint 7 authorization is absent, malformed, consumed, or mismatched.")
        if new_status == "starting" and (state["guest_turns"] != START_GUEST_TURNS
                                           or state["codex_requests"] != START_REQUESTS):
            raise RuntimeError("Reacceptance namespace is consumed; restart is forbidden.")
        state["status"] = new_status
        if new_status == "starting":
            state["start_attempts"] = int(state.get("start_attempts", 0)) + 1
            state["last_start_attempt_unix"] = time.time()
        if detail:
            state["stop_reason"] = detail
        _save_state(state_path, state)


def _release_bootstrap_if_unused(reason: str) -> bool:
    """Permit a same-candidate startup retry only before any turn/request reservation."""
    if LEASE_FD is None:
        return False
    config_path, state_path, _ = _paths()
    with LOCK:
        config = _private_file(config_path)
        state = _private_file(state_path)
        if not _valid_state(state, config) or state.get("status") not in {"starting", "running"}:
            return False
        if state.get("guest_turns") != START_GUEST_TURNS or state.get("codex_requests") != START_REQUESTS:
            return False
        state["status"] = "authorized"
        state["last_bootstrap_failure"] = re.sub(r"[^A-Za-z0-9_.:-]", "_", reason)[:80]
        _save_state(state_path, state)
        return True


def _reserve(field: str, limit: int, label: str) -> int:
    if LEASE_FD is None:
        raise RuntimeError("Sprint 7 process lease is not held.")
    config_path, state_path, _ = _paths()
    with LOCK:
        config = _private_file(config_path)
        state = _private_file(state_path)
        _verify_candidate_inputs(config)
        if state.get("run_id") != RUN_ID or state.get("status") != "running":
            raise RuntimeError("Sprint 7 run is not active.")
        current = state.get(field)
        if not _counter(current, limit) or current >= limit:
            raise RuntimeError(f"Sprint 7 {label} limit reached; no call was launched.")
        state[field] = current + 1
        state[f"{field}_reserved_at_unix"] = time.time()
        _save_state(state_path, state)
        return current + 1


def _reserve_approved_guest_turn(utterance: str) -> int:
    """Atomically verify the next approved utterance and reserve its turn slot."""
    if LEASE_FD is None:
        raise RuntimeError("Sprint 7 process lease is not held.")
    config_path, state_path, _ = _paths()
    with LOCK:
        config = _private_file(config_path)
        state = _private_file(state_path)
        _verify_candidate_inputs(config)
        if state.get("run_id") != RUN_ID or state.get("status") != "running":
            raise RuntimeError("Sprint 7 run is not active.")
        current = state.get("guest_turns")
        if not _counter(current, MAX_GUEST_TURNS) or current >= MAX_GUEST_TURNS:
            raise RuntimeError("Sprint 7 guest turn limit reached; no call was launched.")
        next_turn = current + 1
        try:
            matrix = json.loads(Path(config["live_cases_path"]).read_text(encoding="utf-8"))
            cases = matrix.get("cases")
            case = (cases[current] if matrix.get("run_id") == CASE_RUN_ID
                    and isinstance(cases, list) and len(cases) == MAX_GUEST_TURNS else None)
        except (OSError, json.JSONDecodeError, TypeError, IndexError):
            case = None
        if (next_turn not in APPROVED_CASE_TURNS or not isinstance(case, dict) or case.get("turn") != next_turn
                or not isinstance(case.get("utterance"), str) or case["utterance"] != utterance):
            raise _UnapprovedGuestTurn("Guest question does not match the next approved case; no call was launched.")
        state["guest_turns"] = next_turn
        state["approved_case_turn"] = next_turn
        state["guest_turns_reserved_at_unix"] = time.time()
        _save_state(state_path, state)
        return next_turn


def _hash(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate_manifest_digest(manifest: dict[str, Any]) -> str:
    pinned = {name: manifest.get(name) for name in
              ("run_id", "source_files", "matrix_sha256", "oracle_sha256", "prior_allocation", "continuation")}
    encoded = json.dumps(pinned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Pinned Sprint 7 input is missing or not a regular file.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_candidate_inputs(config: dict[str, Any]) -> None:
    """Verify actual source/case/oracle bytes on every reservation boundary."""
    manifest_path = Path(config["candidate_manifest_path"])
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("Pinned Sprint 7 candidate manifest is unsafe or missing.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Pinned Sprint 7 candidate manifest is unreadable.") from exc
    if (not isinstance(manifest, dict) or manifest.get("run_id") != RUN_ID
            or manifest.get("candidate_sha256") != config.get("candidate_sha256")
            or _candidate_manifest_digest(manifest) != config.get("candidate_sha256")
            or manifest.get("matrix_sha256") != config.get("matrix_sha256")
            or manifest.get("oracle_sha256") != config.get("oracle_sha256")
            or manifest.get("prior_allocation") != config.get("prior_allocation")
            or manifest.get("continuation") is not None or config.get("continuation") is not None
            or not isinstance(manifest.get("source_files"), dict) or not manifest["source_files"]):
        raise RuntimeError("Pinned Sprint 7 candidate manifest changed or lacks source file pins.")
    _verify_closed_prior_allocation(config["prior_allocation"])
    repo_root = Path(__file__).resolve().parents[2]
    for relative, expected in manifest["source_files"].items():
        if (not isinstance(relative, str) or not isinstance(expected, str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected)):
            raise RuntimeError("Pinned Sprint 7 source manifest is malformed.")
        source = repo_root / relative
        if source.is_symlink() or not source.resolve().is_relative_to(repo_root):
            raise RuntimeError("Pinned Sprint 7 source path is unsafe.")
        if _file_sha256(source) != expected:
            raise RuntimeError("Pinned Sprint 7 candidate source hash changed.")
    if (_file_sha256(Path(config["live_cases_path"])) != config.get("matrix_sha256")
            or _file_sha256(Path(config["oracle_path"])) != config.get("oracle_sha256")):
        raise RuntimeError("Pinned Sprint 7 case matrix or independent oracle changed.")


def _event(record: dict[str, Any]) -> None:
    """Append only fixed metadata; never accept request/answer/config values."""
    _, _, path = _paths()
    allowed = {
        "stage", "run_id", "turn", "call", "request_id_sha256", "input_sha256",
        "instructions_sha256", "input_chars", "instructions_chars", "output_chars",
        "output_sha256", "latency_ms", "input_tokens", "output_tokens", "total_tokens",
        "status", "exception_class", "provider", "model", "effort",
    }
    safe = {key: record[key] for key in record.keys() & allowed}
    safe["unix_time"] = time.time()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode)):
        raise RuntimeError("Unsafe Sprint 7 telemetry path.")
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(safe, ensure_ascii=False, sort_keys=True) + "\n")


def _capture_synthetic_json(text: str, turn: dict[str, Any], call: int) -> None:
    if os.environ.get(CAPTURE_ENV) != "1" or turn.get("synthetic_pinned") is not True:
        return
    raw = text.encode("utf-8")
    if len(raw) > 64 * 1024:
        raise RuntimeError("Synthetic response exceeds the private capture cap.")
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Synthetic response capture requires JSON.") from exc
    capture_dir = Path(f"/private/tmp/staylead-s7-{RUN_ID}-captures")
    capture_dir.mkdir(mode=0o700, exist_ok=True)
    if capture_dir.is_symlink() or not stat.S_ISDIR(capture_dir.lstat().st_mode):
        raise RuntimeError("Unsafe private capture directory.")
    capture_dir.chmod(0o700)
    target = capture_dir / f"turn-{turn['guest_turn']:02d}-call-{call:02d}.json"
    document = json.dumps({
        "run_id": RUN_ID, "turn": turn["guest_turn"], "call": call,
        "synthetic_only": True, "response_sha256": _hash(text),
        "response_bytes": len(raw), "response": parsed,
    }, ensure_ascii=False, indent=2) + "\n"
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(document)


def _observed_provider(provider: Any) -> Any:
    original = provider.generate

    async def generate(request: Any) -> Any:
        turn = TURN.get()
        if turn is None:
            raise RuntimeError("Sprint 7 provider call occurred outside a reserved guest turn.")
        requested_output = getattr(request, "max_output_tokens", None)
        if not isinstance(requested_output, int) or requested_output < 1 or requested_output > MAX_OUTPUT_TOKENS:
            raise RuntimeError("Sprint 7 provider request exceeded the pinned output cap.")
        if turn["calls"] >= MAX_CALLS_PER_TURN:
            raise RuntimeError("Sprint 7 two-call-per-turn limit reached.")
        # Persist the allowance before launch; the global reservation number is not needed here.
        _reserve("codex_requests", MAX_REQUESTS, "request")
        turn["calls"] += 1
        started = time.monotonic()
        base = {
            "run_id": RUN_ID, "turn": turn["guest_turn"], "call": turn["calls"],
            "request_id_sha256": _hash(turn.get("request_id")),
            "input_sha256": _hash(request.input_text),
            "instructions_sha256": _hash(request.instructions),
            "input_chars": len(request.input_text), "instructions_chars": len(request.instructions),
            "provider": "codex_cli", "model": MODEL, "effort": EFFORT,
        }
        _event({"stage": "provider_reserved", **base})
        try:
            result = await original(request)
        except BaseException as exc:
            _event({"stage": "provider_failed", **base,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "exception_class": type(exc).__name__})
            _transition_status("halted", detail="provider_failure")
            raise
        usage = getattr(result, "usage", None)
        _capture_synthetic_json(result.text, turn, turn["calls"])
        _event({
            "stage": "provider_completed", **base,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "output_chars": len(result.text), "output_sha256": _hash(result.text),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        })
        return result

    provider.generate = generate
    return provider


def create_runtime_app() -> Any:
    if os.environ.get(LIVE_ENV) != "1":
        raise RuntimeError(f"Set {LIVE_ENV}=1 explicitly to enable live calls.")
    _acquire_process_lease()
    config_path, state_path, _ = _paths()
    config, state = _private_file(config_path), _private_file(state_path)
    if not _valid_state(state, config, fresh=True):
        raise RuntimeError("Sprint 7 run is not freshly authorized; API was not started.")
    _transition_status("starting")
    executable = shutil.which("codex")
    if not executable:
        _release_bootstrap_if_unused("codex_cli_unavailable")
        raise RuntimeError("Existing Codex CLI is unavailable.")

    from pydantic import SecretStr

    from staylead_platform.composition.configuration.settings import Settings
    from staylead_platform.composition.dependencies.guest_chat import build_provider
    from staylead_platform.entrypoints.app import create_app
    settings = Settings(
        _env_file=None, environment="development", database_url=config["database_url"],
        session_signing_secret=SecretStr(config["session_signing_secret"]),
        ai_provider="codex_cli", ai_timeout_seconds=PROVIDER_TIMEOUT_SECONDS,
        ai_turn_timeout_seconds=TURN_TIMEOUT_SECONDS, ai_max_output_tokens=MAX_OUTPUT_TOKENS,
        codex_cli_executable=executable, codex_cli_model=MODEL,
        codex_cli_reasoning_effort=EFFORT,
    )
    provider = build_provider(settings)
    if provider is None:
        _transition_status("halted", detail="provider_disabled")
        raise RuntimeError("Codex CLI provider composition is disabled.")
    app = create_app(settings, provider=_observed_provider(provider))

    from fastapi.responses import JSONResponse

    @app.on_event("startup")
    async def mark_runtime_running() -> None:
        _transition_status("running")

    @app.middleware("http")
    async def bounded_acceptance(request: Any, call_next: Any) -> Any:
        if request.method != "POST" or not request.url.path.endswith("/messages"):
            return await call_next(request)
        with LOCK:
            state_now = _private_file(_paths()[1])
        if state_now.get("status") != "running":
            return JSONResponse(status_code=423, content={"error": {"code": "acceptance_halted"}})
        try:
            body = await request.body()
            payload = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        if not isinstance(payload, dict) or not isinstance(payload.get("question"), str):
            return JSONResponse(status_code=400, content={"error": {"code": "semantic_turn_required"}})
        if "answer_only_receipt_id" in payload or "retry" in payload or "resume" in payload:
            return JSONResponse(status_code=400, content={"error": {"code": "retry_resume_disabled"}})
        try:
            number = _reserve_approved_guest_turn(payload["question"])
        except _UnapprovedGuestTurn:
            return JSONResponse(status_code=400, content={"error": {"code": "unapproved_guest_turn"}})
        except RuntimeError:
            return JSONResponse(status_code=429, content={"error": {"code": "acceptance_limit"}})
        turn = {"guest_turn": number, "calls": 0,
                "request_id": payload.get("request_id") if isinstance(payload.get("request_id"), str) else None,
                "synthetic_pinned": True}
        token = TURN.set(turn)
        started = time.monotonic()
        try:
            response = await call_next(request)
            status = response.status_code
            _event({"stage": "http_completed", "run_id": RUN_ID, "turn": number,
                    "status": status, "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "request_id_sha256": _hash(turn["request_id"])})
            if status >= 400 or turn["calls"] == 0:
                _transition_status("halted", detail="blocking_http_or_no_provider_call")
            return response
        except BaseException as exc:
            _event({"stage": "http_failed", "run_id": RUN_ID, "turn": number,
                    "exception_class": type(exc).__name__,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1)})
            _transition_status("halted", detail="blocking_http_exception")
            raise
        finally:
            TURN.reset(token)

    _event({"stage": "runtime_started", "run_id": RUN_ID, "provider": "codex_cli",
            "model": MODEL, "effort": EFFORT})
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18087)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("Sprint 7 acceptance runtime binds to loopback only.")
    try:
        import uvicorn
        uvicorn.run(create_runtime_app(), host=args.host, port=args.port, log_level="warning")
        _release_bootstrap_if_unused("server_stopped_before_first_reservation")
    except Exception as exc:  # noqa: BLE001 - every startup/server failure must attempt conservative bootstrap recovery.
        recovery_failure: str | None = None
        try:
            _release_bootstrap_if_unused(type(exc).__name__)
        except (OSError, RuntimeError) as recovery_exc:
            recovery_failure = type(recovery_exc).__name__
        recovery_note = f"; bootstrap recovery failed: {recovery_failure}" if recovery_failure else ""
        parser.exit(2, f"Sprint 7 runtime refused/failed: {type(exc).__name__}{recovery_note}\n")
    finally:
        _release_process_lease()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
