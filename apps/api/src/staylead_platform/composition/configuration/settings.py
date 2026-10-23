"""Environment-backed settings; loading configuration does not open external connections."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STAYLEAD_", env_file=".env", extra="ignore")

    environment: str = "development"
    domain: str = "hospitality"
    database_url: str = "postgresql+psycopg://staylead:change-me@localhost:5432/staylead"
    ai_provider: str = "disabled"
    session_signing_secret: SecretStr | None = None
    fixture_root: str | None = None
    ai_timeout_seconds: float = 25.0
    ai_turn_timeout_seconds: float = 45.0
    ai_max_output_tokens: int = 700
    codex_cli_executable: str = "codex"
    codex_cli_model: str = "gpt-6-luna"
    codex_cli_reasoning_effort: str = "low"
    azure_openai_base_url: str | None = Field(default=None, validation_alias="AZURE_OPENAI_BASE_URL")
    azure_openai_api_key: SecretStr | None = Field(default=None, validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_model_deployment: str = Field(
        default="",
        validation_alias="AZURE_OPENAI_MODEL_DEPLOYMENT",
    )
