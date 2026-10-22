"""FastAPI application factory with no startup credentials or external connections."""

from fastapi import FastAPI

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.startup.domain_profile import select_domain_profile


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    profile = select_domain_profile(settings.domain)
    app = FastAPI(title="StayLead Platform API", version="0.1.0")
    app.state.domain_profile = profile

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "domain": profile.name}

    return app


app = create_app()
