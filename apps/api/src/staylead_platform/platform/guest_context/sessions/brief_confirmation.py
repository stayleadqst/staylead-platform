"""Purpose-separated, session-bound confirmation challenges for guest brief edits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from staylead_platform.platform.contracts.guest_brief import ValidatedGuestBriefPatch

_PURPOSE = "staylead.guest_brief.confirm.v1"
_KEY_CONTEXT = b"staylead:guest-brief-confirmation:v1"
_MAX_TTL_SECONDS = 300
_MAX_TOKEN_LENGTH = 32_768


class InvalidBriefConfirmation(ValueError):
    """The challenge is malformed, invalidly signed, expired, or misbound."""


def brief_state_changes(
    before: dict[str, Any], after: dict[str, Any],
    before_pending: tuple[str, ...], after_pending: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    """Return an opaque field-level diff suitable for user review, without domain policy."""
    changes: list[dict[str, Any]] = []

    def visit(path: str, old: Any, new: Any, old_present: bool = True, new_present: bool = True) -> None:
        if old_present and new_present and isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys(), key=str):
                visit(f"{path}.{key}" if path else str(key), old.get(key), new.get(key), key in old, key in new)
            return
        if old_present != new_present or old != new:
            changes.append({"field": path, "before_present": old_present, "before": old,
                            "after_present": new_present, "after": new})

    visit("", before, after)
    if before_pending != after_pending:
        changes.append({"field": "pending_fields", "before": list(before_pending), "after": list(after_pending)})
    return tuple(changes)


@dataclass(frozen=True)
class BriefConfirmationClaims:
    session_id: str
    hotel_id: str
    request_id: str
    source_utterance_id: str
    question: str
    expected_brief_version: int
    operations: tuple[dict[str, Any], ...]
    turn_intents: tuple[str, ...]
    authorized_targets: tuple[str, ...]
    selected_fact_ids: tuple[str, ...]
    changes: tuple[dict[str, Any], ...]
    validated_data: dict[str, Any]
    validated_pending_fields: tuple[str, ...]
    validated_applied_delta: dict[str, Any]
    validated_status: Literal["applied", "no_change", "clarification", "partial_success"]
    validated_source_fields: tuple[str, ...]
    proposal_hash: str
    issued_at: int
    expires_at: int


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _key(secret: str) -> bytes:
    if not secret:
        raise InvalidBriefConfirmation("confirmation signing is not configured")
    return hmac.new(secret.encode("utf-8"), _KEY_CONTEXT, hashlib.sha256).digest()


def _proposal_hash(
    operations: tuple[dict[str, Any], ...], changes: tuple[dict[str, Any], ...], version: int,
    validated_patch: dict[str, Any],
) -> str:
    return hashlib.sha256(_canonical_json({
        "operations": list(operations), "changes": list(changes), "expected_brief_version": version,
        "validated_patch": validated_patch,
    })).hexdigest()


def issue_brief_confirmation(
    *, secret: str, session_id: str, hotel_id: str, request_id: str,
    source_utterance_id: str, question: str, expected_brief_version: int,
    operations: tuple[dict[str, Any], ...], turn_intents: tuple[str, ...],
    authorized_targets: tuple[str, ...], selected_fact_ids: tuple[str, ...],
    changes: tuple[dict[str, Any], ...], validated_patch: ValidatedGuestBriefPatch,
    now: int | None = None,
    ttl_seconds: int = _MAX_TTL_SECONDS,
) -> tuple[str, BriefConfirmationClaims]:
    issued_at = int(time.time()) if now is None else now
    if ttl_seconds < 1 or ttl_seconds > _MAX_TTL_SECONDS:
        raise ValueError("confirmation lifetime is outside the allowed range")
    validated_patch_payload = {
        "data": validated_patch.data,
        "pending_fields": list(validated_patch.pending_fields),
        "applied_delta": validated_patch.applied_delta,
        "status": validated_patch.status,
        "source_fields": list(validated_patch.source_fields),
    }
    claims = BriefConfirmationClaims(
        session_id=session_id, hotel_id=hotel_id, request_id=request_id,
        source_utterance_id=source_utterance_id, question=question,
        expected_brief_version=expected_brief_version, operations=operations,
        turn_intents=turn_intents, authorized_targets=authorized_targets,
        selected_fact_ids=selected_fact_ids, changes=changes,
        validated_data=validated_patch.data,
        validated_pending_fields=validated_patch.pending_fields,
        validated_applied_delta=validated_patch.applied_delta,
        validated_status=validated_patch.status,
        validated_source_fields=validated_patch.source_fields,
        proposal_hash=_proposal_hash(
            operations, changes, expected_brief_version, validated_patch_payload,
        ),
        issued_at=issued_at, expires_at=issued_at + ttl_seconds,
    )
    payload = {
        "purpose": _PURPOSE,
        "sid": claims.session_id,
        "hid": claims.hotel_id,
        "rid": claims.request_id,
        "source": claims.source_utterance_id,
        "question": claims.question,
        "version": claims.expected_brief_version,
        "operations": list(claims.operations),
        "intents": list(claims.turn_intents),
        "targets": list(claims.authorized_targets),
        "fact_ids": list(claims.selected_fact_ids),
        "changes": list(claims.changes),
        "validated_patch": {
            "data": claims.validated_data,
            "pending_fields": list(claims.validated_pending_fields),
            "applied_delta": claims.validated_applied_delta,
            "status": claims.validated_status,
            "source_fields": list(claims.validated_source_fields),
        },
        "proposal_hash": claims.proposal_hash,
        "iat": claims.issued_at,
        "exp": claims.expires_at,
    }
    encoded = base64.urlsafe_b64encode(_canonical_json(payload)).rstrip(b"=").decode("ascii")
    signature = hmac.new(_key(secret), encoded.encode("ascii"), hashlib.sha256).digest()
    token = f"{encoded}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"
    if len(token) > _MAX_TOKEN_LENGTH:
        raise ValueError("confirmation proposal is too large")
    return token, claims


def verify_brief_confirmation(
    token: str, *, secret: str, now: int | None = None,
) -> BriefConfirmationClaims:
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH:
        raise InvalidBriefConfirmation("invalid confirmation token")
    try:
        encoded, supplied = token.split(".", 1)
        signed = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
        expected = hmac.new(_key(secret), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signed, expected):
            raise InvalidBriefConfirmation("invalid confirmation signature")
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise InvalidBriefConfirmation("invalid confirmation payload")
        if payload.get("purpose") != _PURPOSE:
            raise InvalidBriefConfirmation("invalid confirmation purpose")
        validated_patch = payload["validated_patch"]
        if not isinstance(validated_patch, dict):
            raise InvalidBriefConfirmation("invalid validated patch")
        validated_status = validated_patch.get("status")
        if validated_status not in {"applied", "no_change", "clarification", "partial_success"}:
            raise InvalidBriefConfirmation("invalid validated patch status")
        claims = BriefConfirmationClaims(
            session_id=_required_text(payload, "sid"),
            hotel_id=_required_text(payload, "hid"),
            request_id=_required_text(payload, "rid"),
            source_utterance_id=_required_text(payload, "source"),
            question=_required_text(payload, "question"),
            expected_brief_version=_required_nonnegative_int(payload, "version"),
            operations=_required_dict_tuple(payload, "operations"),
            turn_intents=_required_text_tuple(payload, "intents"),
            authorized_targets=_required_text_tuple(payload, "targets"),
            selected_fact_ids=_required_text_tuple(payload, "fact_ids"),
            changes=_required_dict_tuple(payload, "changes"),
            validated_data=_required_object(validated_patch, "data"),
            validated_pending_fields=_required_text_tuple(validated_patch, "pending_fields"),
            validated_applied_delta=_required_object(validated_patch, "applied_delta"),
            validated_status=validated_status,
            validated_source_fields=_required_text_tuple(validated_patch, "source_fields"),
            proposal_hash=_required_text(payload, "proposal_hash"),
            issued_at=_required_nonnegative_int(payload, "iat"),
            expires_at=_required_nonnegative_int(payload, "exp"),
        )
    except InvalidBriefConfirmation:
        raise
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidBriefConfirmation("invalid confirmation token") from exc
    checked_at = int(time.time()) if now is None else now
    if (claims.expires_at <= checked_at or claims.issued_at > checked_at
            or claims.expires_at <= claims.issued_at
            or claims.expires_at - claims.issued_at > _MAX_TTL_SECONDS):
        raise InvalidBriefConfirmation("confirmation token expired")
    validated_patch_payload = {
        "data": claims.validated_data,
        "pending_fields": list(claims.validated_pending_fields),
        "applied_delta": claims.validated_applied_delta,
        "status": claims.validated_status,
        "source_fields": list(claims.validated_source_fields),
    }
    if claims.proposal_hash != _proposal_hash(
        claims.operations, claims.changes, claims.expected_brief_version, validated_patch_payload,
    ):
        raise InvalidBriefConfirmation("confirmation proposal hash does not match")
    return claims


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value or len(value) > 2000:
        raise InvalidBriefConfirmation("invalid confirmation field")
    return value


def _required_nonnegative_int(payload: dict[str, Any], key: str) -> int:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidBriefConfirmation("invalid confirmation field")
    return value


def _required_text_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    value = payload[key]
    if (not isinstance(value, list) or len(value) > 64
            or any(not isinstance(item, str) or not item or len(item) > 256 for item in value)):
        raise InvalidBriefConfirmation("invalid confirmation field")
    return tuple(value)


def _required_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload[key]
    if not isinstance(value, dict):
        raise InvalidBriefConfirmation("invalid confirmation object")
    return value


def _required_dict_tuple(payload: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    value = payload[key]
    if not isinstance(value, list) or len(value) > 32 or any(not isinstance(item, dict) for item in value):
        raise InvalidBriefConfirmation("invalid confirmation field")
    return tuple(value)
