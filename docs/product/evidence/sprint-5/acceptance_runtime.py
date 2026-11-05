"""Sprint 5 local acceptance API; offline fake by default, live mode is opt-in.

Manual use from the repository root::

    PYTHONPATH=apps/api/src python3 docs/product/evidence/sprint-5/acceptance_runtime.py fake
    STAYLEAD_LIVE_EVAL=1 PYTHONPATH=apps/api/src python3 docs/product/evidence/sprint-5/acceptance_runtime.py live
    STAYLEAD_LIVE_EVAL=1 PYTHONPATH=apps/api/src python3 docs/product/evidence/sprint-5/acceptance_runtime.py diagnostic

Fake controls live in ``/tmp/staylead-sprint5-control.json``. Set
``{"hide_completed_response_once":true}`` to deliver one retryable 503 after
the API has completed a request; replay the same request ID to observe its stored
result. ``{"fail_postapply_answer":true}`` injects one post-apply answer failure,
and ``{"response_delay_seconds":N}`` delays message responses by at most 30 seconds.
The completion fault is rejected in live mode. The remediation state persists a
four-semantic-turn cap; answer-only receipt resumes are counted separately and do
not consume a semantic turn. Runtime credentials are read from the existing private
``/tmp/staylead-sprint5-runtime.json`` file.
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
EVENTS = BASE / "runtime-events.jsonl"
REMEDIATION_EVENTS = BASE / "remediation-runtime-events.jsonl"
RUNTIME = Path("/tmp/staylead-sprint5-runtime.json")
CONTROL = Path("/tmp/staylead-sprint5-control.json")
RUN_STATE = BASE / "remediation-run-state.json"
REMEDIATION_RUN_ID = "s5-r2-90-20261023"
ADDITIONAL_ATTEMPT_LIMIT = 8
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18085
LOCK = threading.Lock()
TURN = contextvars.ContextVar("sprint5_turn", default=None)
HTTPX_TRACE_EVENTS = contextvars.ContextVar("sprint5_httpx_trace_events", default=None)
HTTPX_TRACE_START = contextvars.ContextVar("sprint5_httpx_trace_start", default=None)
TOTAL_PROVIDER_CALLS = 0


def event(item: dict[str, Any]) -> None:
    is_remediation = item.get("provider_mode") == "live" or str(item.get("stage", "")).startswith("live_")
    path = REMEDIATION_EVENTS if is_remediation else EVENTS
    with LOCK, path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"unix_time": time.time(), **item}, ensure_ascii=False) + "\n")


def _load_run_state() -> dict[str, Any]:
    try:
        value = json.loads(RUN_STATE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit("Approved remediation run state is missing; live mode was not started.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Approved remediation run state is unreadable; live mode was not started.") from exc
    if (
        not isinstance(value, dict)
        or value.get("run_id") != REMEDIATION_RUN_ID
        or value.get("max_additional_attempts") != ADDITIONAL_ATTEMPT_LIMIT
        or value.get("prior_attempts") != 1
        or not isinstance(value.get("observed_attempts"), int)
        or isinstance(value.get("observed_attempts"), bool)
        or value["observed_attempts"] < 0
        or value["observed_attempts"] > ADDITIONAL_ATTEMPT_LIMIT
        or not isinstance(value.get("semantic_guest_turns"), int)
        or isinstance(value.get("semantic_guest_turns"), bool)
        or value["semantic_guest_turns"] < 0
        or value["semantic_guest_turns"] > 4
        or not isinstance(value.get("answer_only_resumes", 0), int)
        or isinstance(value.get("answer_only_resumes", 0), bool)
        or value.get("answer_only_resumes", 0) < 0
    ):
        raise SystemExit("Approved remediation run state does not match this bounded run; live mode was not started.")
    return value


def _write_run_state(state: dict[str, Any]) -> None:
    temp_path = RUN_STATE.with_name(RUN_STATE.name + ".tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(RUN_STATE)


def _reserve_provider_attempt() -> int:
    """Persist one additional observed call immediately before invoking the provider."""
    with LOCK:
        state = _load_run_state()
        if state["observed_attempts"] >= state["max_additional_attempts"]:
            raise RuntimeError("Sprint 5 additional provider-attempt limit reached; no provider call was made.")
        state["observed_attempts"] += 1
        _write_run_state(state)
        return state["observed_attempts"]


def _reserve_semantic_turn() -> int:
    with LOCK:
        state = _load_run_state()
        if state["semantic_guest_turns"] >= 4:
            raise RuntimeError("Sprint 5 four-semantic-turn limit reached; no message was sent to the API.")
        state["semantic_guest_turns"] += 1
        _write_run_state(state)
        return state["semantic_guest_turns"]


def _reserve_answer_only_resume() -> int:
    with LOCK:
        state = _load_run_state()
        state["answer_only_resumes"] = state.get("answer_only_resumes", 0) + 1
        _write_run_state(state)
        return state["answer_only_resumes"]


def _safe_request_id(value: Any) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", value):
        return None
    return value


def _live_failure_event(
    exc: BaseException, *, attempt: int, turn_call: int, started_at: float,
    trace_events: list[dict[str, Any]], cancelled: bool = False,
) -> None:
    failure: dict[str, Any] = {
        "stage": "live_provider_cancelled" if cancelled else "live_provider_failure",
        "provider_mode": "live", "run_id": REMEDIATION_RUN_ID,
        "attempt": attempt, "turn_call": turn_call, "provider": "foundry_grok",
        "exception_class": type(exc).__name__,
        "latency_ms": round((time.monotonic() - started_at) * 1000, 1),
        "usage": "unknown", "httpx_trace": trace_events[:100],
    }
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        cause_class = type(cause).__name__
        cause_module = type(cause).__module__
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", cause_class):
            failure["cause_class"] = cause_class
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,199}", cause_module):
            failure["cause_module"] = cause_module
    error_code = getattr(exc, "code", None)
    if isinstance(error_code, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", error_code):
        failure["provider_error_code"] = error_code
    retryable = getattr(exc, "retryable", None)
    if isinstance(retryable, bool):
        failure["retryable"] = retryable
    status = getattr(exc, "status_code", getattr(exc, "status", None))
    if isinstance(status, int) and 100 <= status <= 599:
        failure["provider_status"] = status
    provider_request_id = _safe_request_id(getattr(exc, "request_id", None))
    if provider_request_id:
        failure["provider_request_id"] = provider_request_id
    event(failure)


def controls() -> dict[str, Any]:
    try:
        value = json.loads(CONTROL.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def redact(value: Any, key: str = "") -> Any:
    if key.lower() in {
        "access_token", "authorization", "token", "secret", "session_signing_secret",
        "database_url", "dsn", "api_key", "key1", "key2",
    }:
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)bearer\s+[^\s\",}]+", "Bearer <redacted>", value)
    return value


def _parse_input(request: Any) -> dict[str, Any]:
    try:
        data = json.loads(request.input_text)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _brief_data(payload: dict[str, Any]) -> dict[str, Any]:
    brief = payload.get("guest_brief") or {}
    return brief.get("data") or {}


def _question(payload: dict[str, Any]) -> str:
    return str(payload.get("question") or payload.get("current_question") or "")


def _dates(question: str) -> list[str]:
    found: list[str] = []
    for value in re.findall(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", question):
        try:
            found.append(date(int(value[0]), int(value[1]), int(value[2])).isoformat())
        except ValueError:
            pass
    if found:
        return found
    for value in re.findall(
        r"(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(20\d{2})", question, re.IGNORECASE,
    ):
        try:
            found.append(date(int(value[2]), int(value[1]), int(value[0])).isoformat())
        except ValueError:
            pass
    return found


def _proposal(question: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return explicit operations for the four authored acceptance utterances."""
    normalized = question.lower()
    dates = _dates(question)
    brief = _brief_data(payload)
    party = brief.get("party") or {}
    children = party.get("children") or []
    operations: list[dict[str, Any]] = []

    if any(word in normalized for word in ("bỏ trẻ", "bỏ em bé", "bỏ bé", "remove child")):
        if len(children) == 1:
            operations.append({"op": "remove_child", "member_id": children[0]["member_id"]})
    elif dates and len(dates) >= 2:
        operations.append({"op": "set_dates", "check_in": dates[0], "check_out": dates[1]})
    elif dates and any(word in normalized for word in ("trả phòng", "checkout", "check-out")):
        operations.append({"op": "set_dates", "check_out": dates[-1]})

    adults = re.search(r"(\d+)\s+người lớn", normalized)
    if adults:
        operations.append({"op": "set_adults", "count": int(adults.group(1))})

    age_match = re.search(r"(?:bé|trẻ|con)\s*(?:đó\s*)?(\d{1,2})\s*tuổi", normalized)
    if not age_match:
        age_match = re.search(r"(\d{1,2})\s*tuổi", normalized)
    if age_match and children:
        operations.append({
            "op": "set_child_age", "member_id": children[0]["member_id"],
            "age": int(age_match.group(1)),
        })
    elif (
        not age_match
        and any(word in normalized for word in ("thêm", "add"))
        and any(word in normalized for word in ("trẻ", "bé", "child"))
    ):
        operations.append({"op": "add_child", "age": None})

    return {"ops": operations} if operations else None


