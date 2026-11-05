from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from pydantic import ValidationError
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.identity.oidc_operator import (
    ABSOLUTE_SECONDS,
    COOKIE,
    FLOW_COOKIE,
    IDLE_SECONDS,
    OidcOperatorAuth,
    Session,
)
from staylead_platform.infrastructure.identity.operator import OperatorPrincipal

ISSUER = "https://issuer.test"
CLIENT = "staylead-s21-test"


def settings() -> Settings:
    return Settings(_env_file=None, environment="test", operator_oidc_enabled=True,
                    operator_oidc_issuer=ISSUER,
                    operator_oidc_authorization_endpoint=f"{ISSUER}/authorize",
                    operator_oidc_token_endpoint=f"{ISSUER}/token",
                    operator_oidc_jwks_uri=f"{ISSUER}/jwks", operator_oidc_client_id=CLIENT,
                    operator_oidc_redirect_uri="https://operator.test/api/operator/auth/callback",
                    operator_oidc_browser_origin="https://operator.test",
                    operator_oidc_identities={f"{ISSUER}|subject-a": {
                        "operator_id": "operator-a", "property_id": "HTL-S8-DEMO",
                        "permissions": ["guide:read", "guide:write"],
                    }})


KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def claims(**updates):
    now = int(time.time())
    result = {"iss": ISSUER, "sub": "subject-a", "aud": CLIENT, "iat": now,
              "exp": now + 300, "nonce": "nonce-a"}
    result.update(updates)
    return result


def token_for(key=KEY, **updates):
    return jwt.encode(claims(**updates), key, algorithm="RS256", headers={"kid": "test-key"})


def install_jwks(monkeypatch, key=KEY):
    monkeypatch.setattr(jwt, "PyJWKClient", lambda *_a, **_kw: SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=key.public_key())))


def test_oidc_code_flow_binds_browser_cookie_and_consumes_state(monkeypatch):
    install_jwks(monkeypatch)
    auth = OidcOperatorAuth(settings())
    start = auth.start()
    query = parse_qs(urlsplit(start.headers["location"]).query)
    state = query["state"][0]
    nonce = query["nonce"][0]
    verifier = auth.flows[state].verifier
    verifier_challenge = base64.urlsafe_b64encode(hashlib.sha256(auth.flows[state].verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [verifier_challenge]
    cookie = start.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    assert FLOW_COOKIE in start.headers["set-cookie"]
    assert "secure" in start.headers["set-cookie"].lower()
    assert "httponly" in start.headers["set-cookie"].lower()
    assert "samesite=lax" in start.headers["set-cookie"].lower()

    exchanged = []

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"id_token": token_for(nonce=nonce)}

    class FakeClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, _url, data):
            exchanged.append(data)
            return FakeResponse()

    monkeypatch.setattr("staylead_platform.infrastructure.identity.oidc_operator.httpx.AsyncClient", FakeClient)
    response = asyncio.run(auth.callback("auth-code", state, None, cookie))
    assert response.status_code == 303
    assert COOKIE in response.headers["set-cookie"]
    assert "secure" in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert len(exchanged) == 1
    assert exchanged[0]["code_verifier"] == verifier
    with pytest.raises(HTTPException) as replay:
        asyncio.run(auth.callback("auth-code", state, None, cookie))
    assert replay.value.status_code == 401
    assert len(exchanged) == 1


def test_flow_cookie_transfer_and_unknown_state_fail_before_token_exchange(monkeypatch):
    auth = OidcOperatorAuth(settings())
    start = auth.start()
    query = parse_qs(urlsplit(start.headers["location"]).query)
    exchanges = []

    class FakeClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, *_args, **_kwargs): exchanges.append(True); raise AssertionError("must not exchange")

    monkeypatch.setattr("staylead_platform.infrastructure.identity.oidc_operator.httpx.AsyncClient", FakeClient)
    with pytest.raises(HTTPException):
        asyncio.run(auth.callback("code", query["state"][0], None, "attacker-browser-cookie"))
    with pytest.raises(HTTPException):
        asyncio.run(auth.callback("code", "unissued-state", None, "attacker-browser-cookie"))
    assert not exchanges


@pytest.mark.parametrize("overrides,key", [
    ({"iss": "https://wrong.test"}, KEY),
    ({"aud": "another-client"}, KEY),
    ({"aud": [CLIENT, "another-client"], "azp": CLIENT}, KEY),
    ({"azp": "another-client"}, KEY),
    ({"exp": int(time.time()) - 1}, KEY),
    ({"sub": "unmapped-subject"}, KEY),
    ({"nonce": "wrong-nonce"}, KEY),
    ({}, OTHER_KEY),
])
def test_callback_rejects_invalid_claims_signature_or_unmapped_subject(monkeypatch, overrides, key):
    install_jwks(monkeypatch)
    auth = OidcOperatorAuth(settings())
    start = auth.start()
    query = parse_qs(urlsplit(start.headers["location"]).query)
    state = query["state"][0]
    nonce = query["nonce"][0]
    flow_cookie = start.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    if key is OTHER_KEY:
        install_jwks(monkeypatch, key=KEY)

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            invalid_claims = {"nonce": nonce}
            invalid_claims.update(overrides)
            return {"id_token": token_for(key, **invalid_claims)}

    class FakeClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, *_args, **_kwargs): return FakeResponse()

    monkeypatch.setattr("staylead_platform.infrastructure.identity.oidc_operator.httpx.AsyncClient", FakeClient)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(auth.callback("auth-code", state, None, flow_cookie))
    assert rejected.value.status_code == 401


