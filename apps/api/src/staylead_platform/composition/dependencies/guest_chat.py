"""Composition and application service for anonymous Hospitality guest Q&A."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.domains.hospitality.prompts.grounded_qa import (
    FACT_SELECTION_INSTRUCTIONS,
    GROUNDED_QA_INSTRUCTIONS,
)
from staylead_platform.domains.hospitality.schemas.fact_selection import FactSelection
from staylead_platform.domains.hospitality.schemas.grounded_answer import HospitalityGroundedAnswer
from staylead_platform.infrastructure.ai_provider import FoundryGrokConfig, FoundryGrokProvider
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.knowledge_repository import (
    PostgresKnowledgeFactRepository,
)
from staylead_platform.infrastructure.persistence.store import (
    IdempotencyConflict,
    RequestInProgress,
    ScopeError,
    VersionConflict,
    complete_request,
    create_session,
    fail_request,
    get_hotel_by_slug,
    get_session,
    recent_messages,
    reserve_request,
)
from staylead_platform.platform.contracts.ai_provider import AIProvider, ProviderError
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    ConversationFailure,
    GroundedQAOrchestrator,
)
from staylead_platform.platform.guest_context.sessions.signing import (
    InvalidSessionToken,
    issue_token,
    verify_token,
)
from staylead_platform.platform.knowledge.retrieval.retriever import KnowledgeRetriever

SESSION_TTL = timedelta(hours=24)


class GuestChatError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable


def build_provider(settings: Settings) -> AIProvider | None:
    if settings.ai_provider == "disabled":
        return None
    if settings.ai_provider != "foundry_grok":
        raise ValueError("Unsupported AI provider configuration.")
    if (not settings.azure_openai_base_url or not settings.azure_openai_api_key
            or not settings.azure_openai_model_deployment):
        raise ValueError("Foundry Grok requires server-side endpoint, credential, and deployment configuration.")
    return FoundryGrokProvider(FoundryGrokConfig(
        base_url=settings.azure_openai_base_url,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_model_deployment,
        timeout_seconds=settings.ai_timeout_seconds,
    ))


def create_guest_chat_application(
    settings: Settings, engine: Engine | None = None, provider: AIProvider | None = None,
) -> GuestChatApplication:
    database = engine or create_database_engine(settings.database_url)
    selected_provider = provider if provider is not None else build_provider(settings)
    orchestrator = None
    if selected_provider:
        repository = PostgresKnowledgeFactRepository(database)
        retriever = KnowledgeRetriever(repository)
        orchestrator = GroundedQAOrchestrator(
            provider=selected_provider,
            retriever=retriever,
            instructions=GROUNDED_QA_INSTRUCTIONS,
            response_schema=HospitalityGroundedAnswer,
            selection_instructions=FACT_SELECTION_INSTRUCTIONS,
            selection_schema=FactSelection,
            max_output_tokens=settings.ai_max_output_tokens,
        )
    return GuestChatApplication(settings, database, orchestrator)


def _citation_reference(fact: dict[str, Any]) -> dict[str, Any]:
    provenance = fact.get("provenance", {})
    return {
        "fact_id": fact["fact_id"], "hotel_id": fact["hotel_id"],
        "source_id": provenance.get("source_id"), "source_version": provenance.get("source_version"),
        "section": provenance.get("section"), "fact_version": provenance.get("fact_version"),
        "imported_at": provenance.get("imported_at"),
    }


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError("The guest turn deadline expired.")
    return remaining


def _is_database_timeout(exc: OperationalError) -> bool:
    return getattr(getattr(exc, "orig", None), "sqlstate", None) in {"55P03", "57014"}


class GuestChatApplication:
    def __init__(self, settings: Settings, engine: Engine, orchestrator: GroundedQAOrchestrator | None) -> None:
        self._settings = settings
        self._engine = engine
        self._orchestrator = orchestrator

    def open_session(self, hotel_slug: str) -> dict[str, Any]:
        try:
            hotel = get_hotel_by_slug(self._engine, hotel_slug)
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Session storage is unavailable.", retryable=True) from exc
        if not hotel:
            raise GuestChatError(404, "hotel_unavailable", "This hotel is not available.")
        if not self._settings.session_signing_secret:
            raise GuestChatError(503, "session_signing_unavailable", "Guest sessions are not configured.")
        session_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + SESSION_TTL
        try:
            create_session(self._engine, session_id, hotel["hotel_id"], expires_at)
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Session storage is unavailable.", retryable=True) from exc
        token = issue_token(
            secret=self._settings.session_signing_secret.get_secret_value(),
            session_id=session_id, hotel_id=hotel["hotel_id"], expires_at=int(expires_at.timestamp()),
        )
        return {
            "session_id": session_id, "access_token": token, "token_type": "Bearer",
            "expires_at": expires_at.isoformat(), "hotel": hotel["public_config"],
            "config_version": hotel["config_version"],
        }

    async def send_message(
        self, *, session_id: str, token: str, request_id: str, question: str,
    ) -> dict[str, Any]:
        if not self._settings.session_signing_secret:
            raise GuestChatError(503, "session_signing_unavailable", "Guest sessions are not configured.")
        try:
            claims = verify_token(token, secret=self._settings.session_signing_secret.get_secret_value())
        except InvalidSessionToken as exc:
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.") from exc
        if claims.session_id != session_id:
            raise GuestChatError(403, "session_scope_mismatch", "The session does not match this request.")
        loop = asyncio.get_running_loop()
        turn_timeout = max(1.0, min(self._settings.ai_turn_timeout_seconds, 90.0))
        deadline = loop.time() + turn_timeout
        deadline_monotonic = time.monotonic() + turn_timeout
        cancellation_event = Event()
        try:
            async with asyncio.timeout_at(deadline):
                remaining = _remaining_seconds(deadline)
                session = await asyncio.to_thread(
                    get_session, self._engine, session_id, timeout_seconds=remaining,
                )
        except TimeoutError as exc:
            raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
        except OperationalError as exc:
            if _is_database_timeout(exc):
                raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
            raise GuestChatError(503, "storage_unavailable", "Session storage is unavailable.", retryable=True) from exc
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Session storage is unavailable.", retryable=True) from exc
        if not session or session["hotel_id"] != claims.hotel_id or session["expires_at"] <= datetime.now(UTC):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        try:
            async with asyncio.timeout_at(deadline):
                remaining = _remaining_seconds(deadline)
                cached = await asyncio.to_thread(
                    reserve_request,
                    self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                    request_id=request_id, question=question, timeout_seconds=remaining,
                    deadline_monotonic=deadline_monotonic, cancellation_event=cancellation_event,
                )
        except TimeoutError as exc:
            cancellation_event.set()
            raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
        except OperationalError as exc:
            if _is_database_timeout(exc):
                cancellation_event.set()
                raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
            raise GuestChatError(503, "storage_unavailable", "Request storage is unavailable.", retryable=True) from exc
        except IdempotencyConflict as exc:
            raise GuestChatError(409, "idempotency_conflict", "request_id was used with different request data.") from exc
        except RequestInProgress as exc:
            raise GuestChatError(409, "request_in_progress", "This request is still processing.", retryable=True) from exc
        except RuntimeError as exc:
            raise GuestChatError(409, "request_failed", "This request already failed; submit a new request_id.") from exc
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Request storage is unavailable.", retryable=True) from exc
        if cached is not None:
            return cached
        if self._orchestrator is None:
            await self._fail_request(session_id, request_id, "provider_unavailable")
            raise GuestChatError(503, "provider_unavailable", "Answer generation is not configured.")
        try:
            async with asyncio.timeout_at(deadline):
                remaining = _remaining_seconds(deadline)
                history = await asyncio.to_thread(
                    recent_messages, self._engine, session_id, claims.hotel_id,
                    timeout_seconds=remaining,
                )
                answer = await self._orchestrator.answer(
                    hotel_id=claims.hotel_id, question=question, history=history, deadline=deadline,
                )
                trace = {
                    "provider": answer.provider, "deployment": answer.deployment, "model": answer.model,
                    "provider_request_id": answer.provider_request_id,
                    "provider_request_ids": list(answer.provider_request_ids), "calls": answer.calls,
                    "usage": {"input_tokens": answer.usage.input_tokens,
                              "output_tokens": answer.usage.output_tokens,
                              "total_tokens": answer.usage.total_tokens},
                    "retrieved_fact_ids": list(answer.retrieval_fact_ids), "failure_stage": None,
                }
                remaining = _remaining_seconds(deadline)
                result = await asyncio.to_thread(
                    complete_request,
                    self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                    request_id=request_id, question=question, answer=answer.answer,
                    evidence=[_citation_reference(fact) for fact in answer.citations],
                    response_fields={"unknowns": list(answer.unknowns), "trace": trace},
                    timeout_seconds=remaining,
                    deadline_monotonic=deadline_monotonic, cancellation_event=cancellation_event,
                )
                return result
        except ProviderError as exc:
            await self._fail_request(session_id, request_id, exc.code)
            status = 504 if exc.code == "provider_timeout" else 401 if exc.code == "provider_auth" else 429 if exc.code == "provider_rate_limited" else 502
            raise GuestChatError(status, exc.code, str(exc), retryable=exc.retryable) from exc
        except TimeoutError as exc:
            cancellation_event.set()
            await self._fail_request(session_id, request_id, "provider_timeout")
            raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
        except OperationalError as exc:
            if _is_database_timeout(exc):
                cancellation_event.set()
                await self._fail_request(session_id, request_id, "provider_timeout")
                raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
            await self._fail_request(session_id, request_id, "storage_unavailable")
            raise GuestChatError(503, "storage_unavailable", "Request storage is unavailable.", retryable=True) from exc
        except ConversationFailure as exc:
            await self._fail_request(session_id, request_id, exc.code)
            status = 503 if exc.code == "provider_failure" else 502
            raise GuestChatError(status, exc.code, str(exc), retryable=exc.retryable) from exc
        except ScopeError as exc:
            await self._fail_request(session_id, request_id, "invalid_session")
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.") from exc
        except VersionConflict as exc:
            await self._fail_request(session_id, request_id, "state_version_conflict")
            raise GuestChatError(409, "state_version_conflict", "Session state changed; submit a new request_id.") from exc
        except Exception as exc:
            await self._fail_request(session_id, request_id, "internal_error")
            raise GuestChatError(500, "internal_error", "The request could not be completed.") from exc
        except asyncio.CancelledError:
            cancellation_event.set()
            await self._fail_request(session_id, request_id, "request_cancelled")
            raise

    async def _fail_request(self, session_id: str, request_id: str, code: str) -> None:
        try:
            await asyncio.wait_for(asyncio.to_thread(
                fail_request, self._engine, session_id=session_id, request_id=request_id,
                code=code, timeout_seconds=0.5,
            ), timeout=0.6)
        except (SQLAlchemyError, TimeoutError):
            # Best effort cleanup must not mask the original timeout/provider failure.
            return
