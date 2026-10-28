"""Environment-backed settings; loading configuration does not open external connections."""

import hmac

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from staylead_platform.infrastructure.identity.operator import DevOperatorCredential


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STAYLEAD_", env_file=".env", extra="ignore")

    environment: str = "development"
    domain: str = "hospitality"
    database_url: str = "postgresql+psycopg://staylead:change-me@localhost:5432/staylead"
    ai_provider: str = "disabled"
    session_signing_secret: SecretStr | None = None
    # Explicit server-only dev/test credentials. There is deliberately no public default.
    dev_operator_credentials: list[DevOperatorCredential] = Field(default_factory=list, repr=False)
    fixture_root: str | None = None
    ai_timeout_seconds: float = 25.0
    ai_turn_timeout_seconds: float = 45.0
    ai_max_output_tokens: int = 700
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
        return self