def test_session_idle_absolute_expiry_and_logout_revoke_cookie_replay():
    now = [10_000.0]
    auth = OidcOperatorAuth(settings(), clock=lambda: now[0])
    principal = OperatorPrincipal("operator-a", "HTL-S8-DEMO", frozenset({"guide:read", "guide:write"}))
    raw = "opaque-random-session-value-for-test"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    auth.sessions[digest] = Session(principal, now[0], now[0])
    request = SimpleNamespace(cookies={COOKIE: raw})
    assert auth.principal(request) == principal
    now[0] += IDLE_SECONDS - 1
    assert auth.principal(request) == principal
    now[0] += IDLE_SECONDS - 1
    assert auth.principal(request) == principal
    now[0] += IDLE_SECONDS
    with pytest.raises(HTTPException) as idle:
        auth.principal(request)
    assert idle.value.status_code == 401

    now[0] += 1
    auth.sessions[digest] = Session(principal, now[0], now[0])
    now[0] += ABSOLUTE_SECONDS - 1
    auth.sessions[digest].last_seen = now[0] - 1
    assert auth.principal(request) == principal
    now[0] += 1
    with pytest.raises(HTTPException) as absolute:
        auth.principal(request)
    assert absolute.value.status_code == 401

    now[0] += 1
    auth.sessions[digest] = Session(principal, now[0], now[0])
    response = auth.logout(request)
    assert response.status_code == 204
    with pytest.raises(HTTPException) as replay:
        auth.principal(request)
    assert replay.value.status_code == 401


def test_write_and_logout_require_exact_origin():
    auth = OidcOperatorAuth(settings())
    allowed = SimpleNamespace(headers={"origin": "https://operator.test"})
    rejected = SimpleNamespace(headers={"origin": "https://attacker.test"})
    auth.require_origin(allowed)
    with pytest.raises(HTTPException) as forbidden:
        auth.require_origin(rejected)
    assert forbidden.value.status_code == 403


def test_oidc_url_validation_requires_https_or_explicit_loopback_opt_in():
    values = {
        "environment": "test", "operator_oidc_enabled": True,
        "operator_oidc_issuer": "http://localhost:18562",
        "operator_oidc_authorization_endpoint": "http://localhost:18562/authorize",
        "operator_oidc_token_endpoint": "http://localhost:18562/token",
        "operator_oidc_jwks_uri": "http://localhost:18562/jwks",
        "operator_oidc_client_id": CLIENT,
        "operator_oidc_redirect_uri": "https://localhost:13561/api/operator/auth/callback",
        "operator_oidc_browser_origin": "https://localhost:13561",
        "operator_oidc_identities": {"http://localhost:18562|subject-a": {
            "operator_id": "operator-a", "property_id": "HTL-S8-DEMO", "permissions": ["guide:read"]}},
    }
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)
    enabled = Settings(_env_file=None, operator_oidc_allow_loopback_http=True, **values)
    assert enabled.operator_oidc_enabled
    with pytest.raises(ValueError):
        Settings(_env_file=None, operator_oidc_allow_loopback_http=True,
                 **{**values, "operator_oidc_browser_origin": "http://localhost:13561",
                    "operator_oidc_redirect_uri": "http://localhost:13561/api/operator/auth/callback"})
    with pytest.raises(ValueError):
        Settings(_env_file=None, operator_oidc_allow_loopback_http=True,
                 **{**values, "operator_oidc_redirect_uri": "https://localhost:13561/callback"})


def test_environment_settings_validation_redacts_oidc_client_secret(monkeypatch):
    marker = "synthetic-review-env-marker-x7jjv588"
    monkeypatch.setenv("STAYLEAD_ENVIRONMENT", "development")
    monkeypatch.setenv("STAYLEAD_OPERATOR_OIDC_ENABLED", "true")
    monkeypatch.setenv("STAYLEAD_OPERATOR_OIDC_CLIENT_SECRET", marker)
    for name in (
        "STAYLEAD_OPERATOR_OIDC_ISSUER",
        "STAYLEAD_OPERATOR_OIDC_AUTHORIZATION_ENDPOINT",
        "STAYLEAD_OPERATOR_OIDC_TOKEN_ENDPOINT",
        "STAYLEAD_OPERATOR_OIDC_JWKS_URI",
        "STAYLEAD_OPERATOR_OIDC_CLIENT_ID",
        "STAYLEAD_OPERATOR_OIDC_REDIRECT_URI",
        "STAYLEAD_OPERATOR_OIDC_BROWSER_ORIGIN",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as invalid_settings:
        Settings(_env_file=None)

    rendered = str(invalid_settings.value)
    assert "Enabled operator OIDC requires fixed issuer" in rendered
    assert marker not in rendered
    assert marker[-12:] not in rendered
