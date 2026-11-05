"""Local OIDC code+PKCE operator sessions; deliberately single-process storage."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException, Request, Response

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.identity.operator import OperatorPrincipal

COOKIE = "__Host-staylead_operator"
FLOW_COOKIE = "__Host-staylead_oidc_flow"
IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60


@dataclass
class Flow:
    nonce: str
    verifier: str
    browser_hash: str
    expires_at: float


@dataclass
class Session:
    principal: OperatorPrincipal
    created_at: float
    last_seen: float


class OidcOperatorAuth:
    """In-memory flow and revocation store; restart logs out every operator."""

    def __init__(self, settings: Settings, clock=time.time) -> None:
        self.settings = settings
        self.clock = clock
        self.flows: dict[str, Flow] = {}
        self.sessions: dict[str, Session] = {}

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    def start(self) -> Response:
        state = self._b64(secrets.token_bytes(32))
        self._prune(self.clock())
        nonce = self._b64(secrets.token_bytes(32))
        verifier = self._b64(secrets.token_bytes(48))
        browser_binding = self._b64(secrets.token_bytes(32))
        self.flows[state] = Flow(nonce, verifier, hashlib.sha256(browser_binding.encode()).hexdigest(), self.clock() + 300)
        challenge = self._b64(hashlib.sha256(verifier.encode()).digest())
        params = urlencode({"response_type": "code", "client_id": self.settings.operator_oidc_client_id,
                            "redirect_uri": self.settings.operator_oidc_redirect_uri,
                            "scope": "openid profile", "state": state, "nonce": nonce,
                            "code_challenge": challenge, "code_challenge_method": "S256"})
        response = Response(status_code=302, headers={"Location": f"{self.settings.operator_oidc_authorization_endpoint}?{params}",
                                                       "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        response.set_cookie(FLOW_COOKIE, browser_binding, httponly=True, secure=True, samesite="lax", path="/", max_age=300)
        return response

    async def callback(self, code: str | None, state: str | None, error: str | None,
                       browser_binding: str | None) -> Response:
        flow = self.flows.pop(state or "", None)
        binding_hash = hashlib.sha256((browser_binding or "").encode()).hexdigest()
        if (error or not code or flow is None or flow.expires_at <= self.clock()
                or not browser_binding or not secrets.compare_digest(binding_hash, flow.browser_hash)):
            raise HTTPException(401, detail={"error": {"code": "oidc_callback_rejected", "message": "Sign-in was rejected or expired.", "retryable": False}})
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                response = await client.post(self.settings.operator_oidc_token_endpoint, data={
                    "grant_type": "authorization_code", "code": code,
                    "redirect_uri": self.settings.operator_oidc_redirect_uri,
                    "client_id": self.settings.operator_oidc_client_id,
                    "code_verifier": flow.verifier,
                    **({"client_secret": self.settings.operator_oidc_client_secret.get_secret_value()}
                       if self.settings.operator_oidc_client_secret else {}),
                })
                response.raise_for_status()
                identity_token = response.json().get("id_token")
            if not isinstance(identity_token, str):
                raise TypeError("missing id token")
            claims = await asyncio.to_thread(self._validate_token, identity_token)
            if not secrets.compare_digest(str(claims.get("nonce", "")), flow.nonce):
                raise ValueError("nonce mismatch")
            aud = claims.get("aud")
            if isinstance(aud, list) and len(aud) != 1:
                raise ValueError("multiple audiences are not accepted for this local client")
            if claims.get("azp", self.settings.operator_oidc_client_id) != self.settings.operator_oidc_client_id:
                raise ValueError("authorized party mismatch")
            key = f"{claims['iss']}|{claims['sub']}"
            mapping = self.settings.operator_oidc_identities.get(key)
            if not mapping:
                raise ValueError("identity is not mapped")
            principal = OperatorPrincipal(mapping.operator_id, mapping.property_id, mapping.permissions)
        except Exception as exc:
            raise HTTPException(401, detail={"error": {"code": "oidc_identity_rejected", "message": "The identity provider response could not be verified.", "retryable": False}}) from exc
        raw_session = self._b64(secrets.token_bytes(32))
        digest = hashlib.sha256(raw_session.encode()).hexdigest()
        now = self.clock()
        self._prune(now)
        self.sessions[digest] = Session(principal, now, now)
        response = Response(status_code=303, headers={"Location": f"{self.settings.operator_oidc_browser_origin}/operator",
                                                      "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        response.set_cookie(COOKIE, raw_session, httponly=True, secure=True, samesite="strict", path="/",
                            max_age=ABSOLUTE_SECONDS)
        response.delete_cookie(FLOW_COOKIE, path="/", httponly=True, secure=True, samesite="lax")
        return response

    def principal(self, request: Request) -> OperatorPrincipal:
        raw = request.cookies.get(COOKIE, "")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        row = self.sessions.get(digest)
        now = self.clock()
        self._prune(now)
        if not raw or row is None or now - row.last_seen >= IDLE_SECONDS or now - row.created_at >= ABSOLUTE_SECONDS:
            self.sessions.pop(digest, None)
            raise HTTPException(401, detail={"error": {"code": "operator_session_expired", "message": "Sign in to continue.", "retryable": False}})
        row.last_seen = now
        return row.principal

    def _validate_token(self, token: str) -> dict[str, Any]:
        client = jwt.PyJWKClient(self.settings.operator_oidc_jwks_uri, timeout=5, cache_keys=True)
        key = client.get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=["RS256", "ES256"],
                          audience=self.settings.operator_oidc_client_id,
                          issuer=self.settings.operator_oidc_issuer,
                          options={"require": ["exp", "iat", "sub", "iss", "aud", "nonce"]})

    def _prune(self, now: float) -> None:
        for state, flow in list(self.flows.items()):
            if flow.expires_at <= now:
                self.flows.pop(state, None)
        for key, session in list(self.sessions.items()):
            if now - session.last_seen >= IDLE_SECONDS or now - session.created_at >= ABSOLUTE_SECONDS:
                self.sessions.pop(key, None)

    def logout(self, request: Request) -> Response:
        raw = request.cookies.get(COOKIE, "")
        self.sessions.pop(hashlib.sha256(raw.encode()).hexdigest(), None)
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, path="/", httponly=True, secure=True, samesite="strict")
        return response

    def require_origin(self, request: Request) -> None:
        if request.headers.get("origin") != self.settings.operator_oidc_browser_origin:
            raise HTTPException(403, detail={"error": {"code": "csrf_origin_rejected", "message": "The request origin is not allowed.", "retryable": False}})
