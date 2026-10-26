"""Composition and application service for anonymous Hospitality guest Q&A."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.domains.hospitality.grounded_claim_format import format_grounded_claim
from staylead_platform.domains.hospitality.prompts.grounded_qa import (
    COMMITTED_FACT_SELECTION_INSTRUCTIONS,
    COMMITTED_GROUNDED_QA_INSTRUCTIONS,
    FACT_SELECTION_INSTRUCTIONS,
    GROUNDED_QA_INSTRUCTIONS,
)
from staylead_platform.domains.hospitality.schemas.fact_selection import FactSelection
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
    committed_answer_output_schema,
)
from staylead_platform.domains.hospitality.schemas.guest_brief import validate_guest_brief_proposal
from staylead_platform.domains.hospitality.validators.guest_clarification import (
    validate_checkout_clarification,
)
from staylead_platform.infrastructure.ai_provider import FoundryGrokConfig, FoundryGrokProvider
from staylead_platform.infrastructure.codex_provider import CodexCLIProvider
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
    apply_guest_brief_patch,
    commit_language_preference,
    complete_partial_request,
    complete_request,
    create_session,
    fail_request,
    get_active_snapshot,
    get_completed_response,
    get_guest_brief,
    get_guest_brief_receipt,
    get_guest_brief_source_utterance,
    get_hotel_by_slug,
    get_language_preference,
    get_session,
    recent_messages,
    reserve_request,
    validate_evidence_current,
)
from staylead_platform.platform.contracts.ai_provider import AIProvider, ProviderError
from staylead_platform.platform.contracts.guest_brief import GuestBriefContext, GuestBriefSnapshot
from staylead_platform.platform.contracts.knowledge import (
    ActiveKnowledgeSnapshot,
    EligibleAsset,
    EvidenceBinding,
    MediaDescriptor,
    SourceVersionRef,
)
from staylead_platform.platform.contracts.language import language_direction, normalize_language_tag
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    ConversationFailure,
    GroundedQAOrchestrator,
)
from staylead_platform.platform.conversation.responses.presentation_labels import (
    LABEL_KEYS,
    labels_fallback,
    missing_label_keys,
    resolve_label_bundle,
)
from staylead_platform.platform.guest_context.sessions.signing import (
    InvalidSessionToken,
    issue_token,
    verify_token,
)
from staylead_platform.platform.knowledge.retrieval.retriever import KnowledgeRetriever

SESSION_TTL = timedelta(hours=24)
MEDIA_MAX_BYTES = {"image/png": 5 * 1024 * 1024, "video/mp4": 20 * 1024 * 1024, "text/vtt": 256 * 1024}


def _validation_diagnostics_enabled(settings: Settings) -> bool:
    return bool(settings.validation_diagnostics) and settings.environment.lower() in {"development", "test"}


class GuestChatError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False,
                 partial_result: dict[str, Any] | None = None,
                 validation_diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable
        self.partial_result = partial_result
        self.validation_diagnostics = validation_diagnostics


def build_provider(settings: Settings) -> AIProvider | None:
    if settings.ai_provider == "disabled":
        return None
    if settings.ai_provider == "codex_cli":
        if settings.environment.lower() not in {"development", "test"}:
            raise ValueError("The Codex CLI provider is available only in development and test environments.")
        return CodexCLIProvider(
            executable=settings.codex_cli_executable,
            timeout_seconds=settings.ai_timeout_seconds,
            model=settings.codex_cli_model,
            reasoning_effort=settings.codex_cli_reasoning_effort,
        )
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
            committed_instructions=COMMITTED_GROUNDED_QA_INSTRUCTIONS,
            response_schema=HospitalityGroundedAnswer,
            selection_instructions=FACT_SELECTION_INSTRUCTIONS,
            committed_selection_instructions=COMMITTED_FACT_SELECTION_INSTRUCTIONS,
            selection_schema=FactSelection,
            claim_formatter=format_grounded_claim,
            clarification_validator=validate_checkout_clarification,
            committed_output_schema_factory=committed_answer_output_schema,
            response_envelope_key="response",
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


def _sum_known_usage(first: int | None, second: int | None) -> int | None:
    """Only report a total when both provider calls reported that usage field."""
    return None if first is None or second is None else first + second


def _is_database_timeout(exc: OperationalError) -> bool:
    return getattr(getattr(exc, "orig", None), "sqlstate", None) in {"55P03", "57014"}


def _brief_payload(brief: GuestBriefSnapshot) -> dict[str, Any]:
    return {
        "brief_version": brief.brief_version,
        **brief.data,
        "pending_fields": list(brief.pending_fields),
    }


def _receipt_payload(receipt: Any) -> dict[str, Any]:
    value = asdict(receipt)
    value["source_refs"] = [dict(ref) for ref in value.get("source_refs", [])]
    return value


def _language_preference_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {"language_tag": "und", "source": "fallback", "revision": 0}
    return {"language_tag": row["language_tag"], "source": row["source"], "revision": row["revision"]}


def _resume_marker(receipt_id: str) -> str:
    return f"answer-only-resume:{receipt_id}"


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
            brief_stale = False
            if stored.get("brief_dependent"):
                current_brief = get_guest_brief(
                    self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                )
                brief_stale = current_brief.brief_version != stored.get("brief_version_used")
            current_language = get_language_preference(
                self._engine, session_id=session_id, hotel_id=claims.hotel_id,
            )
            preference_stale = (
                (current_language or {}).get("revision", 0)
                != (stored.get("presentation") or {}).get("preference_revision", 0)
            )
        except GuestChatError:
            raise
        except Exception as exc:
            raise GuestChatError(503, "freshness_unavailable", "Answer freshness could not be checked.", retryable=True) from exc
        eligible = bool(freshness.get("eligible") and not brief_stale and not preference_stale)
        return {"status": "current" if eligible else "stale", "answer_eligibility": "current" if eligible else "stale"}

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
            "language_preference": _language_preference_payload(None),
        }

    async def send_message(
        self, *, session_id: str, token: str, request_id: str, question: str | None,
        answer_only_receipt_id: str | None = None,
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
        if (question is None) == (answer_only_receipt_id is None):
            raise GuestChatError(422, "invalid_message", "Provide either a question or an answer-only receipt reference.")
        if question is not None and not question.strip():
            raise GuestChatError(422, "invalid_question", "Question cannot be blank.")
        try:
            current_language_row = await asyncio.to_thread(
                get_language_preference, self._engine, session_id=session_id,
                hotel_id=claims.hotel_id, timeout_seconds=_remaining_seconds(deadline),
            )
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Language preference storage is unavailable.", retryable=True) from exc
        current_language = _language_preference_payload(current_language_row)
        reservation_question = question if question is not None else _resume_marker(answer_only_receipt_id or "")
        try:
            async with asyncio.timeout_at(deadline):
                remaining = _remaining_seconds(deadline)
                cached = await asyncio.to_thread(
                    reserve_request,
                    self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                    request_id=request_id, question=reservation_question, timeout_seconds=remaining,
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
            if str(exc) == "brief_apply_no_effect":
                raise GuestChatError(
                    503, "brief_apply_no_effect",
                    "The trip update was not applied. Submit it again as a new request.", retryable=True,
                ) from exc
            if str(exc) == "brief_apply_outcome_unknown":
                raise GuestChatError(
                    503, "brief_apply_outcome_unknown",
                    "We could not confirm whether the trip update was saved. Retry this same request to check.",
                    retryable=True,
                ) from exc
            raise GuestChatError(409, "request_failed", "This request already failed; submit a new request_id.") from exc
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Request storage is unavailable.", retryable=True) from exc
        if cached is not None:
            try:
                current_brief = await asyncio.to_thread(
                    get_guest_brief, self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                    timeout_seconds=_remaining_seconds(deadline),
                )
                cached["guest_brief"] = _brief_payload(current_brief)
                brief_stale = bool(
                    cached.get("brief_dependent")
                    and cached.get("brief_version_used") != current_brief.brief_version
                )
                receipt_result = await asyncio.to_thread(
                    get_guest_brief_receipt, self._engine, session_id=session_id,
                    hotel_id=claims.hotel_id, receipt_id=request_id,
                    timeout_seconds=_remaining_seconds(deadline),
                )
                if receipt_result:
                    cached["brief_receipt"] = _receipt_payload(receipt_result["receipt"])
                    cached["applied_delta"] = receipt_result["receipt"].applied_delta
                    cached["answer_status"] = receipt_result["receipt"].answer_status
            except Exception as exc:
                raise GuestChatError(503, "freshness_unavailable", "Trip details freshness could not be checked.", retryable=True) from exc
            bindings = cached.get("evidence_bindings") or _evidence_bindings(
                cached.get("evidence", []), cached.get("media", []),
            )
            try:
                decision = await asyncio.to_thread(
                    validate_evidence_current, self._engine, claims.hotel_id, bindings, datetime.now(UTC),
                )
            except Exception as exc:
                raise GuestChatError(503, "freshness_unavailable", "Answer freshness could not be checked.", retryable=True) from exc
            if not decision.eligible and cached.get("status") != "partial_success":
                raise GuestChatError(409, "stale_source", "The saved answer is no longer current. Ask again in a new turn.")
            cached.pop("evidence_bindings", None)
            cached.pop("freshness", None)
            presentation = cached.get("presentation") or {
                "language_tag": current_language["language_tag"],
                "direction": language_direction(current_language["language_tag"]),
                "preference_revision": current_language["revision"],
                "labels": resolve_label_bundle(current_language["language_tag"], None),
                "labels_fallback": labels_fallback(current_language["language_tag"]),
                "freshness": "current", "receipt_id": cached.get("brief_receipt", {}).get("request_id"),
            }
            presentation_stale = presentation.get("preference_revision") != current_language["revision"]
            presentation["freshness"] = "stale" if presentation_stale else "current"
            cached["presentation"] = presentation
            presentation.setdefault("labels_fallback", labels_fallback(presentation["language_tag"]))
            cached["language_preference"] = current_language
            cached["answer_eligibility"] = (
                "pending" if cached.get("status") == "partial_success" or cached.get("answer_status") == "failed"
                else "stale" if presentation_stale or not decision.eligible or brief_stale
                else "current"
            )
            return cached
        if self._orchestrator is None:
            await self._fail_request(session_id, request_id, "provider_unavailable")
            raise GuestChatError(503, "provider_unavailable", "Answer generation is not configured.")
        mutation = None
        brief_context: GuestBriefContext | None = None
        brief_version_used: int | None = None
        brief_dependent = False
        receipt_id_for_answer: str | None = None
        transcript_question = question or "Continue the saved answer using my current trip details."
        committed_brief: GuestBriefSnapshot | None = None
        prepared = None
        resumed_receipt = None
        language_race = False
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
                if answer_only_receipt_id:
                    saved_receipt = await asyncio.to_thread(
                        get_guest_brief_receipt, self._engine, session_id=session_id,
                        hotel_id=claims.hotel_id, receipt_id=answer_only_receipt_id,
                        timeout_seconds=_remaining_seconds(deadline),
                    )
                    source_turn = await asyncio.to_thread(
                        get_guest_brief_source_utterance, self._engine, session_id=session_id,
                        hotel_id=claims.hotel_id, receipt_id=answer_only_receipt_id,
                        timeout_seconds=_remaining_seconds(deadline),
                    )
                    if not saved_receipt or not source_turn or saved_receipt["receipt"].status not in {"applied", "partial_success"}:
                        raise GuestChatError(404, "brief_receipt_unavailable", "The saved trip update is not available for this chat.")
                    if saved_receipt["receipt"].answer_status != "failed":
                        raise GuestChatError(409, "brief_resume_unavailable", "This trip update does not need an answer resume.")
                    resumed_receipt = saved_receipt["receipt"]
                    committed_brief = await asyncio.to_thread(
                        get_guest_brief, self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                        timeout_seconds=_remaining_seconds(deadline),
                    )
                    receipt_id_for_answer = answer_only_receipt_id
                    answer = await self._orchestrator.answer_committed_turn(
                        hotel_id=claims.hotel_id, question=source_turn["content"], history=history,
                        brief=committed_brief, deadline=deadline,
                        preferred_language_tag=(current_language_row or {}).get("language_tag"),
                        missing_label_keys=tuple(missing_label_keys(current_language["language_tag"])),
                        label_bundle_keys=LABEL_KEYS,
                    )
                else:
                    committed_brief = await asyncio.to_thread(
                        get_guest_brief, self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                        timeout_seconds=_remaining_seconds(deadline),
                    )
                    source_utterance_id = str(uuid.uuid4())
                    prepared = await self._orchestrator.prepare_turn(
                        hotel_id=claims.hotel_id, question=transcript_question, history=history,
                        brief=committed_brief, deadline=deadline,
                        source_utterance_id=source_utterance_id,
                        preferred_language_tag=(current_language_row or {}).get("language_tag"),
                        missing_label_keys=tuple(missing_label_keys(current_language["language_tag"])),
                        label_bundle_keys=LABEL_KEYS,
                    )
                    requested_tag = normalize_language_tag(prepared.explicit_language_tag)
                    inferred_tag = normalize_language_tag(prepared.inferred_language_tag)
                    if requested_tag or (current_language_row is None and inferred_tag):
                        expected_language_revision = current_language["revision"]
                        requested_committed_tag = requested_tag or inferred_tag or "und"
                        try:
                            current_language_row = await asyncio.to_thread(
                                commit_language_preference, self._engine,
                                session_id=session_id, hotel_id=claims.hotel_id,
                                language_tag=requested_tag or inferred_tag or "und",
                                source="explicit" if requested_tag else "inferred",
                                expected_revision=current_language["revision"],
                                timeout_seconds=_remaining_seconds(deadline),
                            )
                        except Exception as exc:
                            raise GuestChatError(503, "storage_unavailable", "Language preference could not be saved.", retryable=True) from exc
                        current_language = _language_preference_payload(current_language_row)
                        language_race = (
                            current_language["revision"] == expected_language_revision
                            and current_language["language_tag"] != requested_committed_tag
                        ) or current_language["language_tag"] != requested_committed_tag
                    if prepared.guest_patch is not None:
                        source_utterance_id = prepared.source_utterance_id or source_utterance_id
                        brief_context = GuestBriefContext(
                            session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                            expected_brief_version=committed_brief.brief_version,
                            source_utterance_id=source_utterance_id, source_utterance=transcript_question,
                        )
                        validated = validate_guest_brief_proposal(committed_brief, prepared.guest_patch)
                        apply_attempted = True
                        try:
                            mutation = await asyncio.to_thread(
                                apply_guest_brief_patch, self._engine, context=brief_context,
                                mutation=validated,
                                payload_hash=hashlib.sha256(transcript_question.encode("utf-8")).hexdigest(),
                                timeout_seconds=_remaining_seconds(deadline),
                                deadline_monotonic=deadline_monotonic,
                                cancellation_event=cancellation_event,
                            )
                        except asyncio.CancelledError:
                            cancellation_event.set()
                            recovered = await asyncio.shield(self._resolve_apply_outcome_unknown(
                                session_id=session_id, hotel_id=claims.hotel_id,
                                request_id=request_id, deadline=deadline,
                                uncertain_if_missing=True,
                            ))
                            apply_attempted = False
                            # Replacing the timeout cancellation with the scoped
                            # recovery result lets the outer handler return a
                            # durable partial receipt when the commit succeeded.
                            raise recovered
                        except Exception as exc:
                            if not apply_attempted:
                                raise
                            cancellation_event.set()
                            apply_attempted = False
                            raise await self._resolve_apply_outcome_unknown(
                                session_id=session_id, hotel_id=claims.hotel_id,
                                request_id=request_id, deadline=deadline,
                                uncertain_if_missing=False,
                            ) from exc
                        apply_attempted = False
                        committed_brief = mutation.brief
                        receipt_id_for_answer = request_id
                        answer = await self._orchestrator.answer_committed_turn(
                            hotel_id=claims.hotel_id, question=transcript_question, history=history,
                            brief=committed_brief, deadline=deadline,
                            selected_fact_ids=prepared.selected_fact_ids,
                            preferred_language_tag=current_language["language_tag"] if current_language["source"] != "fallback" else None,
                            missing_label_keys=tuple(missing_label_keys(current_language["language_tag"])),
                            label_bundle_keys=LABEL_KEYS,
                        )
                    elif prepared.provisional_answer is not None:
                        if language_race:
                            answer = await self._orchestrator.answer_committed_turn(
                                hotel_id=claims.hotel_id, question=transcript_question, history=history,
                                brief=committed_brief, deadline=deadline,
                                selected_fact_ids=prepared.selected_fact_ids,
                                preferred_language_tag=current_language["language_tag"],
                                missing_label_keys=tuple(missing_label_keys(current_language["language_tag"])),
                                label_bundle_keys=LABEL_KEYS,
                            )
                        else:
                            answer = prepared.provisional_answer
                    else:
                        answer = await self._orchestrator.answer_committed_turn(
                            hotel_id=claims.hotel_id, question=transcript_question, history=history,
                            brief=committed_brief, deadline=deadline,
                            selected_fact_ids=prepared.selected_fact_ids,
                            preferred_language_tag=current_language["language_tag"] if current_language["source"] != "fallback" else None,
                            missing_label_keys=tuple(missing_label_keys(current_language["language_tag"])),
                            label_bundle_keys=LABEL_KEYS,
                        )
                # The orchestrator sets this only when its structured output cites
                # validated canonical brief fields. A supplied brief alone does not
                # make an ordinary grounded FAQ stale on a later trip edit.
                brief_dependent = bool(answer.brief_dependent)
                brief_version_used = answer.brief_version_used if brief_dependent else None
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
                    "guest_claims_rejected": answer.rejected_guest_claims,
                    "answer_validation": "safe_portion" if answer.rejected_guest_claims else "fully_validated",
                    "usage": {"input_tokens": answer.usage.input_tokens,
                              "output_tokens": answer.usage.output_tokens,
                              "total_tokens": answer.usage.total_tokens},
                    "retrieved_fact_ids": list(answer.retrieval_fact_ids), "failure_stage": None,
                    "preparation_calls": prepared.preparation_calls if prepared else 0,
                }
                preparation_is_answer = bool(prepared and prepared.provisional_answer is answer)
                if prepared and not preparation_is_answer:
                    trace["calls"] = int(trace["calls"]) + prepared.preparation_calls
                    trace["provider_request_ids"] = [*prepared.provider_request_ids, *trace["provider_request_ids"]]
                    trace["usage"] = {
                        "input_tokens": _sum_known_usage(trace["usage"]["input_tokens"], prepared.input_tokens),
                        "output_tokens": _sum_known_usage(trace["usage"]["output_tokens"], prepared.output_tokens),
                        "total_tokens": _sum_known_usage(trace["usage"]["total_tokens"], prepared.total_tokens),
                    }
                    if trace["provider_request_ids"]:
                        trace["provider_request_id"] = trace["provider_request_ids"][-1]
                if resumed_receipt is not None:
                    trace["resume_receipt_id"] = resumed_receipt.request_id
                brief_fields: dict[str, Any] = {}
                if committed_brief is not None:
                    brief_fields["guest_brief"] = _brief_payload(committed_brief)
                if mutation is not None:
                    receipt_payload = _receipt_payload(mutation.receipt)
                    receipt_payload["answer_status"] = "completed"
                    if brief_version_used is not None:
                        receipt_payload["brief_version_used"] = brief_version_used
                    brief_fields["brief_receipt"] = receipt_payload
                    brief_fields["applied_delta"] = mutation.receipt.applied_delta
                    brief_fields["answer_status"] = "completed"
                elif resumed_receipt is not None:
                    receipt_payload = _receipt_payload(resumed_receipt)
                    receipt_payload["answer_status"] = "completed"
                    receipt_payload["brief_version_used"] = brief_version_used
                    brief_fields["brief_receipt"] = receipt_payload
                    brief_fields["applied_delta"] = resumed_receipt.applied_delta
                    brief_fields["answer_status"] = "completed"
                if brief_version_used is not None:
                    answer = replace(answer, brief_version_used=brief_version_used)
                answer_locale = (
                    current_language["language_tag"] if current_language["source"] != "fallback"
                    else normalize_language_tag(answer.inferred_language_tag) or "und"
                )
                answer_labels = resolve_label_bundle(answer_locale, answer.label_bundle)
                answer_presentation = {
                    "language_tag": answer_locale,
                    "direction": language_direction(answer_locale),
                    "preference_revision": current_language["revision"],
                    "labels": answer_labels,
                    "labels_fallback": labels_fallback(answer_locale),
                    "freshness": "current",
                    "receipt_id": receipt_id_for_answer,
                }
                try:
                    latest_language_row = await asyncio.to_thread(
                        get_language_preference, self._engine, session_id=session_id,
                        hotel_id=claims.hotel_id, timeout_seconds=_remaining_seconds(deadline),
                    )
                except Exception as exc:
                    raise GuestChatError(503, "storage_unavailable", "Language preference could not be checked.", retryable=True) from exc
                latest_language = _language_preference_payload(latest_language_row)
                language_stale = latest_language["revision"] != answer_presentation["preference_revision"]
                answer_presentation["freshness"] = "stale" if language_stale else "current"
                remaining = _remaining_seconds(deadline)
                result = await asyncio.to_thread(
                    complete_request,
                    self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                    request_id=request_id, question=transcript_question, answer=answer.answer,
                    evidence=evidence,
                    expected_generation=snapshot.generation,
                    evidence_bindings=bindings,
                    response_fields={"unknowns": list(answer.unknowns),
                                     "guest_claims": list(answer.guest_claims),
                                     "trace": trace, "media": media,
                                     "source_generation": snapshot.generation,
                                     "language_preference": latest_language,
                                     "presentation": answer_presentation,
                                     "answer_eligibility": "stale" if language_stale else "current", **brief_fields},
                    brief_version_used=brief_version_used,
                    brief_dependent=brief_dependent,
                    brief_receipt_id=receipt_id_for_answer,
                    timeout_seconds=remaining,
                    deadline_monotonic=deadline_monotonic, cancellation_event=cancellation_event,
                )
                result.pop("evidence_bindings", None)
                return result
        except GuestChatError as exc:
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code=exc.code, message=str(exc), deadline=deadline,
                ) from exc
            await self._fail_request(session_id, request_id, exc.code)
            raise
        except ProviderError as exc:
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                status = 504 if exc.code == "provider_timeout" else 401 if exc.code == "provider_auth" else 429 if exc.code == "provider_rate_limited" else 502
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code=exc.code, message=str(exc), deadline=deadline, status=status,
                ) from exc
            await self._fail_request(session_id, request_id, exc.code)
            status = 504 if exc.code == "provider_timeout" else 401 if exc.code == "provider_auth" else 429 if exc.code == "provider_rate_limited" else 502
            raise GuestChatError(status, exc.code, str(exc), retryable=exc.retryable) from exc
        except TimeoutError as exc:
            cancellation_event.set()
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code="provider_timeout", message="The request exceeded its time limit.", deadline=deadline,
                ) from exc
            await self._fail_request(session_id, request_id, "provider_timeout")
            raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
        except OperationalError as exc:
            if _is_database_timeout(exc):
                cancellation_event.set()
                if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                    raise await self._partial_failure(
                        session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                        receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                        code="provider_timeout", message="The request exceeded its time limit.", deadline=deadline,
                    ) from exc
                await self._fail_request(session_id, request_id, "provider_timeout")
                raise GuestChatError(504, "provider_timeout", "The request exceeded its time limit.", retryable=True) from exc
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code="storage_unavailable", message="The answer could not be completed.", deadline=deadline,
                ) from exc
            await self._fail_request(session_id, request_id, "storage_unavailable")
            raise GuestChatError(503, "storage_unavailable", "Request storage is unavailable.", retryable=True) from exc
        except ConversationFailure as exc:
            diagnostics = exc.validation_diagnostics if _validation_diagnostics_enabled(self._settings) else None
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code=exc.code, message=str(exc), deadline=deadline,
                    validation_diagnostics=diagnostics,
                ) from exc
            await self._fail_request(session_id, request_id, exc.code)
            status = 503 if exc.code == "provider_failure" else 502
            raise GuestChatError(
                status, exc.code, str(exc), retryable=exc.retryable,
                validation_diagnostics=diagnostics,
            ) from exc
        except ScopeError as exc:
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code="invalid_session", message="The trip update was saved, but the answer could not be completed.", deadline=deadline,
                ) from exc
            await self._fail_request(session_id, request_id, "invalid_session")
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.") from exc
        except VersionConflict as exc:
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code="brief_version_conflict", message="Your trip details were updated, but another change happened before the answer finished.", deadline=deadline,
                ) from exc
            await self._fail_request(session_id, request_id, "state_version_conflict")
            raise GuestChatError(409, "state_version_conflict", "Session state changed; submit a new request_id.") from exc
        except StaleSource as exc:
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code="stale_source", message="Your trip details were updated, but hotel records changed before the answer finished.", deadline=deadline,
                ) from exc
            await self._fail_request(session_id, request_id, "stale_source")
            raise GuestChatError(409, "stale_source", "Hotel records changed while this answer was being prepared. Ask again in a new turn.") from exc
        except Exception as exc:
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                raise await self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code="internal_error", message="Your trip details were updated, but the answer could not be completed.", deadline=deadline,
                ) from exc
            await self._fail_request(session_id, request_id, "internal_error")
            raise GuestChatError(500, "internal_error", "The request could not be completed.") from exc
        except asyncio.CancelledError:
            cancellation_event.set()
            if mutation is not None and mutation.receipt.brief_version_after > mutation.receipt.brief_version_before:
                await asyncio.shield(self._partial_failure(
                    session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                    receipt_id=request_id, brief_version_used=mutation.brief.brief_version,
                    code="request_cancelled", message="Your trip details were updated, but the answer was interrupted.", deadline=deadline,
                ))
            else:
                await self._fail_request(session_id, request_id, "request_cancelled")
            raise

    async def _partial_failure(
        self, *, session_id: str, hotel_id: str, request_id: str, receipt_id: str,
        brief_version_used: int, code: str, message: str, deadline: float, status: int = 502,
        validation_diagnostics: dict[str, Any] | None = None,
    ) -> GuestChatError:
        brief = await asyncio.to_thread(
            get_guest_brief, self._engine, session_id=session_id, hotel_id=hotel_id,
            timeout_seconds=0.5,
        )
        saved = await asyncio.to_thread(
            get_guest_brief_receipt, self._engine, session_id=session_id, hotel_id=hotel_id,
            receipt_id=receipt_id, timeout_seconds=0.5,
        )
        if saved is None:
            raise GuestChatError(503, "receipt_unavailable", "The trip update receipt could not be loaded.", retryable=True)
        receipt = saved["receipt"]
        preference_row = await asyncio.to_thread(
            get_language_preference, self._engine, session_id=session_id,
            hotel_id=hotel_id, timeout_seconds=0.5,
        )
        preference = _language_preference_payload(preference_row)
        partial = {
            "request_id": request_id, "status": "partial_success",
            "error": {"code": code, "message": message},
            "guest_brief": _brief_payload(brief),
            "brief_receipt": _receipt_payload(receipt),
            "applied_delta": receipt.applied_delta,
            "answer_status": "failed",
            "language_preference": preference,
            "presentation": {
                "language_tag": preference["language_tag"],
                "direction": language_direction(preference["language_tag"]),
                "preference_revision": preference["revision"],
                "labels": resolve_label_bundle(preference["language_tag"], None),
                "labels_fallback": labels_fallback(preference["language_tag"]),
                "freshness": "current", "receipt_id": receipt_id,
            },
            "answer_eligibility": "pending",
        }
        if validation_diagnostics is not None:
            partial["error"]["validation_diagnostics"] = validation_diagnostics
        partial = await asyncio.to_thread(
            complete_partial_request, self._engine, session_id=session_id, hotel_id=hotel_id,
            request_id=request_id, response=partial, brief_receipt_id=receipt_id,
            brief_version_used=brief_version_used, timeout_seconds=0.5,
        )
        return GuestChatError(
            status, code, message, retryable=True, partial_result=partial,
            validation_diagnostics=validation_diagnostics,
        )

    async def _resolve_apply_outcome_unknown(
        self, *, session_id: str, hotel_id: str, request_id: str, deadline: float,
        uncertain_if_missing: bool,
    ) -> GuestChatError:
        """Resolve a lost apply acknowledgement without inviting a duplicate edit."""
        lookup_succeeded = False
        try:
            saved = await asyncio.wait_for(asyncio.to_thread(
                get_guest_brief_receipt, self._engine, session_id=session_id,
                hotel_id=hotel_id, receipt_id=request_id, timeout_seconds=0.5,
            ), timeout=0.65)
            lookup_succeeded = True
        except (SQLAlchemyError, TimeoutError, RuntimeError):
            saved = None

        if saved is not None:
            receipt = saved["receipt"]
            if receipt.brief_version_after > receipt.brief_version_before:
                try:
                    return await self._partial_failure(
                        session_id=session_id, hotel_id=hotel_id, request_id=request_id,
                        receipt_id=request_id, brief_version_used=receipt.brief_version_after,
                        code="brief_apply_outcome_unknown",
                        message="Your trip details were saved, but the answer did not finish. Continue from this receipt.",
                        deadline=deadline, status=502,
                    )
                except (SQLAlchemyError, TimeoutError, RuntimeError):
                    # The durable receipt remains recoverable by same-ID replay.
                    lookup_succeeded = False

        code = "brief_apply_outcome_unknown" if uncertain_if_missing or not lookup_succeeded else "brief_apply_no_effect"
        await self._fail_request(session_id, request_id, code)
        if code == "brief_apply_no_effect":
            return GuestChatError(
                503, code,
                "The trip update was not saved. You can submit it again as a new request.", retryable=True,
            )
        return GuestChatError(
            503, code,
            "We could not confirm whether the trip update was saved. Retry this same request to check; do not submit it as a new request.",
            retryable=True,
        )

    async def _fail_request(self, session_id: str, request_id: str, code: str) -> None:
        try:
            await asyncio.wait_for(asyncio.to_thread(
                fail_request, self._engine, session_id=session_id, request_id=request_id,
                code=code, timeout_seconds=0.5,
            ), timeout=0.6)
        except (SQLAlchemyError, TimeoutError):
            # Best effort cleanup must not mask the original timeout/provider failure.
            return
