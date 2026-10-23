"""HTTP transport for the composed StayLead guest-chat application."""

from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies.guest_chat import (
    GuestChatError,
    create_guest_chat_application,
)
from staylead_platform.composition.startup.domain_profile import select_domain_profile
from staylead_platform.platform.contracts.ai_provider import AIProvider

MAX_QUESTION_CHARS = 2000
GUEST_CONTRACT_VERSION = "1"


class CreateSessionRequest(BaseModel):
    hotel_slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9-]+$")


class MessageRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class FreshnessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


def create_app(
    settings: Settings | None = None,
    *,
    provider: AIProvider | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    selected_settings = settings or Settings()
    profile = select_domain_profile(selected_settings.domain)
    guest_chat = create_guest_chat_application(selected_settings, engine=engine, provider=provider)
    app = FastAPI(title="StayLead Platform API", version="0.1.0")
    app.state.domain_profile = profile
    app.state.guest_chat = guest_chat

    @app.exception_handler(HTTPException)
    async def structured_http_error(_request: Any, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "error": {"code": "request_error", "message": "The request could not be completed.", "retryable": False}
        }
        return JSONResponse(status_code=exc.status_code, content=detail, headers=exc.headers)

    @app.exception_handler(GuestChatError)
    async def guest_chat_error(_request: Any, exc: GuestChatError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={
            "error": {"code": exc.code, "message": str(exc), "retryable": exc.retryable},
        })

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "domain": profile.name,
            "guest_contract_version": GUEST_CONTRACT_VERSION,
        }

    @app.post("/v1/guest/sessions", status_code=201, tags=["guest chat"])
    async def open_guest_session(body: CreateSessionRequest) -> dict[str, Any]:
        return guest_chat.open_session(body.hotel_slug)

    @app.get("/v1/guest/hotels/{hotel_slug}", tags=["guest chat"])
    async def lookup_guest_hotel(hotel_slug: str) -> dict[str, Any]:
        return guest_chat.lookup_hotel(hotel_slug)

    @app.post("/v1/guest/sessions/{session_id}/messages", tags=["guest chat"])
    async def send_message(
        session_id: str,
        body: MessageRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not body.question.strip():
            raise HTTPException(status_code=422, detail={
                "error": {"code": "invalid_question", "message": "Question cannot be blank.", "retryable": False},
                "request_id": body.request_id,
            })
        if not authorization or not authorization.startswith("Bearer "):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        return await guest_chat.send_message(
            session_id=session_id, token=authorization[7:],
            request_id=body.request_id, question=body.question,
        )

    @app.post("/v1/guest/sessions/{session_id}/freshness", tags=["guest chat"])
    def check_freshness(
        session_id: str,
        body: FreshnessRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        if not authorization or not authorization.startswith("Bearer "):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        return guest_chat.check_freshness(
            session_id=session_id, token=authorization[7:], request_id=body.request_id,
        )

    @app.get("/v1/guest/sessions/{session_id}/media/{media_id}", tags=["guest media"])
    def get_guest_media(
        session_id: str,
        media_id: str,
        generation: int,
        source_id: str,
        source_version: str,
        source_hash: str,
        sha256: str,
        authorization: str | None = Header(default=None),
    ) -> Response:
        if not authorization or not authorization.startswith("Bearer "):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        asset = guest_chat.read_media(
            session_id=session_id, token=authorization[7:], media_id=media_id,
            generation=generation, source_id=source_id, source_version=source_version,
            source_hash=source_hash, media_sha256=sha256,
        )
        return Response(
            content=asset.content,
            media_type=asset.mime_type,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    return app


app = create_app()
