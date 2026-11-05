"""Signed, anonymous, hotel-bound guest session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionClaims:
    session_id: str
    hotel_id: str
    expires_at: int


class InvalidSessionToken(ValueError):
    pass


def issue_token(*, secret: str, session_id: str, hotel_id: str, expires_at: int) -> str:
    payload = json.dumps({"sid": session_id, "hid": hotel_id, "exp": expires_at}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret.encode(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _verify_signature(token: str, *, secret: str) -> SessionClaims:
    try:
        encoded, signed = token.split(".", 1)
        padding = "=" * (-len(signed) % 4)
        signature = base64.urlsafe_b64decode(signed + padding)
        expected = hmac.new(secret.encode(), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidSessionToken("invalid signature")
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        values = json.loads(payload)
        claims = SessionClaims(values["sid"], values["hid"], int(values["exp"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidSessionToken("invalid token") from exc
    return claims


def verify_token(token: str, *, secret: str, now: int | None = None) -> SessionClaims:
    claims = _verify_signature(token, secret=secret)
    if claims.expires_at <= (now if now is not None else int(time.time())):
        raise InvalidSessionToken("expired token")
    return claims


def verify_token_for_delete(token: str, *, secret: str) -> SessionClaims:
    """Verify token ownership for deletion, including after normal read expiry."""
    return _verify_signature(token, secret=secret)