def _fact_ids(payload: dict[str, Any], question: str) -> list[str]:
    index = payload.get("candidate_index") or []
    facts = payload.get("facts") or []
    candidates = index or facts
    normalized = question.lower()
    if any(word in normalized for word in ("ăn sáng", "bữa sáng", "breakfast")):
        return [f["fact_id"] for f in candidates if f.get("field") == "breakfast"][:4]
    return []


def _answer_payload(payload: dict[str, Any], question: str) -> dict[str, Any]:
    facts = payload.get("facts") or []
    selected = []
    for fact in facts:
        if fact.get("field") == "breakfast" and any(word in question.lower() for word in ("ăn sáng", "bữa sáng", "breakfast")):
            selected.append(fact)
    claims = []
    for fact in selected:
        window = (fact.get("conditions") or {}).get("window")
        value = str(fact.get("value") or "")
        statement = value
        if window:
            statement = f"{value} Khung giờ phục vụ: {window}."
        claims.append({"text": statement[:2000], "fact_ids": [fact["fact_id"]]})
    result: dict[str, Any] = {
        "supported_claims": claims,
        "unknowns": [] if claims else ["Thông tin này chưa được xác nhận trong dữ liệu hiện có."],
        "conflicts": [],
        "guest_brief_refs": [],
    }
    patch = _proposal(question, payload) if payload.get("guest_brief_patch_enabled", True) else None
    if patch:
        result["guest_patch"] = patch
    return result


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: Any) -> Any:
        global TOTAL_PROVIDER_CALLS
        state = TURN.get()
        if state is None:
            state = {"calls": 0, "saw_patch": False, "fail_used": False}
            TURN.set(state)
        self.calls += 1
        state["calls"] += 1
        TOTAL_PROVIDER_CALLS += 1
        if state["calls"] > 2:
            raise RuntimeError("Sprint 5 acceptance limit: two provider calls per guest turn")
        payload = _parse_input(request)
        question = _question(payload)
        is_selector = "candidate_index" in payload
        control = controls()
        if (
            not state["fail_used"] and state["saw_patch"] and not is_selector
            and control.get("fail_postapply_answer") is True
        ):
            state["fail_used"] = True
            control["fail_postapply_answer"] = False
            CONTROL.write_text(json.dumps(control), encoding="utf-8")
            event({"stage": "fake_provider_failure", "class": "ForcedPostApplyAnswerFailure", "usage": "unknown"})
            raise RuntimeError("Forced post-apply answer failure for recovery acceptance")

        if is_selector:
            output: dict[str, Any] = {"fact_ids": _fact_ids(payload, question)}
            patch = _proposal(question, payload) if payload.get("guest_brief_patch_enabled", True) else None
            if patch:
                output["guest_patch"] = patch
                state["saw_patch"] = True
        else:
            output = _answer_payload(payload, question)
            if output.get("guest_patch", {}).get("ops"):
                state["saw_patch"] = True
        from staylead_platform.platform.contracts.ai_provider import (
            GenerationResult,
            Usage,
        )
        raw = json.dumps(output, ensure_ascii=False)
        event({
            "stage": "fake_provider", "call": self.calls,
            "model": "offline-fake", "output_chars": len(raw),
            "output_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "usage": {"input_tokens": None, "output_tokens": None, "total_tokens": None},
        })
        await asyncio.sleep(0)
        return GenerationResult(
            text=raw, provider="fake", deployment="acceptance", model="offline-fake",
            request_id=f"s5-fake-{self.calls}", usage=Usage(),
        )


