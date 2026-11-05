"""Environment-backed settings; loading configuration does not open external connections."""

import hmac

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from staylead_platform.infrastructure.identity.operator import (
    DevOperatorCredential,
    OidcOperatorMapping,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STAYLEAD_", env_file=".env", extra="ignore", hide_input_in_errors=True,
    )

    environment: str = "development"
    domain: str = "hospitality"
    database_url: str = "postgresql+psycopg://staylead:change-me@localhost:5432/staylead"
    ai_provider: str = "disabled"
    session_signing_secret: SecretStr | None = None
    # Explicit server-only dev/test credentials. There is deliberately no public default.
    dev_operator_credentials: list[DevOperatorCredential] = Field(default_factory=list, repr=False)
    operator_oidc_enabled: bool = False
    operator_oidc_issuer: str | None = None
    operator_oidc_authorization_endpoint: str | None = None
    operator_oidc_token_endpoint: str | None = None
    operator_oidc_jwks_uri: str | None = None
    operator_oidc_client_id: str | None = None
    operator_oidc_client_secret: SecretStr | None = Field(default=None, repr=False)
    operator_oidc_redirect_uri: str | None = None
    operator_oidc_browser_origin: str | None = None
    operator_oidc_identities: dict[str, OidcOperatorMapping] = Field(default_factory=dict, repr=False)
    operator_oidc_allow_loopback_http: bool = False
    fixture_root: str | None = None
    ai_timeout_seconds: float = 25.0
    ai_turn_timeout_seconds: float = 45.0
    ai_max_output_tokens: int = 700
    guest_request_body_limit_bytes: int = Field(default=65_536, gt=0)
    guest_turns_per_session: int = Field(default=12, gt=0)
    guest_turns_per_hotel: int = Field(default=120, gt=0)
    guest_admission_window_seconds: int = Field(default=600, gt=0)
    guest_in_flight_per_session: int = Field(default=1, gt=0)
    guest_in_flight_per_hotel: int = Field(default=4, gt=0)
    guest_provider_calls_per_request: int = Field(default=2, gt=0)
    session_retention_sweep_interval_seconds: int = Field(default=60, ge=1, le=3600)
    validation_diagnostics: bool = False
    codex_cli_executable: str = "codex"
    codex_cli_model: str = "gpt-6-luna"
    codex_cli_reasoning_effort: str = "low"
    # Server-owned destinations keyed by the trusted hotel slug. These defaults
    # use the reserved .example domain and are explicitly demonstration-only.
    booking_destination_by_hotel: dict[str, str] = Field(default_factory=lambda: {
        "harbor-city-demo": "https://booking.example/hotels/harbor-city-demo",
        "lagoon-family-demo": "https://booking.example/hotels/lagoon-family-demo",
        "pine-ridge-demo": "https://booking.example/hotels/pine-ridge-demo",
    })
    booking_contact_by_hotel: dict[str, str] = Field(default_factory=dict)
    booking_contact_hours_by_hotel: dict[str, str] = Field(default_factory=dict)
    azure_openai_base_url: str | None = Field(default=None, validation_alias="AZURE_OPENAI_BASE_URL")
    azure_openai_api_key: SecretStr | None = Field(default=None, validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_model_deployment: str = Field(
        default="",
        validation_alias="AZURE_OPENAI_MODEL_DEPLOYMENT",
    )

    @model_validator(mode="after")
    def disable_dev_operator_credentials_outside_dev(self) -> "Settings":
        if self.dev_operator_credentials and self.environment.lower() not in {"development", "test"}:
            raise ValueError("Development operator credentials are unavailable outside development and test.")
        token_values = [item.token.get_secret_value().encode("utf-8") for item in self.dev_operator_credentials]
        for index, token in enumerate(token_values):
            if any(hmac.compare_digest(token, other) for other in token_values[index + 1:]):
                raise ValueError("Development operator credentials must use distinct bearer tokens.")
        if self.operator_oidc_enabled:
            if self.environment.lower() not in {"development", "test"}:
                raise ValueError("Local operator OIDC is only available in development and test.")
            required = (self.operator_oidc_issuer, self.operator_oidc_authorization_endpoint,
                        self.operator_oidc_token_endpoint, self.operator_oidc_jwks_uri,
                        self.operator_oidc_client_id, self.operator_oidc_redirect_uri,
                        self.operator_oidc_browser_origin)
            if not all(required):
                raise ValueError("Enabled operator OIDC requires fixed issuer, endpoints, client ID and browser URLs.")
            from urllib.parse import urlsplit
            issuer_parts = urlsplit(self.operator_oidc_issuer or "")
            for raw in (self.operator_oidc_issuer, self.operator_oidc_authorization_endpoint,
                        self.operator_oidc_token_endpoint, self.operator_oidc_jwks_uri):
                parsed = urlsplit(raw or "")
                local_http = (self.operator_oidc_allow_loopback_http and parsed.scheme == "http"
                              and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
                if ((parsed.scheme != "https" and not local_http) or parsed.username or parsed.password
                        or parsed.query or parsed.fragment or (parsed.hostname, parsed.port) != (issuer_parts.hostname, issuer_parts.port)):
                    raise ValueError("Operator OIDC URLs must use HTTPS (loopback HTTP requires explicit opt-in).")
            browser = urlsplit(self.operator_oidc_browser_origin or "")
            callback = urlsplit(self.operator_oidc_redirect_uri or "")
            if (browser.scheme != "https" or not browser.netloc or browser.username or browser.password
                    or browser.path or browser.query or browser.fragment
                    or callback.scheme != "https" or (callback.scheme, callback.netloc) != (browser.scheme, browser.netloc)
                    or callback.path != "/api/operator/auth/callback" or callback.query or callback.fragment
                    or callback.username or callback.password):
                raise ValueError("Operator callback must be the fixed HTTPS callback on the configured browser origin.")
            for key in self.operator_oidc_identities:
                issuer, separator, subject = key.partition("|")
                if not separator or issuer != self.operator_oidc_issuer or not subject or "|" in subject:
                    raise ValueError("OIDC identity map keys must be the fixed issuer followed by one subject.")
        return self
