"""Opt-in local Codex CLI runtime for the Sprint 5 browser acceptance.

Run from the repository root after the coordinator has prepared the private
runtime config and approved ``codex-run-state.json``::

    STAYLEAD_LIVE_EVAL=1 PYTHONPATH=apps/api/src \
      apps/api/.venv/bin/python docs/product/evidence/sprint-5/codex_acceptance_runtime.py \
      --host 127.0.0.1 --port 18085

The API uses the existing production routes and persistence path. It reads the
private runtime file in memory, starts no model call at startup, and records
sanitized per-call telemetry in ``codex-runtime-events.jsonl``. Four semantic
guest turns, eight Codex invocations total, and two invocations per turn are
persisted bounds. Answer-only recovery requests are counted separately.
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
RUN_STATE = BASE / "codex-run-state.json"
EVENTS = BASE / "codex-runtime-events.jsonl"
RUNTIME = Path("/tmp/staylead-sprint5-runtime.json")
RUN_ID = "s5-codex-90-20261023"
MAX_REQUESTS = 8
MAX_SEMANTIC_TURNS = 4
MAX_CALLS_PER_TURN = 2
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18085
LOCK = threading.Lock()
TURN = contextvars.ContextVar("sprint5_codex_turn", default=None)


def _event(item: dict[str, Any]) -> None:
    with LOCK, EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"unix_time": time.time(), **item}, ensure_ascii=False) + "\n")


def _load_state() -> dict[str, Any]:
    try:
        state = json.loads(RUN_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Approved Codex acceptance state is missing or unreadable; API was not started.") from exc
    if (
        not isinstance(state, dict)
        or state.get("run_id") != RUN_ID
        or state.get("max_codex_requests") != MAX_REQUESTS
        or state.get("prior_grok_attempts") != 8
        or not isinstance(state.get("codex_requests"), int)
        or isinstance(state.get("codex_requests"), bool)
        or not 0 <= state["codex_requests"] <= MAX_REQUESTS
        or not isinstance(state.get("semantic_guest_turns"), int)
        or isinstance(state.get("semantic_guest_turns"), bool)
        or not 0 <= state["semantic_guest_turns"] <= MAX_SEMANTIC_TURNS
        or not isinstance(state.get("answer_only_resumes"), int)
        or isinstance(state.get("answer_only_resumes"), bool)
        or state["answer_only_resumes"] < 0
        or not isinstance(state.get("authority"), str)
    ):
        raise SystemExit("Codex acceptance state does not match the approved bounded run; API was not started.")
    return state


def _save_state(state: dict[str, Any]) -> None:
    temporary = RUN_STATE.with_name(RUN_STATE.name + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(RUN_STATE)


def _reserve_counter(field: str, limit: int, label: str) -> int:
    with LOCK:
        state = _load_state()
        if state[field] >= limit:
            raise RuntimeError(f"Sprint 5 {label} limit reached; no request was sent.")
        state[field] += 1
        _save_state(state)
        return state[field]


def _reserve_provider_request() -> int:
    return _reserve_counter("codex_requests", MAX_REQUESTS, "Codex request")


def _reserve_semantic_turn() -> int:
    return _reserve_counter("semantic_guest_turns", MAX_SEMANTIC_TURNS, "semantic guest turn")


def _reserve_resume() -> int:
    # Recovery is separately observable and does not consume one of four new turns.
    with LOCK:
        state = _load_state()
        state["answer_only_resumes"] += 1
        _save_state(state)
        return state["answer_only_resumes"]


def _safe_id(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", value):
        return value
    return None


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in {
        "access_token", "authorization", "token", "session_token", "secret",
        "session_signing_secret", "database_url", "dsn", "api_key", "key1", "key2",
    }:
        return "<redacted>"
    if isinstance(value, dict):
        return {str(name): _redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)bearer\s+[^\s\",}]+", "Bearer <redacted>", value)
    return value


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
            turn = {"calls": 0, "request_id": None, "kind": "untracked"}
            TURN.set(turn)
        if turn["calls"] >= MAX_CALLS_PER_TURN:
            raise RuntimeError("Sprint 5 two-Codex-requests-per-turn limit reached; no model request was made.")
        attempt = _reserve_provider_request()
        turn["calls"] += 1
        started = time.monotonic()
        input_bytes = request.input_text.encode("utf-8")
        instruction_bytes = request.instructions.encode("utf-8")
        common = {
            "provider_mode": "codex_cli",
            "run_id": RUN_ID,
            "attempt": attempt,
            "semantic_guest_turn": turn.get("semantic_guest_turn"),
            "turn_kind": turn["kind"],
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
            _event({
                "stage": "provider_call_cancelled", **common,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "exception_class": type(exc).__name__, "success": False,
            })
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            safe_code = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", code) else None
            _event({
                "stage": "provider_call_failed", **common,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "exception_class": type(exc).__name__, "provider_error_code": safe_code,
                "success": False,
            })
            raise
        output_bytes = result.text.encode("utf-8")
        _event({
            "stage": "provider_call_completed", **common,
            "provider": result.provider,
            "deployment": result.deployment,
            "actual_model": "unreported",
            "provider_turn_id": _safe_id(result.request_id),
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "usage": asdict(result.usage),
            "output_chars": len(result.text),
            "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "success": True,
        })
        return result

    provider.generate = generate
    return provider


def create_runtime_app() -> Any:
    if os.environ.get("STAYLEAD_LIVE_EVAL") != "1":
        raise SystemExit("Codex acceptance requires explicit STAYLEAD_LIVE_EVAL=1.")
    _load_state()
    if not RUNTIME.is_file():
        raise SystemExit("Private runtime config is missing; API was not started.")
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
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
        codex_cli_executable=executable,
        codex_cli_model="gpt-6-luna",
        codex_cli_reasoning_effort="low",
    )
    selected_provider = build_provider(settings)
    if selected_provider is None:
        raise SystemExit("Codex provider composition is disabled; API was not started.")
    provider = _observed_provider(selected_provider, cli_version)
    app = create_app(settings, provider=provider)

    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def acceptance_events(request: Any, call_next: Any) -> Any:
        body = await request.body()
        delivered = False

        async def receive() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        request._receive = receive
        is_message = request.method == "POST" and request.url.path.endswith("/messages")
        payload: dict[str, Any] = {}
        try:
            parsed = json.loads(body) if body else {}
            if isinstance(parsed, dict):
                payload = parsed
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        turn: dict[str, Any] | None = None
        token = None
        if is_message:
            request_id = _safe_id(payload.get("request_id"))
            if payload.get("answer_only_receipt_id"):
                kind = "answer_only_resume"
                try:
                    resume = _reserve_resume()
                except RuntimeError:
                    return JSONResponse(status_code=429, content={"error": {"code": "acceptance_limit"}})
                turn = {"calls": 0, "request_id": request_id, "kind": kind, "resume": resume}
            elif payload.get("question") is not None:
                kind = "semantic_guest_turn"
                try:
                    semantic_turn = _reserve_semantic_turn()
                except RuntimeError:
                    return JSONResponse(status_code=429, content={"error": {"code": "acceptance_limit"}})
                turn = {
                    "calls": 0, "request_id": request_id,
                    "kind": kind, "semantic_guest_turn": semantic_turn,
                }
            if turn is not None:
                token = TURN.set(turn)
        started = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            chunks = [chunk async for chunk in response.body_iterator]
            response_body = b"".join(chunks)
            item: dict[str, Any] = {
                "stage": "http", "method": request.method, "path": request.url.path,
                "status": status, "provider_mode": "codex_cli",
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
            }
            if turn is not None:
                item.update({
                    "turn_kind": turn["kind"],
                    "turn_request_id": _safe_id(turn.get("request_id")),
                    "provider_calls_in_turn": turn["calls"],
                })
                if "semantic_guest_turn" in turn:
                    item["semantic_guest_turn"] = turn["semantic_guest_turn"]
                if "resume" in turn:
                    item["answer_only_resume"] = turn["resume"]
                try:
                    decoded_response: Any = json.loads(response_body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    decoded_response = {"bytes": len(response_body)}
                item["response"] = _redact(decoded_response)
            _event(item)
            from starlette.responses import Response
            return Response(
                content=response_body, status_code=status,
                headers={key: value for key, value in response.headers.items()
                         if key.lower() not in {"content-length", "transfer-encoding"}},
                media_type=response.media_type,
            )
        finally:
            if token is not None:
                TURN.reset(token)

    _event({
        "stage": "runtime_started", "provider_mode": "codex_cli",
        "run_id": RUN_ID, "model": "gpt-6-luna", "reasoning_effort": "low",
        "cli_version": cli_version, "max_codex_requests": MAX_REQUESTS,
        "max_semantic_guest_turns": MAX_SEMANTIC_TURNS,
        "max_calls_per_turn": MAX_CALLS_PER_TURN,
    })
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_runtime_app(), host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
