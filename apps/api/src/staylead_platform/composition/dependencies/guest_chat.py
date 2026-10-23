"""Composition and application service for anonymous Hospitality guest Q&A."""

from __future__ import annotations

import asyncio
import hashlib
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
from staylead_platform.infrastructure.persistence.media_repository import PostgresMediaRepository
from staylead_platform.infrastructure.persistence.store import (
    IdempotencyConflict,
    RequestInProgress,
    ScopeError,
    StaleSource,
    VersionConflict,
    complete_request,
    create_session,
    fail_request,
    get_active_snapshot,
    get_completed_response,
    get_hotel_by_slug,
    get_session,
    recent_messages,
    reserve_request,
    validate_evidence_current,
)
from staylead_platform.platform.contracts.ai_provider import AIProvider, ProviderError
from staylead_platform.platform.contracts.knowledge import (
    ActiveKnowledgeSnapshot,
    EligibleAsset,
    EvidenceBinding,
    MediaDescriptor,
    SourceVersionRef,
)
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
MEDIA_MAX_BYTES = {"image/png": 5 * 1024 * 1024, "video/mp4": 20 * 1024 * 1024, "text/vtt": 256 * 1024}


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
    media_repository = PostgresMediaRepository(database)
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
    return GuestChatApplication(settings, database, orchestrator, media_repository)


def _citation_reference(fact: dict[str, Any], source: SourceVersionRef) -> dict[str, Any]:
    provenance = fact.get("provenance", {})
    return {
        "fact_id": fact["fact_id"], "hotel_id": fact["hotel_id"],
        "source_id": provenance.get("source_id"), "source_version": provenance.get("source_version"),
        "source_hash": source.source_hash, "source_generation": source.hotel_generation,
        "section": provenance.get("section"), "fact_version": provenance.get("fact_version"),
        "imported_at": provenance.get("imported_at"),
    }


def _media_reference(
    media: MediaDescriptor, cited_fact_ids: set[str], source: SourceVersionRef,
) -> dict[str, Any] | None:
    if media.source_version != source.source_version:
        return None
    eligible_facts = sorted(set(media.fact_ids) & cited_fact_ids)
    if not eligible_facts or media.kind not in {"image", "video"}:
        return None
    expected_mime = {"image": "image/png", "video": "video/mp4"}[media.kind]
    if media.mime_type != expected_mime or media.byte_size > MEDIA_MAX_BYTES[expected_mime]:
        return None
    result: dict[str, Any] = {
        "media_id": media.media_id,
        "hotel_id": media.hotel_id,
        "fact_ids": eligible_facts,
        "kind": media.kind,
        "mime_type": media.mime_type,
        "byte_size": media.byte_size,
        "sha256": media.sha256,
        "caption": media.caption,
        "alt_text": media.alt_text,
        "source_id": media.source_id,
        "source_version": media.source_version,
        "source_hash": source.source_hash,
        "source_generation": source.hotel_generation,
    }
    for name in ("start_seconds", "end_seconds", "duration_seconds", "captions_media_id"):
        value = getattr(media, name)
        if value is not None:
            result[name] = value
    if media.captions_sha256 is not None:
        result["captions_sha256"] = media.captions_sha256
    return result


def _evidence_bindings(
    evidence: list[dict[str, Any]], media: list[dict[str, Any]],
    snapshot: ActiveKnowledgeSnapshot | None = None,
) -> list[EvidenceBinding]:
    """Group response evidence by the exact hotel source revision that supplied it."""
    refs = {item.source_id: item for item in snapshot.sources} if snapshot else {}
    grouped: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for collection, rows, id_field in (("facts", evidence, "fact_id"), ("media", media, "media_id")):
        for item in rows:
            source_id = item.get("source_id")
            ref = refs.get(source_id) or SourceVersionRef(
                hotel_id=item.get("hotel_id", ""), source_id=source_id or "",
                hotel_generation=int(item.get("source_generation", 0)),
                source_version=item.get("source_version", ""), source_hash=item.get("source_hash", ""),
                status="approved", guest_approved=True, valid_from="0001-01-01", valid_to="9999-12-31",
            )
            key = (ref.source_id, ref.source_version, ref.source_hash, ref.hotel_generation)
            binding = grouped.setdefault(key, {
                "source": ref, "fact_ids": [], "media_ids": [], "media_sha256": {},
            })
            if collection == "facts":
                binding["fact_ids"].append(item[id_field])
            else:
                binding["media_ids"].append(item[id_field])
                binding["media_sha256"][item[id_field]] = item.get("sha256", "")
                captions_id = item.get("captions_media_id")
                captions_hash = item.get("captions_sha256")
                if captions_id and captions_hash:
                    binding["media_ids"].append(captions_id)
                    binding["media_sha256"][captions_id] = captions_hash
    return [EvidenceBinding(
        source=value["source"], fact_ids=tuple(sorted(set(value["fact_ids"]))),
        media_ids=tuple(sorted(set(value["media_ids"]))), media_sha256=value["media_sha256"],
    ) for value in grouped.values()]


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError("The guest turn deadline expired.")
    return remaining


