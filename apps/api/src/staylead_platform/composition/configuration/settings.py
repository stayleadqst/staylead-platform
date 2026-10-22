"""Environment-backed settings; loading configuration does not open external connections."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STAYLEAD_", env_file=".env", extra="ignore")

    environment: str = "development"
    domain: str = "hospitality"
    database_url: str = "postgresql+psycopg://staylead:change-me@localhost:5432/staylead"
    ai_provider: str = "azure_openai"