def _live_provider() -> Any:
    from pydantic import SecretStr
    from staylead_platform.infrastructure.ai_provider import (
        FoundryGrokConfig,
        FoundryGrokProvider,
    )

    result = subprocess.run(
        ["az", "cognitiveservices", "account", "keys", "list", "--resource-group", "Ken-Dev",
         "--name", "KEN-OpenAI-USEast2", "--subscription", "222aa766-dff0-4c9e-811f-90ce9b5c44f4", "-o", "json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise SystemExit("Existing development credential retrieval unavailable; live mode was not started.")
    api_key = json.loads(result.stdout)["key1"]

    async def trace_httpx(name: str, info: dict[str, Any]) -> None:
        del info
        events = HTTPX_TRACE_EVENTS.get()
        started = HTTPX_TRACE_START.get()
        if events is None or started is None or not isinstance(name, str):
            return
        if len(events) >= 100 or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", name):
            return
        events.append({"event": name, "offset_ms": round((time.monotonic() - started) * 1000, 1)})

    provider = FoundryGrokProvider(FoundryGrokConfig(
        base_url="https://ken-openai-useast2.services.ai.azure.com/openai/v1/",
        api_key=SecretStr(api_key), deployment="cc-dev-grok-4-1-fast-reasoning",
        trace_callback=trace_httpx,
    ))
    original = provider.generate

    async def observed(request: Any) -> Any:
        global TOTAL_PROVIDER_CALLS
        state = TURN.get()
        if state is None:
            state = {"calls": 0, "saw_patch": False, "fail_used": False}
            TURN.set(state)
        if state["calls"] >= 2:
            raise RuntimeError("Sprint 5 two-provider-calls-per-turn limit reached; no provider call was made.")
        attempt = _reserve_provider_attempt()
        state["calls"] += 1
        TOTAL_PROVIDER_CALLS += 1
        started_at = time.monotonic()
        trace_events: list[dict[str, Any]] = []
        event({
            "stage": "live_provider_call_started", "provider_mode": "live",
            "run_id": REMEDIATION_RUN_ID, "attempt": attempt,
            "turn_call": state["calls"], "provider": "foundry_grok",
            "requested_model": "grok-4-1-fast-reasoning",
            "request_shape": {
                "instructions_chars": len(request.instructions),
                "input_chars": len(request.input_text),
                "max_output_tokens": request.max_output_tokens,
            },
        })
        trace_token = HTTPX_TRACE_EVENTS.set(trace_events)
        trace_start_token = HTTPX_TRACE_START.set(started_at)
        try:
            response = await original(request)
        except asyncio.CancelledError as exc:
            _live_failure_event(
                exc, attempt=attempt, turn_call=state["calls"],
                started_at=started_at, trace_events=trace_events, cancelled=True,
            )
            raise
        except Exception as exc:
            _live_failure_event(
                exc, attempt=attempt, turn_call=state["calls"],
                started_at=started_at, trace_events=trace_events,
            )
            raise
        finally:
            HTTPX_TRACE_START.reset(trace_start_token)
            HTTPX_TRACE_EVENTS.reset(trace_token)
        event({
            "stage": "live_provider_call_completed", "provider_mode": "live",
            "run_id": REMEDIATION_RUN_ID, "attempt": attempt,
            "turn_call": state["calls"], "provider": response.provider,
            "model": response.model, "deployment": response.deployment,
            "provider_request_id": _safe_request_id(response.request_id),
            "latency_ms": round((time.monotonic() - started_at) * 1000, 1),
            "usage": asdict(response.usage), "output_chars": len(response.text),
            "output_limit_tokens": request.max_output_tokens,
            "httpx_trace": trace_events[:100],
        })
        return response

    provider.generate = observed
    return provider


def create_runtime_app(live: bool = False) -> Any:
    if not RUNTIME.exists():
        raise SystemExit("Private runtime config is missing; prepare the ignored local config first.")
    if live and os.environ.get("STAYLEAD_LIVE_EVAL") != "1":
        raise SystemExit("Live mode requires explicit STAYLEAD_LIVE_EVAL=1.")
    if live and controls().get("hide_completed_response_once") is True:
        raise SystemExit("hide_completed_response_once is fake-only; clear it before starting live mode.")
    if live:
        _load_run_state()

    from pydantic import SecretStr
    from staylead_platform.composition.configuration.settings import Settings
    from staylead_platform.entrypoints.app import create_app

    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    settings = Settings(
        _env_file=None, database_url=runtime["database_url"],
        session_signing_secret=SecretStr(runtime["session_signing_secret"]), ai_provider="disabled",
    )
    provider = _live_provider() if live else FakeProvider()
    app = create_app(settings, provider=provider)

    from fastapi.responses import Response

    @app.middleware("http")
    async def acceptance_events(request: Any, call_next: Any) -> Any:
        request_body = await request.body()
        # Starlette's middleware call_next consumes the original receive stream;
        # install a replay receive so FastAPI can parse the same body.
        delivered = False

        async def receive() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return {"type": "http.disconnect"}

        request._receive = receive
        is_message = request.method == "POST" and request.url.path.endswith("/messages")
        state = {"calls": 0, "saw_patch": False, "fail_used": False}
        token = TURN.set(state) if is_message else None
        body_json: dict[str, Any] = {}
        try:
            if request_body:
                parsed = json.loads(request_body)
                if isinstance(parsed, dict):
                    body_json = parsed
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        turn_kind: str | None = None
        semantic_turn: int | None = None
        resume_count: int | None = None
        if live and is_message:
            try:
                if body_json.get("answer_only_receipt_id"):
                    turn_kind = "answer_only_resume"
                    resume_count = _reserve_answer_only_resume()
                elif body_json.get("question") is not None:
                    turn_kind = "semantic_guest_turn"
                    semantic_turn = _reserve_semantic_turn()
            except RuntimeError:
                if token is not None:
                    TURN.reset(token)
                event({
                    "stage": "live_acceptance_limit", "provider_mode": "live",
                    "run_id": REMEDIATION_RUN_ID, "turn_kind": turn_kind,
                    "status": 429, "provider_calls_in_turn": 0,
                })
                return Response(
                    content=json.dumps({"error": {"code": "acceptance_limit", "message": "Sprint 5 acceptance limit reached."}}),
                    status_code=429, media_type="application/json",
                )
        try:
            response = await call_next(request)
            if is_message and controls().get("response_delay_seconds"):
                await asyncio.sleep(min(float(controls()["response_delay_seconds"]), 30.0))
            response_body = b"".join([chunk async for chunk in response.body_iterator])
            try:
                decoded_response: Any = json.loads(response_body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                decoded_response = {"body_sha256": hashlib.sha256(response_body).hexdigest(), "bytes": len(response_body)}
            delivered_status = response.status_code
            delivered_body = response_body
            injected_unknown_completion = False
            control = controls()
            if (
                not live and is_message and response.status_code == 200
                and isinstance(decoded_response, dict)
                and decoded_response.get("status") == "completed"
                and control.get("hide_completed_response_once") is True
            ):
                control["hide_completed_response_once"] = False
                CONTROL.write_text(json.dumps(control), encoding="utf-8")
                injected_unknown_completion = True
                delivered_status = 503
                delivered_body = json.dumps({
                    "error": {
                        "code": "storage_unavailable",
                        "message": "The response was interrupted after completion; retry this request ID.",
                        "retryable": True,
                    },
                    "request_id": body_json.get("request_id"),
                }).encode("utf-8")
            item: dict[str, Any] = {
                "stage": "http", "method": request.method, "path": request.url.path,
                "status": delivered_status, "provider_mode": "live" if live else "fake",
            }
            if is_message:
                item["question"] = body_json.get("question")
                item["internal_status"] = response.status_code
                item["internal_response"] = redact(decoded_response)
                item["delivered_status"] = delivered_status
                if live:
                    item["turn_kind"] = turn_kind
                    if semantic_turn is not None:
                        item["semantic_guest_turn"] = semantic_turn
                    if resume_count is not None:
                        item["answer_only_resume"] = resume_count
                if injected_unknown_completion:
                    item["fault"] = "hide_completed_response_once"
                    item["delivered_response"] = redact(json.loads(delivered_body))
                else:
                    item["response"] = redact(decoded_response)
                item["provider_calls_in_turn"] = state["calls"]
            event(item)
            return Response(
                content=delivered_body, status_code=delivered_status,
                headers={k: v for k, v in response.headers.items() if k.lower() not in {"content-length", "transfer-encoding"}},
                media_type=response.media_type,
            )
        finally:
            if token is not None:
                TURN.reset(token)

    return app


async def _run_diagnostic() -> None:
    from staylead_platform.platform.contracts.ai_provider import GenerationRequest

    provider = _live_provider()
    turn_token = TURN.set({"calls": 0, "saw_patch": False, "fail_used": False})
    try:
        result = await provider.generate(GenerationRequest(
            instructions='Return one JSON object with the key "ok" set to true.',
            input_text='{"probe":"ping"}', max_output_tokens=140,
        ))
    finally:
        TURN.reset(turn_token)
    event({
        "stage": "live_diagnostic_completed", "provider_mode": "live",
        "run_id": REMEDIATION_RUN_ID, "provider": result.provider,
        "model": result.model, "provider_request_id": _safe_request_id(result.request_id),
        "usage": asdict(result.usage), "output_chars": len(result.text),
    })
    print("One-call provider diagnostic completed; see remediation-runtime-events.jsonl.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "fake", "live", "diagnostic"))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.mode == "init":
        if RUNTIME.exists():
            raise SystemExit("Private runtime config already exists; refusing to replace it.")
        runtime = {"database_url": "<REDACTED_LOCAL_DATABASE_URL>", "session_signing_secret": secrets.token_urlsafe(48)}
        RUNTIME.write_text(json.dumps(runtime), encoding="utf-8")
        RUNTIME.chmod(0o600)
        print("Private acceptance runtime initialized with a placeholder database URL.")
        return

    if args.mode == "live" and os.environ.get("STAYLEAD_LIVE_EVAL") != "1":
        raise SystemExit("Live mode requires explicit STAYLEAD_LIVE_EVAL=1.")
    if args.mode == "diagnostic":
        if os.environ.get("STAYLEAD_LIVE_EVAL") != "1":
            raise SystemExit("Diagnostic mode requires explicit STAYLEAD_LIVE_EVAL=1.")
        if controls().get("hide_completed_response_once") is True:
            raise SystemExit("hide_completed_response_once is fake-only; clear it before diagnostic mode.")
        _load_run_state()
        try:
            asyncio.run(_run_diagnostic())
        except RuntimeError as exc:
            code = getattr(exc, "code", None)
            safe_code = (
                code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", code)
                else type(exc).__name__
            )
            print(f"One-call provider diagnostic failed ({safe_code}); see remediation-runtime-events.jsonl.")
            raise SystemExit(1) from None
        except asyncio.CancelledError:
            print("One-call provider diagnostic was cancelled; see remediation-runtime-events.jsonl.")
            raise SystemExit(1) from None
        return
    import uvicorn
    uvicorn.run(create_runtime_app(args.mode == "live"), host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
