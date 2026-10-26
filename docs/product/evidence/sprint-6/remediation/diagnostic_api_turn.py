"""One-shot API diagnostic for explicitly selected existing acceptance sessions.

Invoke only for a coordinator-selected turn. No server is started and no
request is retried. Existing output for a turn makes that turn non-rerunnable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parent
MATRIX_PATH = EVIDENCE.parent / "live-cases.json"
MATRIX_ID = "staylead-s6-nine-turn-multilingual-20261026-v1"
MAX_REQUESTS, MAX_TURNS, MAX_CALLS_PER_TURN = 18, 9, 2
BASE_URL = "http://127.0.0.1:18086"


def _namespace_settings(namespace: str) -> dict[str, Any]:
    if namespace not in {"remediation-4", "remediation-6"}:
        raise ValueError("Diagnostic namespace must be remediation-4 or remediation-6.")
    prefix = "staylead-sprint6-remediation-4" if namespace == "remediation-4" else "staylead-sprint6-remediation-6"
    number = namespace.rsplit("-", 1)[1]
    return {
        "namespace": namespace,
        "run_id": f"s6-codex-20261026-{namespace}",
        "state": Path(f"/private/tmp/{prefix}-run-state.json"),
        "events": Path(f"/private/tmp/{prefix}-runtime-events.jsonl"),
        "runtime": Path(f"/private/tmp/{prefix}-runtime.json"),
        "anchor_turn": 6 if namespace == "remediation-4" else 2,
        "first_turn": 7 if namespace == "remediation-4" else 3,
        "last_turn": 9,
        "output_prefix": "diagnostic-api-turn" if namespace == "remediation-4" else f"namespace{number}-diagnostic-api-turn",
    }


DIAGNOSTIC_NAMESPACE = os.environ.get("STAYLEAD_S6_DIAGNOSTIC_NAMESPACE", "remediation-4")
_SETTINGS = _namespace_settings(DIAGNOSTIC_NAMESPACE)
RUN_ID = _SETTINGS["run_id"]
STATE_PATH = _SETTINGS["state"]
EVENTS_PATH = _SETTINGS["events"]
RUNTIME_PATH = _SETTINGS["runtime"]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object.")
    return value


def _matrix_turn(turn: int) -> dict[str, Any]:
    matrix = _read_json(MATRIX_PATH)
    cases = matrix.get("turns")
    if matrix.get("matrix_id") != MATRIX_ID or not isinstance(cases, list) or len(cases) != MAX_TURNS:
        raise ValueError("Pinned acceptance matrix mismatch.")
    case = next((item for item in cases if isinstance(item, dict) and item.get("turn") == turn), None)
    if not case or not isinstance(case.get("utterance"), str):
        raise ValueError("Pinned turn unavailable.")
    return case


def _preflight_turn(turn: int, state: dict[str, Any], namespace: str | None = None) -> None:
    settings = _namespace_settings(namespace or DIAGNOSTIC_NAMESPACE)
    if not settings["first_turn"] <= turn <= settings["last_turn"]:
        raise ValueError("Turn is outside the selected diagnostic namespace's remaining-turn range.")
    if state.get("run_id") != settings["run_id"]:
        raise ValueError("Diagnostic run identity mismatch.")
    if state.get("guest_turns") != turn - 1:
        raise ValueError("Guest-turn counter does not match selected turn.")
    if state.get("max_guest_turns") != MAX_TURNS or state.get("max_codex_requests") != MAX_REQUESTS:
        raise ValueError("Persistent cap mismatch.")
    count = state.get("codex_requests")
    if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count < MAX_REQUESTS:
        raise ValueError("Persistent request counter invalid or exhausted.")
    if state.get("max_calls_per_turn") != MAX_CALLS_PER_TURN:
        raise ValueError("Per-turn provider cap mismatch.")
    if state.get("authorized_for_live_calls") is not True:
        raise ValueError("Persistent run state is not authorized for live calls.")


def _anchor_request_hash(events_path: Path, run_id: str, anchor_turn: int) -> str:
    fingerprints = set()
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        fingerprint = event.get("turn_request_id_sha256")
        if (event.get("run_id") == run_id and event.get("guest_turn") == anchor_turn
                and event.get("stage") == "provider_call_started"
                and isinstance(fingerprint, str) and re.fullmatch(r"[a-f0-9]{16,64}", fingerprint)):
            fingerprints.add(fingerprint)
    if len(fingerprints) != 1:
        raise ValueError("Selected namespace anchor request fingerprint missing or ambiguous.")
    return next(iter(fingerprints))


def _result_path(namespace: str, turn: int) -> Path:
    settings = _namespace_settings(namespace)
    if not settings["first_turn"] <= turn <= settings["last_turn"]:
        raise ValueError("Turn is outside the selected diagnostic namespace's remaining-turn range.")
    return EVIDENCE / f"{settings['output_prefix']}-{turn:02d}.json"


def _verify_prior_turn_count(actual: int, expected: int) -> None:
    if actual != expected:
        raise ValueError("Resolved DB session guest-turn count does not match selected turn.")


def _resolve_session(database_url: str, request_hash: str, expected_guest_turns: int) -> tuple[str, str]:
    from sqlalchemy import select
    from staylead_platform.infrastructure.database import create_database_engine
    from staylead_platform.infrastructure.persistence.store import hotels, requests, sessions

    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            rows = connection.execute(
                select(requests.c.session_id, requests.c.hotel_id, requests.c.request_id)
                .where(requests.c.hotel_id == "HTL-CITY01")
            ).mappings().all()
            matches = [row for row in rows if _hash(str(row["request_id"])).startswith(request_hash)]
            session_ids = {row["session_id"] for row in matches}
            hotel_ids = {row["hotel_id"] for row in matches}
            if len(session_ids) != 1 or hotel_ids != {"HTL-CITY01"}:
                raise ValueError("Turn-six fingerprint did not resolve to one scoped session.")
            session_id = next(iter(session_ids))
            scoped = connection.execute(
                select(sessions.c.session_id, hotels.c.synthetic)
                .join(hotels, hotels.c.hotel_id == sessions.c.hotel_id)
                .where(sessions.c.session_id == session_id, sessions.c.hotel_id == "HTL-CITY01")
            ).mappings().one_or_none()
            prior_requests = connection.execute(
                select(requests.c.request_id).where(
                    requests.c.session_id == session_id,
                    requests.c.hotel_id == "HTL-CITY01",
                )
            ).all()
            if scoped is None or scoped["synthetic"] is not True:
                raise ValueError("Resolved DB session failed synthetic scope checks.")
            _verify_prior_turn_count(len(prior_requests), expected_guest_turns)
            return str(session_id), "HTL-CITY01"
    finally:
        engine.dispose()


def _safe_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    errors, count = value.get("errors"), value.get("error_count")
    if not isinstance(errors, list) or not isinstance(count, int) or isinstance(count, bool):
        return {"code": "model_validation", "diagnostics_shape": "invalid"}
    result = []
    for item in errors[:64]:
        if not isinstance(item, dict) or not isinstance(item.get("loc"), list):
            continue
        loc = [part for part in item["loc"][:12] if
               (isinstance(part, int) and not isinstance(part, bool))
               or (isinstance(part, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}|<key>", part))]
        error_type = item.get("type")
        if isinstance(error_type, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", error_type):
            result.append({"loc": loc, "type": error_type})
    return {"code": "model_validation", "error_count": min(count, 10000), "errors": result}


def safe_response(payload: Any) -> dict[str, Any]:
    """Allowlist known API answer fields; never pass unknown nested data through."""
    if not isinstance(payload, dict):
        return {"response_shape": "non_object"}
    safe: dict[str, Any] = {}
    for key in ("status", "answer", "answer_eligibility"):
        if isinstance(payload.get(key), str):
            safe[key] = payload[key][:12000]
    if isinstance(payload.get("unknowns"), list):
        safe["unknowns"] = [item[:1000] for item in payload["unknowns"][:32] if isinstance(item, str)]
    if isinstance(payload.get("evidence"), list):
        keys = ("fact_id", "hotel_id", "source_id", "source_version", "section")
        safe["evidence"] = [
            {key: item[key] for key in keys if isinstance(item.get(key), (str, int))}
            for item in payload["evidence"][:32] if isinstance(item, dict)
        ]
    fields = {
        "language_preference": ("language_tag", "source", "revision"),
        "presentation": ("language_tag", "direction", "preference_revision", "freshness", "labels_fallback"),
        "brief_receipt": ("status", "brief_version_before", "brief_version_after", "answer_status", "brief_version_used"),
        "trace": ("answer_validation", "guest_claims_rejected"),
    }
    for section, names in fields.items():
        value = payload.get(section)
        if isinstance(value, dict):
            safe[section] = {name: value[name] for name in names if name in value}
    brief = payload.get("guest_brief")
    if isinstance(brief, dict):
        brief_safe: dict[str, Any] = {}
        if isinstance(brief.get("brief_version"), int):
            brief_safe["brief_version"] = brief["brief_version"]
        dates = brief.get("dates")
        if isinstance(dates, dict):
            brief_safe["dates"] = {
                key: dates[key] for key in ("check_in", "check_out", "nights")
                if isinstance(dates.get(key), (str, int))
            }
        party = brief.get("party")
        if isinstance(party, dict):
            party_safe: dict[str, Any] = {}
            if isinstance(party.get("adults"), int):
                party_safe["adults"] = party["adults"]
            children = party.get("children")
            if isinstance(children, list):
                safe_children = []
                for child in children[:20]:
                    if not isinstance(child, dict) or not (
                        child.get("age") is None or isinstance(child.get("age"), int)
                    ):
                        continue
                    safe_child = {"age": child["age"]}
                    member_id = child.get("member_id")
                    if isinstance(member_id, str) and member_id:
                        safe_child["member_id_sha256"] = _hash(member_id)[:16]
                    member_hash = child.get("member_id_sha256")
                    if ("member_id_sha256" not in safe_child and isinstance(member_hash, str)
                            and re.fullmatch(r"[a-f0-9]{16,64}", member_hash)):
                        safe_child["member_id_sha256"] = member_hash
                    safe_children.append(safe_child)
                party_safe["children"] = safe_children
            brief_safe["party"] = party_safe
        if isinstance(brief.get("pending_fields"), list):
            brief_safe["pending_fields"] = [
                item[:120] for item in brief["pending_fields"][:32] if isinstance(item, str)
            ]
        safe["guest_brief"] = brief_safe
    error = payload.get("error")
    if isinstance(error, dict):
        safe["error"] = {key: error[key] for key in ("code", "retryable")
                         if isinstance(error.get(key), (str, bool))}
        diagnostics = error.get("validation_diagnostics")
        if isinstance(diagnostics, dict) and diagnostics.get("code") == "model_validation":
            safe["error"]["validation_diagnostics"] = _safe_diagnostics(diagnostics)
    return safe


def _write_result(path: Path, value: dict[str, Any], *, exclusive: bool) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if exclusive:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    path.chmod(0o600)


def execute_turn(turn: int) -> dict[str, Any]:
    settings = _namespace_settings(DIAGNOSTIC_NAMESPACE)
    if not settings["first_turn"] <= turn <= settings["last_turn"]:
        raise ValueError("Turn is outside the selected diagnostic namespace's remaining-turn range.")
    output = _result_path(DIAGNOSTIC_NAMESPACE, turn)
    if output.exists():
        raise ValueError("Evidence already exists for this turn; refusing repeat.")
    state = _read_json(settings["state"])
    _preflight_turn(turn, state, DIAGNOSTIC_NAMESPACE)
    case = _matrix_turn(turn)
    config = _read_json(settings["runtime"])
    database_url, secret = config.get("database_url"), config.get("session_signing_secret")
    if not isinstance(database_url, str) or not isinstance(secret, str) or not secret:
        raise ValueError("Private runtime config incomplete.")
    session_id, hotel_id = _resolve_session(
        database_url,
        _anchor_request_hash(settings["events"], settings["run_id"], settings["anchor_turn"]),
        expected_guest_turns=turn - 1,
    )
    request_id = str(uuid.uuid4())
    result: dict[str, Any] = {
        "classification": "DIAGNOSTIC realAPI/PG/Codex",
        "run_id": settings["run_id"], "run_namespace": DIAGNOSTIC_NAMESPACE,
        "matrix_id": MATRIX_ID, "turn": turn,
        "request_id_sha256": _hash(request_id)[:16],
        "question_sha256": _hash(case["utterance"]),
        "automatic_retry": False, "ui_or_clipboard_checked": False,
        "full_matrix_pass": False, "http_status": None, "response": None,
        "transport_error": None, "counter_state_after": None,
    }
    # An exclusive marker prevents a second request if this process is rerun.
    _write_result(output, {**result, "status": "in_progress"}, exclusive=True)
    from staylead_platform.platform.guest_context.sessions.signing import issue_token
    token = issue_token(secret=secret, session_id=session_id, hotel_id=hotel_id,
                        expires_at=int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()))
    body = json.dumps({"request_id": request_id, "question": case["utterance"]}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/v1/guest/sessions/{session_id}/messages", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    del token, secret, config
    try:
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result["http_status"], raw = response.status, response.read(1024 * 1024)
        except urllib.error.HTTPError as exc:
            result["http_status"], raw = exc.code, exc.read(1024 * 1024)
        try:
            result["response"] = safe_response(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["response"] = {"response_shape": "non_json", "response_bytes": len(raw)}
    except Exception as exc:
        result["transport_error"] = type(exc).__name__
    finally:
        result["status"] = "completed" if result["http_status"] is not None else "transport_error"
        try:
            after = _read_json(settings["state"])
            result["counter_state_after"] = {
                key: after.get(key) for key in
                ("run_id", "codex_requests", "guest_turns", "max_codex_requests", "max_guest_turns")
            }
        except Exception:
            result["counter_state_after"] = {"status": "unavailable"}
        _write_result(output, result, exclusive=False)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turn", required=True, type=int, choices=range(3, 10))
    args = parser.parse_args()
    try:
        result = execute_turn(args.turn)
    except Exception as exc:
        print(f"Diagnostic stopped ({type(exc).__name__}); inspect the turn artifact before any further action.")
        return 2
    print(json.dumps({key: result[key] for key in
                      ("classification", "run_id", "turn", "status", "http_status", "request_id_sha256",
                       "counter_state_after")}, indent=2))
    print(f"Redacted evidence: {_result_path(DIAGNOSTIC_NAMESPACE, args.turn)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
