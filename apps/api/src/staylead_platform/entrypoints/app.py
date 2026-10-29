"""HTTP transport for the composed StayLead guest-chat application."""

from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.engine import Engine

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies.guest_chat import (
    GuestChatError,
    create_guest_chat_application,
)
from staylead_platform.composition.dependencies.operator_guide import (
    create_operator_guide_application,
)
from staylead_platform.composition.startup.domain_profile import select_domain_profile
from staylead_platform.entrypoints.operator.router import router as operator_router
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.platform.contracts.ai_provider import AIProvider

MAX_QUESTION_CHARS = 2000
GUEST_CONTRACT_VERSION = "2"


class RawRequestBodyLimitMiddleware:
    """Reject oversized raw HTTP bodies before any route or parser can dispatch work."""

    def __init__(self, app: Any, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith("/v1/guest/"):
            await self.app(scope, receive, send)
            return
        content_lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        try:
            if content_lengths and max(int(value) for value in content_lengths) > self.max_bytes:
                await self._too_large(send)
                return
        except ValueError:
            # Let the HTTP server/framework report malformed Content-Length headers.
            pass

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._too_large(send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _too_large(self, send: Any) -> None:
        body = b'{"error":{"code":"request_too_large","message":"Request body exceeds the allowed size.","retryable":false}}'
        await send({"type": "http.response.start", "status": 413, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii")),
        ]})
        await send({"type": "http.response.body", "body": body})


class CreateSessionRequest(BaseModel):
    hotel_slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9-]+$")


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    question: str | None = Field(default=None, min_length=1, max_length=MAX_QUESTION_CHARS)
    answer_only_receipt_id: str | None = Field(default=None, min_length=1, max_length=128,
                                               pattern=r"^[A-Za-z0-9._:-]+$")

    @model_validator(mode="after")
    def require_question_or_resume_receipt(self) -> "MessageRequest":
        if (self.question is None) == (self.answer_only_receipt_id is None):
            raise ValueError("Provide either a question or an answer-only receipt reference.")
        return self


class BriefConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    confirmation_token: str = Field(min_length=1, max_length=32_768)


class FreshnessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class SelectRoomAdviceOptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: int = Field(ge=1)
    option_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")


def create_app(
    settings: Settings | None = None,
    *,
    provider: AIProvider | None = None,
    engine: Engine | None = None,
    operator_guide: Any | None = None,
) -> FastAPI:
    selected_settings = settings or Settings()
    profile = select_domain_profile(selected_settings.domain)
    database = engine or create_database_engine(selected_settings.database_url)
    guest_chat = create_guest_chat_application(selected_settings, engine=database, provider=provider)
    selected_operator_guide = operator_guide
    if selected_operator_guide is None:
        selected_operator_guide = create_operator_guide_application(selected_settings, engine=database)
    app = FastAPI(title="StayLead Platform API", version="0.1.0")
    app.add_middleware(
        RawRequestBodyLimitMiddleware,
        max_bytes=selected_settings.guest_request_body_limit_bytes,
    )
    app.state.domain_profile = profile
    app.state.guest_chat = guest_chat
    app.state.settings = selected_settings
    app.state.operator_guide = selected_operator_guide
    app.include_router(operator_router)

    @app.exception_handler(HTTPException)
    async def structured_http_error(_request: Any, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "error": {"code": "request_error", "message": "The request could not be completed.", "retryable": False}
        }
        return JSONResponse(status_code=exc.status_code, content=detail, headers=exc.headers)

    @app.exception_handler(GuestChatError)
    async def guest_chat_error(_request: Any, exc: GuestChatError) -> JSONResponse:
        error: dict[str, Any] = {"code": exc.code, "message": str(exc), "retryable": exc.retryable}
        if (selected_settings.validation_diagnostics
                and selected_settings.environment.lower() in {"development", "test"}
                and exc.validation_diagnostics is not None):
            error["validation_diagnostics"] = exc.validation_diagnostics
        content: dict[str, Any] = {"error": error}
        partial_result = getattr(exc, "partial_result", None)
        if partial_result is not None:
            content.update(partial_result)
            content["error"] = error
        return JSONResponse(status_code=exc.status, content=content)

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
        if body.answer_only_receipt_id is None and (body.question is None or not body.question.strip()):
            raise HTTPException(status_code=422, detail={
                "error": {"code": "invalid_question", "message": "Question cannot be blank.", "retryable": False},
                "request_id": body.request_id,
            })
        if not authorization or not authorization.startswith("Bearer "):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        return await guest_chat.send_message(
            session_id=session_id, token=authorization[7:],
            request_id=body.request_id, question=body.question,
            answer_only_receipt_id=body.answer_only_receipt_id,
        )

    @app.post("/v1/guest/sessions/{session_id}/brief-confirmations", tags=["guest chat"])
    async def confirm_guest_brief_edit(
        session_id: str,
        body: BriefConfirmationRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        return await guest_chat.confirm_brief_edit(
            session_id=session_id,
            token=authorization[7:],
            request_id=body.request_id,
            confirmation_token=body.confirmation_token,
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

    @app.get("/v1/guest/sessions/{session_id}/room-advice", tags=["guest room advice"])
    def read_room_advice(
        session_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        return guest_chat.read_room_advice(session_id=session_id, token=authorization[7:])

    @app.post("/v1/guest/sessions/{session_id}/room-advice/{result_id}/selection", tags=["guest room advice"])
    def choose_room_advice_option(
        session_id: str,
        result_id: str,
        body: SelectRoomAdviceOptionRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        return guest_chat.choose_room_advice_option(
            session_id=session_id, token=authorization[7:], result_id=result_id,
            result_version=body.result_version, option_id=body.option_id,
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
