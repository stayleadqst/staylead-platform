# Local operator OIDC

The local operator can use authorization-code flow with PKCE when
`STAYLEAD_OPERATOR_OIDC_ENABLED=true` in a development or test environment.
OIDC settings are server-side only. The API validates the ID token signature
against its configured JWKS URI and checks issuer, one-client audience, expiry,
nonce, and an exact issuer/subject mapping before it issues a local session.

Set one fixed authorization endpoint, token endpoint, JWKS URI, issuer, client
ID, HTTPS browser origin, and callback URI. The callback must be exactly
`<browser-origin>/api/operator/auth/callback`. All provider endpoints must use
the issuer's origin. The Next server must also set
`STAYLEAD_OIDC_AUTHORIZATION_ENDPOINT` and
`STAYLEAD_OPERATOR_BROWSER_ORIGIN`; its proxy allows only those configured
redirect targets and the known operator auth and guide routes.

For an isolated loopback OIDC test provider, set
`STAYLEAD_OPERATOR_OIDC_ALLOW_LOOPBACK_HTTP=true`. That exception applies only
to provider endpoints on loopback. Keep the browser origin and callback on
HTTPS; use a hostname distinct from the provider host so cookie scoping is
unambiguous. Do not use this switch for a public or shared service.

Map each accepted identity explicitly in
`STAYLEAD_OPERATOR_OIDC_IDENTITIES` using a key of
`<issuer>|<subject>` and only the supported `guide:read` and `guide:write`
permissions. Do not put client secrets, database credentials, or signing
material in browser-visible `NEXT_PUBLIC_*` settings.

The browser receives only an opaque `__Host-staylead_operator` cookie. It is
Secure, HttpOnly, SameSite=Strict, and contains no provider token. Flow state,
nonce, PKCE verifier, and session revocation records are held by one API
process. Sessions expire at 30 minutes idle or 8 hours absolute; restarting the
API logs out all operators. This in-memory store is intended for the local
operator slice and is not shared across workers or restarts. Logout revokes the
server-side record. Protected write operations and logout require the exact
configured browser Origin.

When OIDC is disabled, the existing development/test bearer operator path
remains available. When OIDC is enabled, bearer credentials are not accepted
as a fallback.
