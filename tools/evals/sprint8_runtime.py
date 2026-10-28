"""Opt-in, fail-closed Sprint 8 local-guide acceptance runtime.

Import is offline. A live server requires separately prepared private 0600
authorization/config/state plus immutable candidate, case, oracle and source
pins. This module has no initialize/reset operation and never reads Sprint 7.
"""
from __future__ import annotations

import argparse
import asyncio
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

RUN_ID = "s8-local-guide-20261028-reacceptance1"
CASE_RUN_ID = "s8-local-guide-20261028-reacceptance1"
LIVE_ENV = "STAYLEAD_S8_LIVE_EVAL"
CONFIG_ENV = "STAYLEAD_S8_RUNTIME_CONFIG"
STATE_ENV = "STAYLEAD_S8_RUN_STATE"
EVENTS_ENV = "STAYLEAD_S8_RUNTIME_EVENTS"
CAPTURE_ENV = "STAYLEAD_S8_CAPTURE_SYNTHETIC_JSON"
MAX_TURNS, MAX_REQUESTS, MAX_CALLS_PER_TURN = 4, 8, 2
PROVIDER_TIMEOUT_SECONDS, TURN_TIMEOUT_SECONDS, MAX_OUTPUT_TOKENS = 25.0, 45.0, 700
MODEL, EFFORT = "gpt-6.1-sol", "low"
PROPOSED_CASES = Path("docs/product/evidence/sprint-8/acceptance-cases-proposed.json")
CANDIDATE_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs/product/evidence/sprint-8/candidate-manifest.json"
HARNESS_FILES = {
    "tools/evals/sprint8_runtime.py", "tools/evals/sprint8_browser.mjs",
    "tools/evals/sprint8_browser_helpers.mjs", "tests/contracts/test_sprint8_acceptance_harness.py",
}
TURN: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("sprint8_turn", default=None)
LOCK = threading.RLock()
LEASE_PATH = Path(f"/private/tmp/staylead-s8-{RUN_ID}.process.lock")
LEASE_FD: int | None = None


