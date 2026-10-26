"""Bounded, opt-in Codex CLI runtime for the resumed Sprint 6 acceptance batch.

This module does not call a provider on import or application startup. The live
server requires an explicit opt-in, an approved persistent run-state file, and
the private runtime config at ``/private/tmp/staylead-sprint6-remediation-runtime.json``.
This namespace is distinct from the immutable original run; its fresh counters
are 9 guest turns / 18 Codex requests.

Once execution is authorized and the coordinator has prepared the run-state::

    STAYLEAD_LIVE_EVAL=1 PYTHONPATH=apps/api/src \
      apps/api/.venv/bin/python docs/product/evidence/sprint-6/remediation/resumed_acceptance_runtime.py \
      --host 127.0.0.1 --port 18086

Answer-only resume is disabled by default and requires the explicit local
``STAYLEAD_S6_OPERATOR_RESUME=1`` start flag. An operator-approved resume gets
its own persistent reservation and does not consume a semantic guest-turn slot.
Every Codex invocation reserves a persistent request slot before launch.
Provider input/output and guest utterances are never written to telemetry.
Synthetic JSON output capture is separate, explicit opt-in, capped at 64 KiB,
and restricted to a private /private/tmp file with mode 0600.
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
MATRIX_PATH = BASE.parent / "live-cases.json"
RUN_STATE = Path("/private/tmp/staylead-sprint6-remediation-run-state.json")
EVENTS = Path("/private/tmp/staylead-sprint6-remediation-runtime-events.jsonl")
RUNTIME = Path("/private/tmp/staylead-sprint6-remediation-runtime.json")
CAPTURE_DIR = Path("/private/tmp/staylead-sprint6-remediation-synthetic-output")
RUN_ID = "s6-codex-20261026-remediation-1"
MATRIX_ID = "staylead-s6-nine-turn-multilingual-20261026-v1"
MAX_REQUESTS = 18
MAX_GUEST_TURNS = 9
MAX_CALLS_PER_TURN = 2
MAX_ANSWER_ONLY_RESUMES = 18
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
        or state.get("max_answer_only_resumes") != MAX_ANSWER_ONLY_RESUMES
        or state.get("prior_grok_attempts") != PRIOR_GROK_ATTEMPTS
        or state.get("authorized_for_live_calls") is not True
        or not isinstance(state.get("authority"), str)
        or not state["authority"].strip()
        or not _valid_counter(state.get("codex_requests"), MAX_REQUESTS)
        or not _valid_counter(state.get("guest_turns"), MAX_GUEST_TURNS)
        or not _valid_counter(state.get("answer_only_resumes"), MAX_ANSWER_ONLY_RESUMES)
        or not isinstance(state.get("answer_only_receipt_hashes"), list)
        or len(state["answer_only_receipt_hashes"]) != state["answer_only_resumes"]
        or any(not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{64}", item) for item in state["answer_only_receipt_hashes"])
        or len(set(state["answer_only_receipt_hashes"])) != len(state["answer_only_receipt_hashes"])
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


def _reserve_answer_only_resume(receipt_id: Any) -> tuple[int, int]:
    if not isinstance(receipt_id, str) or not 1 <= len(receipt_id) <= 512:
        raise RuntimeError("An answer-only receipt is required for operator resume.")
    receipt_hash = hashlib.sha256(receipt_id.encode("utf-8")).hexdigest()
    with LOCK:
        state = _load_state()
        if state["guest_turns"] < 1:
            raise RuntimeError("An answer-only resume requires a prior semantic guest turn.")
        if receipt_hash in state["answer_only_receipt_hashes"]:
            raise RuntimeError("This answer-only receipt was already reserved; no retry was sent.")
        if state["answer_only_resumes"] >= MAX_ANSWER_ONLY_RESUMES:
            raise RuntimeError("Sprint 6 answer-only resume reservation limit reached.")
        state["answer_only_resumes"] += 1
        state["answer_only_receipt_hashes"].append(receipt_hash)
        _save_state(state)
        return state["answer_only_resumes"], state["guest_turns"]


def _identifier_hash(value: Any) -> str | None:
    if isinstance(value, str) and 1 <= len(value) <= 200:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return None


def _safe_validation_diagnostics(value: Any) -> dict[str, Any] | None:
    """Keep stable validation locations/types, never model values or context."""
    if not isinstance(value, dict) or value.get("code") != "model_validation":
        return None
    errors = value.get("errors")
    count = value.get("error_count")
    if (not isinstance(errors, list) or len(errors) > 64 or
            not isinstance(count, int) or isinstance(count, bool) or
            count < len(errors) or count > 10000):
        return None
    safe_errors = []
    for error in errors:
        if not isinstance(error, dict) or not isinstance(error.get("loc"), list):
            return None
        loc = []
        for segment in error["loc"][:12]:
            if isinstance(segment, int) and not isinstance(segment, bool) and 0 <= segment <= 10000:
                loc.append(segment)
            elif isinstance(segment, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}|<key>", segment):
                loc.append(segment)
            else:
                return None
        error_type = error.get("type")
        if not isinstance(error_type, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", error_type):
            return None
        safe_errors.append({"loc": loc, "type": error_type})
    return {"code": "model_validation", "error_count": count, "errors": safe_errors}


def _capture_synthetic_json(text: str, common: dict[str, Any]) -> dict[str, Any]:
    """Write opt-in pinned-matrix output to a private bounded replay artifact."""
    if (os.environ.get("STAYLEAD_S6_CAPTURE_SYNTHETIC_JSON") != "1" or
            os.environ.get("STAYLEAD_S6_SYNTHETIC_MATRIX_ID") != MATRIX_ID or
            common.get("synthetic_pinned") is not True):
        return {"capture_status": "disabled"}
    encoded = text.encode("utf-8")
    if len(encoded) > 64 * 1024:
        return {"capture_status": "rejected_over_64kib", "response_bytes": len(encoded)}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"capture_status": "rejected_not_json", "response_bytes": len(encoded)}
    capture_file = CAPTURE_DIR / f"output-{int(common.get('attempt', 0)):02d}.json"
    if capture_file.exists():
        return {"capture_status": "refused_existing_capture", "response_bytes": len(encoded)}
    record = {
        "run_id": RUN_ID,
        "matrix_id": MATRIX_ID,
        "guest_turn": common.get("guest_turn"),
        "attempt": common.get("attempt"),
        "synthetic_only": True,
        "request_sha256": common.get("request_shape", {}).get("input_sha256"),
        "prompt_sha256": common.get("request_shape", {}).get("instructions_sha256"),
        "response_bytes": len(encoded),
        "response_sha256": hashlib.sha256(encoded).hexdigest(),
        "body_text": text,
        "body_json": parsed,
    }
    CAPTURE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with capture_file.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    capture_file.chmod(0o600)
    return {"capture_status": "captured_private", "capture_bytes": len(encoded), "capture_file": capture_file.name}


def _is_pinned_synthetic_turn(turn_number: int, question: Any) -> bool:
    if not isinstance(question, str) or not 1 <= turn_number <= MAX_GUEST_TURNS:
        return False
    try:
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        turns = matrix.get("turns") if matrix.get("matrix_id") == MATRIX_ID else None
        return isinstance(turns, list) and len(turns) == MAX_GUEST_TURNS and turns[turn_number - 1].get("utterance") == question
    except (OSError, json.JSONDecodeError, AttributeError, IndexError, TypeError):
        return False


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
            "turn_request_id_sha256": _identifier_hash(turn.get("request_id")),
            "turn_call": turn["calls"],
            "synthetic_pinned": turn.get("synthetic_pinned") is True,
            "answer_only_resume": turn.get("answer_only_resume") is True,
            "resume_reservation": turn.get("resume_reservation"),
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
            diagnostics = _safe_validation_diagnostics(getattr(exc, "validation_diagnostics", None))
            _event({"stage": "provider_call_failed", **common,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "exception_class": type(exc).__name__, "provider_error_code": safe_code,
                    "validation_diagnostics": diagnostics,
                    "success": False})
            raise
        capture = _capture_synthetic_json(result.text, common)
        _event({
            "stage": "provider_call_completed", **common,
            "provider": result.provider,
            "deployment": result.deployment,
            "actual_model": "unreported",
            "provider_turn_id_sha256": _identifier_hash(result.request_id),
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "usage": asdict(result.usage),
            "output_chars": len(result.text),
            "output_sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
            **capture,
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
        validation_diagnostics=os.environ.get("STAYLEAD_VALIDATION_DIAGNOSTICS") == "true",
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
            if not isinstance(payload, dict):
                return JSONResponse(status_code=400, content={"error": {"code": "acceptance_semantic_turn_required"}})
            if any(key in payload for key in ("resume", "retry")):
                return JSONResponse(status_code=400, content={"error": {"code": "acceptance_resume_disabled"}})
            answer_only_receipt_id = payload.get("answer_only_receipt_id")
            if answer_only_receipt_id is not None:
                if os.environ.get("STAYLEAD_S6_OPERATOR_RESUME") != "1":
                    return JSONResponse(status_code=400, content={"error": {"code": "acceptance_operator_resume_disabled"}})
                try:
                    resume_reservation, guest_turn = _reserve_answer_only_resume(answer_only_receipt_id)
                except RuntimeError as exc:
                    code = "acceptance_limit" if "limit reached" in str(exc) else "acceptance_resume_rejected"
                    return JSONResponse(status_code=429 if code == "acceptance_limit" else 409, content={"error": {"code": code}})
                _event({
                    "stage": "answer_only_resume_reserved",
                    "run_id": RUN_ID,
                    "resume_reservation": resume_reservation,
                    "guest_turn": guest_turn,
                    "receipt_sha256": hashlib.sha256(answer_only_receipt_id.encode("utf-8")).hexdigest(),
                })
                turn = {
                    "calls": 0,
                    "request_id": payload.get("request_id") if isinstance(payload.get("request_id"), str) else None,
                    "guest_turn": guest_turn,
                    "synthetic_pinned": False,
                    "answer_only_resume": True,
                    "resume_reservation": resume_reservation,
                }
            else:
                if payload.get("question") is None:
                    return JSONResponse(status_code=400, content={"error": {"code": "acceptance_semantic_turn_required"}})
                try:
                    guest_turn = _reserve_guest_turn()
                except RuntimeError:
                    return JSONResponse(status_code=429, content={"error": {"code": "acceptance_limit"}})
                turn = {
                    "calls": 0,
                    "request_id": payload.get("request_id") if isinstance(payload.get("request_id"), str) else None,
                    "guest_turn": guest_turn,
                    "synthetic_pinned": _is_pinned_synthetic_turn(guest_turn, payload.get("question")),
                    "answer_only_resume": False,
                    "resume_reservation": None,
                }
            token = TURN.set(turn)
        started = time.monotonic()
        try:
            response = await call_next(request)
            if turn is not None:
                _event({
                    "stage": "http_answer_only_resume" if turn.get("answer_only_resume") else "http",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "provider_mode": "codex_cli",
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "guest_turn": turn["guest_turn"],
                    "turn_request_id_sha256": _identifier_hash(turn["request_id"]),
                    "provider_calls_in_turn": turn["calls"],
                    "resume_reservation": turn.get("resume_reservation"),
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
        "max_answer_only_resumes": MAX_ANSWER_ONLY_RESUMES,
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
        "max_answer_only_resumes": MAX_ANSWER_ONLY_RESUMES,
        "answer_only_resumes": 0,
        "answer_only_receipt_hashes": [],
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