def _is_database_timeout(exc: OperationalError) -> bool:
    return getattr(getattr(exc, "orig", None), "sqlstate", None) in {"55P03", "57014"}


class GuestChatApplication:
    def __init__(
        self, settings: Settings, engine: Engine, orchestrator: GroundedQAOrchestrator | None,
        media_repository: Any | None = None,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._orchestrator = orchestrator
        self._media_repository = media_repository or PostgresMediaRepository(engine)

    def lookup_hotel(self, hotel_slug: str) -> dict[str, Any]:
        try:
            hotel = get_hotel_by_slug(self._engine, hotel_slug)
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Hotel lookup is unavailable.", retryable=True) from exc
        if not hotel:
            raise GuestChatError(404, "hotel_unavailable", "This hotel is not available.")
        return {
            "hotel_id": hotel["hotel_id"], "hotel_slug": hotel["slug"],
            "public_config": hotel["public_config"], "config_version": hotel["config_version"],
            "guest_contract_version": "1",
        }

    def read_media(
        self, *, session_id: str, token: str, media_id: str, generation: int,
        source_id: str, source_version: str, source_hash: str, media_sha256: str,
    ) -> EligibleAsset:
        if not self._settings.session_signing_secret:
            raise GuestChatError(503, "session_signing_unavailable", "Guest sessions are not configured.")
        try:
            claims = verify_token(token, secret=self._settings.session_signing_secret.get_secret_value())
        except InvalidSessionToken as exc:
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.") from exc
        if claims.session_id != session_id:
            raise GuestChatError(403, "session_scope_mismatch", "The session does not match this request.")
        try:
            session = get_session(self._engine, session_id)
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Session storage is unavailable.", retryable=True) from exc
        if not session or session["hotel_id"] != claims.hotel_id or session["expires_at"] <= datetime.now(UTC):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        try:
            asset = self._media_repository.read_eligible_asset(
                claims.hotel_id, media_id, datetime.now(UTC), expected_generation=generation,
                expected_source_id=source_id, expected_source_version=source_version,
                expected_source_hash=source_hash, expected_media_sha256=media_sha256,
            )
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Media storage is unavailable.", retryable=True) from exc
        if asset is None:
            raise GuestChatError(404, "media_unavailable", "This media is not available.")
        limit = MEDIA_MAX_BYTES.get(asset.mime_type)
        if (
            asset.descriptor.hotel_id != claims.hotel_id
            or asset.descriptor.media_id != media_id
            or asset.descriptor.source_id != source_id
            or asset.descriptor.source_version != source_version
            or asset.descriptor.source_hash != source_hash
            or asset.mime_type != asset.descriptor.mime_type
            or limit is None
            or len(asset.content) != asset.descriptor.byte_size
            or len(asset.content) > limit
            or hashlib.sha256(asset.content).hexdigest() != media_sha256
            or asset.descriptor.sha256 != media_sha256
        ):
            raise GuestChatError(404, "media_unavailable", "This media is not available.")
        return asset

    def check_freshness(
        self, *, session_id: str, token: str, request_id: str,
    ) -> dict[str, str]:
        if not self._settings.session_signing_secret:
            raise GuestChatError(503, "session_signing_unavailable", "Guest sessions are not configured.")
        try:
            claims = verify_token(token, secret=self._settings.session_signing_secret.get_secret_value())
        except InvalidSessionToken as exc:
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.") from exc
        if claims.session_id != session_id:
            raise GuestChatError(403, "session_scope_mismatch", "The session does not match this request.")
        try:
            session = get_session(self._engine, session_id)
            if not session or session["hotel_id"] != claims.hotel_id or session["expires_at"] <= datetime.now(UTC):
                raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
            stored = get_completed_response(
                self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                request_id=request_id, now=datetime.now(UTC),
            )
            if stored is None:
                raise GuestChatError(404, "response_unavailable", "The saved answer is not available.")
            freshness = stored.get("freshness", {})
        except GuestChatError:
            raise
        except Exception as exc:
            raise GuestChatError(503, "freshness_unavailable", "Answer freshness could not be checked.", retryable=True) from exc
        return {"status": "current" if freshness.get("eligible") else "stale"}

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
            bindings = cached.get("evidence_bindings") or _evidence_bindings(
                cached.get("evidence", []), cached.get("media", []),
            )
            try:
                decision = await asyncio.to_thread(
                    validate_evidence_current, self._engine, claims.hotel_id, bindings, datetime.now(UTC),
                )
            except Exception as exc:
                raise GuestChatError(503, "freshness_unavailable", "Answer freshness could not be checked.", retryable=True) from exc
            if not decision.eligible:
                raise GuestChatError(409, "stale_source", "The saved answer is no longer current. Ask again in a new turn.")
            cached.pop("evidence_bindings", None)
            cached.pop("freshness", None)
            return cached
        if self._orchestrator is None:
            await self._fail_request(session_id, request_id, "provider_unavailable")
            raise GuestChatError(503, "provider_unavailable", "Answer generation is not configured.")
        try:
            async with asyncio.timeout_at(deadline):
                remaining = _remaining_seconds(deadline)
                snapshot = await asyncio.to_thread(
                    get_active_snapshot, self._engine, claims.hotel_id, now=datetime.now(UTC),
                    timeout_seconds=_remaining_seconds(deadline),
                )
                if snapshot is None:
                    raise GuestChatError(404, "hotel_unavailable", "This hotel's records are unavailable.")
                source_refs = {source.source_id: source for source in snapshot.sources}
                history = await asyncio.to_thread(
                    recent_messages, self._engine, session_id, claims.hotel_id,
                    timeout_seconds=_remaining_seconds(deadline),
                )
                answer = await self._orchestrator.answer(
                    hotel_id=claims.hotel_id, question=question, history=history, deadline=deadline,
                )
                cited_fact_ids = {str(fact["fact_id"]) for fact in answer.citations if fact.get("fact_id")}
                try:
                    candidate_media = await asyncio.to_thread(
                        self._media_repository.list_eligible_media,
                        claims.hotel_id, cited_fact_ids, datetime.now(UTC),
                        timeout_seconds=_remaining_seconds(deadline),
                    ) if cited_fact_ids else []
                except OperationalError as exc:
                    if _is_database_timeout(exc):
                        cancellation_event.set()
                        raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
                    raise GuestChatError(503, "media_lookup_unavailable", "Approved media could not be loaded.", retryable=True) from exc
                except TimeoutError as exc:
                    cancellation_event.set()
                    raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
                except Exception as exc:
                    raise GuestChatError(503, "media_lookup_unavailable", "Approved media could not be loaded.", retryable=True) from exc
                media = [
                    projected for item in sorted(candidate_media, key=lambda value: value.media_id)
                    if item.hotel_id == claims.hotel_id
                    and item.source_id in source_refs
                    and (projected := _media_reference(item, cited_fact_ids, source_refs[item.source_id])) is not None
                ]
                evidence = []
                for fact in answer.citations:
                    source_id = fact.get("provenance", {}).get("source_id")
                    source = source_refs.get(source_id)
                    if source is None or fact.get("provenance", {}).get("source_version") != source.source_version:
                        raise StaleSource("retrieved evidence no longer matches active source state")
                    evidence.append(_citation_reference(fact, source))
                bindings = _evidence_bindings(evidence, media, snapshot)
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
                    evidence=evidence,
                    expected_generation=snapshot.generation,
                    evidence_bindings=bindings,
                    response_fields={"unknowns": list(answer.unknowns), "trace": trace, "media": media,
                                     "source_generation": snapshot.generation},
                    timeout_seconds=remaining,
                    deadline_monotonic=deadline_monotonic, cancellation_event=cancellation_event,
                )
                result.pop("evidence_bindings", None)
                return result
        except GuestChatError as exc:
            await self._fail_request(session_id, request_id, exc.code)
            raise
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
        except StaleSource as exc:
            await self._fail_request(session_id, request_id, "stale_source")
            raise GuestChatError(409, "stale_source", "Hotel records changed while this answer was being prepared. Ask again in a new turn.") from exc
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