class UnapprovedTurn(RuntimeError):
    """The request does not match the next pinned utterance/session."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _private(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or not str(path).startswith("/private/tmp/"):
        raise RuntimeError("Sprint 8 control files must be under /private/tmp.")
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 1_048_576:
            raise RuntimeError("Sprint 8 control files must be regular 0600 files under 1 MiB.")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Sprint 8 private control file is missing or unreadable.") from exc
    if not isinstance(value, dict):
        raise TypeError("Sprint 8 control file must contain a JSON object.")
    return value


def _paths() -> tuple[Path, Path, Path]:
    config, state = os.environ.get(CONFIG_ENV), os.environ.get(STATE_ENV)
    if not config or not state:
        raise RuntimeError(f"Set {CONFIG_ENV} and {STATE_ENV} to approved private files.")
    events = os.environ.get(EVENTS_ENV, f"/private/tmp/staylead-s8-{RUN_ID}-events.jsonl")
    paths = Path(config), Path(state), Path(events)
    if any(not item.is_absolute() or not str(item).startswith("/private/tmp/") for item in paths):
        raise RuntimeError("Sprint 8 private paths must be under /private/tmp.")
    return paths


def _candidate_digest(files: dict[str, str]) -> str:
    raw = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return _sha(raw)


def _harness_digest(config: dict[str, Any]) -> str:
    value = {"files": config.get("harness_files"), "browser_executable": config.get("browser_executable")}
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _verify_pins(config: dict[str, Any]) -> None:
    manifest_path = CANDIDATE_MANIFEST_PATH
    try:
        info = manifest_path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > 2_097_152:
            raise RuntimeError("Unsafe or oversized Sprint 8 public candidate manifest.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Sprint 8 public candidate manifest is missing or unreadable.") from exc
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if (manifest.get("schema_version") != 1 or manifest.get("baseline") != "12122f7d012c0617670438de5419efdc3d7729ab"
            or manifest.get("branch") != "sprint-8-guide-shortlist"
            or manifest.get("hash_method") != "sha256(canonical JSON files map: sort_keys=True,separators=(comma,colon))"
            or manifest.get("scope") != "apps, fixtures, product tests; new acceptance harness excluded and separately pinned"
            or not isinstance(files, dict) or not files
            or manifest.get("candidate_sha256") != config.get("candidate_sha256")
            or manifest.get("sha256") != config.get("candidate_sha256")
            or _candidate_digest(files) != config.get("candidate_sha256")
            or manifest.get("browser_executable") != config.get("browser_executable")):
        raise RuntimeError("Sprint 8 candidate manifest pin changed or is malformed.")
    harness_files = config.get("harness_files")
    if not isinstance(harness_files, dict) or set(harness_files) != HARNESS_FILES:
        raise RuntimeError("Sprint 8 private config must pin exactly the four acceptance harness files.")
    root = Path(__file__).resolve().parents[2]
    for rel, expected in files.items():
        if not isinstance(rel, str) or not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise RuntimeError("Sprint 8 source pin is malformed.")
        unresolved = root / rel
        path = unresolved.resolve()
        if unresolved.is_symlink() or not path.is_relative_to(root) or not path.is_file() or _sha(path.read_bytes()) != expected:
            raise RuntimeError(f"Sprint 8 candidate input changed: {rel}")
    for rel, expected in harness_files.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise RuntimeError("Sprint 8 harness source pin is malformed.")
        path = (root / rel).resolve()
        if (rel not in HARNESS_FILES or (root / rel).is_symlink() or not path.is_relative_to(root)
                or not path.is_file() or _sha(path.read_bytes()) != expected):
            raise RuntimeError(f"Sprint 8 acceptance harness changed: {rel}")
    if (not re.fullmatch(r"[a-f0-9]{64}", str(config.get("case_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(config.get("oracle_sha256", "")))):
        raise RuntimeError("Sprint 8 case or oracle SHA-256 is malformed.")
    for key, expected in (("live_cases_path", config.get("case_sha256")), ("oracle_path", config.get("oracle_sha256"))):
        path = Path(config[key])
        _private(path)
        if _sha(path.read_bytes()) != expected:
            raise RuntimeError("Sprint 8 cases or independent oracle pin changed.")
    cases = json.loads(Path(config["live_cases_path"]).read_text(encoding="utf-8"))
    limits = cases.get("limits", {}) if isinstance(cases, dict) else {}
    wanted = {"guest_turns": MAX_TURNS, "requests": MAX_REQUESTS, "calls_per_turn": MAX_CALLS_PER_TURN,
              "provider_timeout_seconds": PROVIDER_TIMEOUT_SECONDS, "turn_timeout_seconds": TURN_TIMEOUT_SECONDS,
              "max_output_tokens": MAX_OUTPUT_TOKENS, "model": MODEL, "effort": EFFORT,
              "automatic_retry": False, "fallback": False, "stop_at_first_blocking_failure": True}
    rows = cases.get("cases", []) if isinstance(cases, dict) else []
    if (cases.get("run_id") != RUN_ID or cases.get("authorized_for_live_calls") is not True
            or limits != wanted or len(rows) != MAX_TURNS
            or [row.get("id") for row in rows] != [f"s8-0{i}" for i in range(1, 5)]
            or [row.get("session") for row in rows] != ["fresh-A", "fresh-B", "fresh-C", "same-C"]
            or cases.get("property") != {"hotel_id": "HTL-S8-DEMO", "slug": "lotus-pilot-demo"}
            or any(not isinstance(row.get("input"), str) or not row["input"] or len(row["input"]) > 2000 for row in rows)):
        raise RuntimeError("Sprint 8 live matrix is not an explicitly approved four-turn matrix.")


def _valid_state(state: dict[str, Any], config: dict[str, Any], *, fresh: bool = False) -> bool:
    profile = {"max_guest_turns": MAX_TURNS, "max_requests": MAX_REQUESTS,
               "max_calls_per_turn": MAX_CALLS_PER_TURN, "provider_timeout_seconds": PROVIDER_TIMEOUT_SECONDS,
               "turn_timeout_seconds": TURN_TIMEOUT_SECONDS, "max_output_tokens": MAX_OUTPUT_TOKENS,
               "model": MODEL, "effort": EFFORT, "automatic_retry": False, "fallback": False,
               "stop_at_first_blocking_failure": True}
    turns = state.get("guest_turns")
    sessions = state.get("sessions", {})
    expected_aliases = ["fresh-A", "fresh-B", "fresh-C"][:min(turns, 3)] if isinstance(turns, int) and not isinstance(turns, bool) else []
    sessions_valid = (isinstance(sessions, dict) and set(sessions) == set(expected_aliases)
                      and all(isinstance(value, str) and value for value in sessions.values())
                      and len(set(sessions.values())) == len(sessions))
    return (state.get("run_id") == config.get("run_id") == RUN_ID
            and config.get("authorized_for_live_calls") is True
            and all(config.get(key) == value for key, value in profile.items())
            and isinstance(config.get("authority"), str) and bool(config["authority"].strip())
            and state.get("authority") == config.get("authority")
            and isinstance(config.get("database_url"), str) and bool(config["database_url"])
            and isinstance(config.get("session_signing_secret"), str) and bool(config["session_signing_secret"])
            and state.get("authorized_for_live_calls") is True and state.get("status") in ({"authorized"} if fresh else {"authorized", "starting", "running", "halted", "completed"})
            and state.get("candidate_sha256") == config.get("candidate_sha256")
            and state.get("case_sha256") == config.get("case_sha256")
            and state.get("oracle_sha256") == config.get("oracle_sha256")
            and state.get("harness_sha256") == _harness_digest(config)
            and re.fullmatch(r"[a-f0-9]{64}", str(state.get("candidate_sha256", ""))) is not None
            and all(state.get(key) == value for key, value in profile.items())
            and state.get("guest_turns") == state.get("approved_case_turn")
            and isinstance(state.get("guest_turns"), int) and not isinstance(state.get("guest_turns"), bool) and 0 <= state["guest_turns"] <= MAX_TURNS
            and sessions_valid
            and isinstance(state.get("requests"), int) and not isinstance(state.get("requests"), bool) and 0 <= state["requests"] <= MAX_REQUESTS
            and (not fresh or (state.get("guest_turns") == state.get("requests") == 0 and state.get("status") == "authorized")))


def _acquire_lease() -> None:
    global LEASE_FD
    with LOCK:
        if LEASE_FD is not None:
            return
        if LEASE_PATH.is_symlink():
            raise RuntimeError("Unsafe Sprint 8 process lease path.")
        fd = os.open(LEASE_PATH, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise RuntimeError("Another Sprint 8 runtime holds the process lease.") from exc
        LEASE_FD = fd


def _release_lease() -> None:
    global LEASE_FD
    with LOCK:
        if LEASE_FD is not None:
            fcntl.flock(LEASE_FD, fcntl.LOCK_UN)
            os.close(LEASE_FD)
            LEASE_FD = None


def _save(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise RuntimeError("Sprint 8 state temporary file already exists.")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
    tmp.replace(path)
    path.chmod(0o600)


def _update(mutator: Any) -> dict[str, Any]:
    _, state_path, _ = _paths()
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    if lock_path.is_symlink():
        raise RuntimeError("Unsafe Sprint 8 state lock.")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        config = _private(_paths()[0]); state = _private(state_path)
        if not _valid_state(state, config) or state.get("status") not in {"authorized", "running"}:
            raise RuntimeError("Sprint 8 authorization/state is invalid or halted.")
        _verify_pins(config)
        mutator(state)
        _save(state_path, state)
        return state
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)


def reserve_turn(session_id: str, utterance: str) -> int:
    def mutate(state: dict[str, Any]) -> None:
        config = _private(_paths()[0]); cases = json.loads(Path(config["live_cases_path"]).read_text(encoding="utf-8"))
        idx = state["guest_turns"]
        if idx >= MAX_TURNS:
            raise RuntimeError("Sprint 8 guest-turn cap reached.")
        case = cases["cases"][idx]
        alias = case.get("session")
        actual_alias = "fresh-" + alias.removeprefix("same-") if isinstance(alias, str) and alias.startswith("same-") else alias
        bound = state.setdefault("sessions", {})
        if (case.get("input") != utterance
                or not isinstance(session_id, str) or not session_id
                or (actual_alias in bound and bound[actual_alias] != session_id)
                or (actual_alias not in bound and session_id in bound.values())):
            raise UnapprovedTurn("Request is not the exact next approved session and utterance.")
        bound[actual_alias] = session_id
        state["guest_turns"] += 1
        state["approved_case_turn"] += 1
        state["status"] = "running"
    result = _update(mutate)
    return result["guest_turns"]


def reserve_request() -> int:
    turn = TURN.get()
    if turn is None:
        raise RuntimeError("Provider call outside an approved Sprint 8 guest turn.")
    if turn["calls"] >= MAX_CALLS_PER_TURN:
        raise RuntimeError("Sprint 8 two-request-per-turn cap reached.")
    def mutate(state: dict[str, Any]) -> None:
        if state["requests"] >= MAX_REQUESTS:
            raise RuntimeError("Sprint 8 request cap reached.")
        state["requests"] += 1
    state = _update(mutate)
    turn["calls"] += 1
    return state["requests"]


def _log(record: dict[str, Any]) -> None:
    _, _, path = _paths()
    allowed = {"stage", "turn", "call", "status", "latency_ms", "request_sha256", "response_sha256", "exception_class"}
    safe = {key: record[key] for key in record.keys() & allowed}
    safe["run_id"] = RUN_ID
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("Unsafe Sprint 8 telemetry file.")
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as out:
        os.fchmod(out.fileno(), 0o600); out.write(json.dumps(safe, sort_keys=True) + "\n")


def _observed(provider: Any) -> Any:
    original = provider.generate
    async def generate(request: Any) -> Any:
        turn = TURN.get()
        if turn is None or not isinstance(request.max_output_tokens, int) or not 1 <= request.max_output_tokens <= MAX_OUTPUT_TOKENS:
            raise RuntimeError("Sprint 8 provider request violates the reserved turn/output cap.")
        reserve_request()  # persist before attempting provider call
        start = time.monotonic()
        try:
            async with asyncio.timeout(PROVIDER_TIMEOUT_SECONDS):
                result = await original(request)
        except BaseException as exc:
            _log({"stage": "provider_failed", "turn": turn["number"], "call": turn["calls"], "latency_ms": int((time.monotonic()-start)*1000), "exception_class": type(exc).__name__})
            _update(lambda state: state.update(status="halted"))
            raise
        _log({"stage": "provider_completed", "turn": turn["number"], "call": turn["calls"], "latency_ms": int((time.monotonic()-start)*1000), "response_sha256": _sha(result.text.encode())})
        return result
    provider.generate = generate
    return provider


def create_runtime_app() -> Any:
    if os.environ.get(LIVE_ENV) != "1":
        raise RuntimeError(f"Set {LIVE_ENV}=1 explicitly to enable live calls.")
    _acquire_lease()
    config_path, state_path, _ = _paths()
    config, state = _private(config_path), _private(state_path)
    if not _valid_state(state, config, fresh=True):
        raise RuntimeError("Sprint 8 run is not freshly authorized; API was not started.")
    _verify_pins(config)
    _update(lambda current: current.update(status="running"))
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("Codex CLI provider is unavailable.")
    from pydantic import SecretStr

    from staylead_platform.composition.configuration.settings import Settings
    from staylead_platform.composition.dependencies.guest_chat import build_provider
    from staylead_platform.entrypoints.app import create_app
    settings = Settings(_env_file=None, environment="development", database_url=config["database_url"],
        session_signing_secret=SecretStr(config["session_signing_secret"]), ai_provider="codex_cli",
        ai_timeout_seconds=PROVIDER_TIMEOUT_SECONDS, ai_turn_timeout_seconds=TURN_TIMEOUT_SECONDS,
        ai_max_output_tokens=MAX_OUTPUT_TOKENS, codex_cli_executable=executable,
        codex_cli_model=MODEL, codex_cli_reasoning_effort=EFFORT)
    provider = build_provider(settings)
    if provider is None:
        raise RuntimeError("Sprint 8 provider composition is disabled.")
    app = create_app(settings, provider=_observed(provider))
    from fastapi.responses import JSONResponse
    @app.middleware("http")
    async def bounded_acceptance(request: Any, call_next: Any) -> Any:
        if request.method != "POST" or not request.url.path.endswith("/messages"):
            return await call_next(request)
        try:
            body = await request.body()
            if len(body) > 4096:
                return JSONResponse(status_code=413, content={"error": {"code": "acceptance_payload_too_large"}})
            payload = json.loads(body) if body else {}
            parts = request.url.path.strip("/").split("/")
            session_id = parts[-2] if len(parts) >= 4 and parts[-1] == "messages" else None
            if not isinstance(payload, dict) or not isinstance(payload.get("question"), str) or not isinstance(session_id, str):
                return JSONResponse(status_code=400, content={"error": {"code": "approved_turn_required"}})
            if any(key in payload for key in ("retry", "resume", "answer_only_receipt_id")):
                return JSONResponse(status_code=400, content={"error": {"code": "retry_disabled"}})
            number = reserve_turn(session_id, payload["question"])
        except UnapprovedTurn:
            return JSONResponse(status_code=400, content={"error": {"code": "unapproved_turn"}})
        except RuntimeError:
            return JSONResponse(status_code=423, content={"error": {"code": "acceptance_halted"}})
        token = TURN.set({"number": number, "calls": 0})
        try:
            async with asyncio.timeout(TURN_TIMEOUT_SECONDS):
                response = await call_next(request)
            if response.status_code >= 400 or TURN.get()["calls"] == 0:
                _update(lambda state: state.update(status="halted"))
            return response
        except BaseException:
            _update(lambda state: state.update(status="halted")); raise
        finally:
            TURN.reset(token)
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=18088)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("Sprint 8 runtime binds to loopback only.")
    try:
        import uvicorn
        uvicorn.run(create_runtime_app(), host=args.host, port=args.port, log_level="warning")
    finally:
        _release_lease()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
