"""Bounded, opt-in Codex CLI runtime for Sprint 6 local acceptance.

This module does not call a provider on import or application startup. The live
server requires an explicit opt-in, an approved persistent run-state file, and
the private runtime config at ``/private/tmp/staylead-sprint6-runtime.json``.
The state file lives outside the repository so a process restart cannot reset
the 9-turn / 18-request counters.

Once execution is authorized and the coordinator has prepared the run-state::

    STAYLEAD_LIVE_EVAL=1 PYTHONPATH=apps/api/src \
      apps/api/.venv/bin/python docs/product/evidence/sprint-6/codex_acceptance_runtime.py \
      --host 127.0.0.1 --port 18086

No answer-only resume, retry endpoint, or resume counter is exposed here.
Every semantic ``/messages`` request reserves a persistent guest-turn slot;
every Codex invocation reserves a persistent request slot before launch.
Provider input/output and guest utterances are never written to telemetry.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
RUN_STATE = Path("/private/tmp/staylead-sprint6-run-state.json")
EVENTS = Path("/private/tmp/staylead-sprint6-runtime-events.jsonl")
RUNTIME = Path("/private/tmp/staylead-sprint6-runtime.json")
RUN_ID = "s6-codex-20261026"
MAX_REQUESTS = 18
MAX_GUEST_TURNS = 9
MAX_CALLS_PER_TURN = 2
PRIOR_GROK_ATTEMPTS = 8  # Frozen Sprint 5 history; never incremented here.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18086
MAX_OUTPUT_TOKENS = 700
LOCK = threading.Lock()
TURN = contextvars.ContextVar("sprint6_codex_turn", default=None)


def _event(item: dict[str, Any]) -> None:
    # Only fixed metadata, hashes, counts, statuses, and exception classes are
    # allowed into this file. Do not add request/response bodies or config.
    with LOCK, EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"unix_time": time.time(), **_redact(item)}, ensure_ascii=False) + "\n")


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in {
        "access_token", "authorization", "token", "session_token", "secret",
        "session_signing_secret", "database_url", "dsn", "api_key", "key1", "key2",
        "question", "message", "input_text", "output", "answer", "response", "body",
    }:
        return "<redacted>"
    if isinstance(value, dict):
        return {str(name): _redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)bearer\s+[^\s\",}]+", "Bearer <redacted>", value)
    return value


def _valid_counter(value: Any, limit: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= limit


def _load_state() -> dict[str, Any]:
    try:
        state = json.loads(RUN_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Approved Sprint 6 run state is missing or unreadable; API was not started.") from exc
    if (
        not isinstance(state, dict)
        or state.get("run_id") != RUN_ID
        or state.get("max_codex_requests") != MAX_REQUESTS
        or state.get("max_guest_turns") != MAX_GUEST_TURNS
        or state.get("max_calls_per_turn") != MAX_CALLS_PER_TURN
        or state.get("prior_grok_attempts") != PRIOR_GROK_ATTEMPTS
        or state.get("authorized_for_live_calls") is not True
        or not isinstance(state.get("authority"), str)
        or not state["authority"].strip()
        or not _valid_counter(state.get("codex_requests"), MAX_REQUESTS)
        or not _valid_counter(state.get("guest_turns"), MAX_GUEST_TURNS)
    ):
        raise SystemExit("Sprint 6 run state does not match the approved bounds; API was not started.")
    return state


def _save_state(state: dict[str, Any]) -> None:
    temporary = RUN_STATE.with_name(RUN_STATE.name + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(RUN_STATE)
    RUN_STATE.chmod(0o600)


def _reserve_counter(field: str, limit: int, label: str) -> int:
    with LOCK:
        state = _load_state()
        if state[field] >= limit:
            raise RuntimeError(f"Sprint 6 {label} limit reached; no request was sent.")
        state[field] += 1
        _save_state(state)
        return state[field]


def _reserve_provider_request() -> int:
    return _reserve_counter("codex_requests", MAX_REQUESTS, "Codex request")


def _reserve_guest_turn() -> int:
    return _reserve_counter("guest_turns", MAX_GUEST_TURNS, "guest turn")


def _safe_id(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", value):
        return value
    return None


def _codex_version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True,
            check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    value = result.stdout.strip()[:100]
    if result.returncode or not re.fullmatch(r"[A-Za-z0-9._+ -]{1,100}", value):
        return "unavailable"
    return value


def _observed_provider(provider: Any, cli_version: str) -> Any:
    original_generate = provider.generate
    metadata = provider.invocation_metadata

    async def generate(request: Any) -> Any:
        turn = TURN.get()
        if turn is None:
            raise RuntimeError("Sprint 6 provider call is outside a reserved guest turn.")
        if turn["calls"] >= MAX_CALLS_PER_TURN:
            raise RuntimeError("Sprint 6 two-Codex-requests-per-turn limit reached; no model request was made.")
        attempt = _reserve_provider_request()
        turn["calls"] += 1
        started = time.monotonic()
        input_bytes = request.input_text.encode("utf-8")
        instruction_bytes = request.instructions.encode("utf-8")
        common = {
            "provider_mode": "codex_cli",
            "run_id": RUN_ID,
            "attempt": attempt,
            "guest_turn": turn["guest_turn"],
            "turn_request_id": _safe_id(turn.get("request_id")),
            "turn_call": turn["calls"],
            "requested_model": metadata.get("model", "gpt-6-luna"),
            "reasoning_effort": metadata.get("reasoning_effort", "low"),
            "cli_version": cli_version,
            "request_shape": {
                "instructions_chars": len(request.instructions),
                "instructions_sha256": hashlib.sha256(instruction_bytes).hexdigest(),
                "input_chars": len(request.input_text),
                "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
                "max_output_tokens": request.max_output_tokens,
            },
        }
        _event({"stage": "provider_call_started", **common})
        try:
            result = await original_generate(request)
        except asyncio.CancelledError as exc:
            _event({"stage": "provider_call_cancelled", **common,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "exception_class": type(exc).__name__, "success": False})
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            safe_code = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", code) else None
            _event({"stage": "provider_call_failed", **common,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "exception_class": type(exc).__name__, "provider_error_code": safe_code,
                    "success": False})
            raise
        _event({
            "stage": "provider_call_completed", **common,
            "provider": result.provider,
            "deployment": result.deployment,
            "actual_model": "unreported",
            "provider_turn_id": _safe_id(result.request_id),
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "usage": asdict(result.usage),
            "output_chars": len(result.text),
            "output_sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
            "success": True,
        })
        return result

    provider.generate = generate
    return provider


def create_runtime_app() -> Any:
    if os.environ.get("STAYLEAD_LIVE_EVAL") != "1":
        raise SystemExit("Sprint 6 acceptance requires explicit STAYLEAD_LIVE_EVAL=1.")
    _load_state()
    try:
        runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Private runtime config is missing or unreadable; API was not started.") from exc
    if not isinstance(runtime, dict) or not runtime.get("database_url") or not runtime.get("session_signing_secret"):
        raise SystemExit("Private runtime config is incomplete; API was not started.")

    executable = shutil.which("codex")
    if not executable:
        raise SystemExit("The existing local Codex CLI is unavailable; API was not started.")
    cli_version = _codex_version(executable)

    from pydantic import SecretStr
    from staylead_platform.composition.configuration.settings import Settings
    from staylead_platform.composition.dependencies.guest_chat import build_provider
    from staylead_platform.entrypoints.app import create_app

    settings = Settings(
        _env_file=None,
        environment="development",
        database_url=runtime["database_url"],
        session_signing_secret=SecretStr(runtime["session_signing_secret"]),
        ai_provider="codex_cli",
        ai_timeout_seconds=25.0,
        ai_turn_timeout_seconds=45.0,
        ai_max_output_tokens=MAX_OUTPUT_TOKENS,
        codex_cli_executable=executable,
        codex_cli_model="gpt-6-luna",
        codex_cli_reasoning_effort="low",
    )
    selected_provider = build_provider(settings)
    if selected_provider is None:
        raise SystemExit("Codex provider composition is disabled; API was not started.")
    app = create_app(settings, provider=_observed_provider(selected_provider, cli_version))

    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def acceptance_events(request: Any, call_next: Any) -> Any:
        is_message = request.method == "POST" and request.url.path.endswith("/messages")
        turn: dict[str, Any] | None = None
        token = None
        if is_message:
            try:
                body = await request.body()
                payload = json.loads(body) if body else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = None
            # Replay/resume, retry, and non-semantic requests cannot consume
            # this fresh acceptance allowance or bypass its turn accounting.
            if not isinstance(payload, dict) or payload.get("question") is None:
                return JSONResponse(status_code=400, content={"error": {"code": "acceptance_semantic_turn_required"}})
            if any(key in payload for key in ("answer_only_receipt_id", "resume", "retry")):
                return JSONResponse(status_code=400, content={"error": {"code": "acceptance_resume_disabled"}})
            try:
                guest_turn = _reserve_guest_turn()
            except RuntimeError:
                return JSONResponse(status_code=429, content={"error": {"code": "acceptance_limit"}})
            turn = {
                "calls": 0,
                "request_id": _safe_id(payload.get("request_id")),
                "guest_turn": guest_turn,
            }
            token = TURN.set(turn)
        started = time.monotonic()
        try:
            response = await call_next(request)
            if turn is not None:
                _event({
                    "stage": "http",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "provider_mode": "codex_cli",
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "guest_turn": turn["guest_turn"],
                    "turn_request_id": turn["request_id"],
                    "provider_calls_in_turn": turn["calls"],
                })
            return response
        finally:
            if token is not None:
                TURN.reset(token)

    _event({
        "stage": "runtime_started", "provider_mode": "codex_cli", "run_id": RUN_ID,
        "model": "gpt-6-luna", "reasoning_effort": "low", "cli_version": cli_version,
        "max_codex_requests": MAX_REQUESTS, "max_guest_turns": MAX_GUEST_TURNS,
        "max_calls_per_turn": MAX_CALLS_PER_TURN,
    })
    return app


def _initialize_state(authority: str) -> None:
    if not authority.strip():
        raise SystemExit("An explicit approval reference is required to initialize live run state.")
    if RUN_STATE.exists():
        raise SystemExit("Sprint 6 run state already exists; counters cannot be reset.")
    state = {
        "run_id": RUN_ID,
        "max_codex_requests": MAX_REQUESTS,
        "codex_requests": 0,
        "max_guest_turns": MAX_GUEST_TURNS,
        "guest_turns": 0,
        "max_calls_per_turn": MAX_CALLS_PER_TURN,
        "prior_grok_attempts": PRIOR_GROK_ATTEMPTS,
        "authorized_for_live_calls": True,
        "authority": authority.strip(),
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    _save_state(state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--initialize-state", action="store_true", help="Initialize once after fresh live-run approval.")
    parser.add_argument("--authority", default="", help="Short approval reference; never put secrets here.")
    args = parser.parse_args()
    if args.initialize_state:
        _initialize_state(args.authority)
        return
    if args.authority:
        raise SystemExit("--authority is only accepted with --initialize-state.")
    import uvicorn
    uvicorn.run(create_runtime_app(), host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
