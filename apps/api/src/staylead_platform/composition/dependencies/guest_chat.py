"""Composition and application service for anonymous Hospitality guest Q&A."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any
from urllib.parse import urlsplit

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
from staylead_platform.domains.hospitality.recommendations.rooms import HospitalityRoomAdvice
from staylead_platform.domains.hospitality.registration.local_guide import HospitalityLocalGuide
from staylead_platform.domains.hospitality.registration.local_guide_labels import (
    LOCAL_GUIDE_LABEL_KEYS,
    has_reviewed_local_guide_labels,
    local_guide_label_source_texts,
    local_guide_source_status_label,
    local_guide_unknown_label,
    resolve_local_guide_label_bundle,
)
from staylead_platform.domains.hospitality.schemas.fact_selection import FactSelection
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
    committed_answer_output_schema,
)
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    validate_committed_turn_channels,
    validate_guest_brief_proposal,
    validate_preparation_metadata,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    fact_selection_output_schema,
    preparation_answer_output_schema,
)
from staylead_platform.domains.hospitality.validators.guest_clarification import (
    validate_pending_guest_clarification,
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
    get_hotel_by_id,
    get_hotel_by_slug,
    get_language_preference,
    get_room_advice_result,
    get_session,
    recent_messages,
    reserve_request,
    save_room_advice_result,
    select_room_advice_option,
    update_room_advice_presentation,
    validate_evidence_current,
)
from staylead_platform.platform.contracts.ai_provider import AIProvider, ProviderError, Usage
from staylead_platform.platform.contracts.guest_brief import GuestBriefContext, GuestBriefSnapshot
from staylead_platform.platform.contracts.knowledge import (
    ActiveKnowledgeSnapshot,
    EligibleAsset,
    EvidenceBinding,
    MediaDescriptor,
    SourceVersionRef,
)
from staylead_platform.platform.contracts.language import language_direction, normalize_language_tag
from staylead_platform.platform.contracts.local_guide import LocalGuideResult
from staylead_platform.platform.contracts.room_advice import RoomAdviceContext, RoomAdviceResult
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    ConversationAnswer,
    ConversationFailure,
    GroundedQAOrchestrator,
)
from staylead_platform.platform.conversation.responses.presentation_labels import (
    LABEL_KEYS,
    label_source_texts,
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


def _booking_channel(settings: Settings, hotel_slug: str) -> dict[str, Any]:
    """Return only server-configured booking details; never derive a target from facts or chat."""
    raw_url = settings.booking_destination_by_hotel.get(hotel_slug)
    destination: str | None = None
    if isinstance(raw_url, str) and len(raw_url) <= 2048:
        try:
            parsed = urlsplit(raw_url)
            if (raw_url == raw_url.strip() and not any(char.isspace() or ord(char) < 32 for char in raw_url)
                    and "\\" not in raw_url and parsed.scheme.lower() == "https"
                    and parsed.hostname and parsed.username is None and parsed.password is None
                    and not parsed.query and not parsed.fragment and parsed.port in (None, 443)):
                destination = raw_url
        except ValueError:
            destination = None
    contact = settings.booking_contact_by_hotel.get(hotel_slug)
    safe_contact = contact.strip()[:240] if isinstance(contact, str) and contact.strip() else None
    synthetic = bool(destination and urlsplit(destination).hostname and urlsplit(destination).hostname.endswith(".example"))
    return {
        "destination_url": destination,
        "contact": safe_contact,
        "destination_kind": "synthetic_demo" if synthetic else "configured",
    }


def _answer_label_request(language_tag: str, turn_intents: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, str]]:
    """Keep bounded answer labels localized without repeating reviewed domain copy."""
    if "local_guide" in turn_intents and not has_reviewed_local_guide_labels(language_tag):
        language = language_tag.split("-", 1)[0].lower()
        keys = LOCAL_GUIDE_LABEL_KEYS
        missing = () if language == "en" else keys
        return missing, keys, local_guide_label_source_texts() if missing else {}
    missing = tuple(missing_label_keys(language_tag))
    return missing, LABEL_KEYS, label_source_texts(missing)


def _room_advice_json(result: RoomAdviceResult) -> dict[str, Any]:
    value = asdict(result)
    # Make the serialized representation JSON-native so PostgreSQL and replay use
    # the exact same checked snapshot that the web client receives.
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _booking_channel_only_answer(turn_intents: tuple[str, ...], preparation: Any | None = None) -> ConversationAnswer:
    """Create an empty safe turn answer after trusted booking intent classification."""
    return ConversationAnswer(
        answer="", citations=(), unknowns=(), provider=getattr(preparation, "provider", None) or "server",
        deployment=getattr(preparation, "deployment", None) or "server-generated",
        model=getattr(preparation, "model", None), provider_request_id=None, usage=Usage(), retrieval_fact_ids=(), calls=0,
        provider_request_ids=(), turn_intents=turn_intents,
    )


def _room_advice_source_refs(result: RoomAdviceResult, snapshot: ActiveKnowledgeSnapshot,
                            facts: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    trusted_sources = {source.source_id: source for source in snapshot.sources}
    trusted_facts = {fact.get("fact_id"): fact for fact in facts}
    grouped: dict[str, set[str]] = {}
    for raw in result.source_refs:
        item = asdict(raw) if not isinstance(raw, dict) and hasattr(raw, "__dataclass_fields__") else dict(raw)
        source = item.get("source") if isinstance(item.get("source"), dict) else item
        source_id = source.get("source_id")
        trusted = trusted_sources.get(source_id)
        if trusted is None or trusted.hotel_id != snapshot.hotel_id:
            raise StaleSource("room advice cited an unknown hotel source")
        if (source.get("source_version", source.get("version")) != trusted.source_version
                or source.get("source_hash", trusted.source_hash) != trusted.source_hash
                or source.get("source_generation", source.get("hotel_generation", snapshot.generation)) != snapshot.generation):
            raise StaleSource("room advice source reference does not match the active snapshot")
        fact_ids = set(item.get("fact_ids", ()))
        if item.get("fact_id"):
            fact_ids.add(item["fact_id"])
        if source.get("fact_id"):
            fact_ids.add(source["fact_id"])
        if not fact_ids:
            raise StaleSource("room advice source reference is missing its supporting fact id")
        if any(fact_id not in trusted_facts
               or trusted_facts[fact_id].get("provenance", {}).get("source_id") != source_id
               for fact_id in fact_ids):
            raise StaleSource("room advice cited a fact outside the selected source-backed facts")
        grouped.setdefault(source_id, set()).update(fact_ids)
    refs: list[dict[str, Any]] = []
    for source_id, fact_ids in sorted(grouped.items()):
        source = trusted_sources[source_id]
        refs.append({"source": {
            "hotel_id": source.hotel_id, "source_id": source.source_id,
            "hotel_generation": source.hotel_generation, "source_version": source.source_version,
            "source_hash": source.source_hash, "status": source.status,
            "guest_approved": source.guest_approved, "valid_from": source.valid_from,
            "valid_to": source.valid_to, "last_failure": source.last_failure,
            "last_success_at": source.last_success_at,
        }, "fact_ids": sorted(fact_ids)})
    return refs


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
    retriever = None
    repository = None
    if selected_provider:
        repository = PostgresKnowledgeFactRepository(database)
        retriever = KnowledgeRetriever(repository)
        local_guide = HospitalityLocalGuide(
            repository,
            lambda hotel_id, now, timeout: get_active_snapshot(
                database, hotel_id, now=now, timeout_seconds=timeout,
            ),
        )
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
            clarification_validator=validate_pending_guest_clarification,
            committed_output_schema_factory=committed_answer_output_schema,
            preparation_selection_schema_factory=fact_selection_output_schema,
            preparation_answer_schema_factory=preparation_answer_output_schema,
            preparation_metadata_validator=validate_preparation_metadata,
            committed_answer_validator=validate_committed_turn_channels,
            response_envelope_key="response",
            max_output_tokens=settings.ai_max_output_tokens,
            room_advice=HospitalityRoomAdvice(),
            local_guide=local_guide,
        )
    return GuestChatApplication(settings, database, orchestrator, media_repository, retriever, repository)


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


def _local_guide_payload_and_bindings(
    result: LocalGuideResult, snapshot: ActiveKnowledgeSnapshot,
    repository: PostgresKnowledgeFactRepository | None,
    *, timeout_seconds: float, label_bundle: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[EvidenceBinding]]:
    """Bind the domain projection to the exact guest-approved M1 facts in this turn."""
    if result.hotel_id != snapshot.hotel_id or result.generation != snapshot.generation:
        raise StaleSource("local-guide result does not match this hotel's current snapshot")
    fact_ids = tuple(dict.fromkeys(result.fact_ids))
    if fact_ids and repository is None:
        raise StaleSource("local-guide fact repository is unavailable")
    facts = repository.get_guest_facts(
        result.hotel_id, set(fact_ids), timeout_seconds=timeout_seconds,
    ) if fact_ids and repository else []
    facts_by_id = {fact.fact_id: fact for fact in facts}
    if set(facts_by_id) != set(fact_ids):
        raise StaleSource("local-guide facts are no longer guest-visible")
    sources = {source.source_id: source for source in snapshot.sources}
    locale = result.metadata.get("locale") if isinstance(result.metadata, dict) else None
    grouped: dict[str, list[str]] = {}
    for fact in facts:
        provenance = fact.provenance
        source_id = provenance.get("source_id")
        source = sources.get(source_id)
        if (source is None or source.hotel_id != result.hotel_id
                or source.status != "approved" or not source.guest_approved
                or provenance.get("source_version") != source.source_version
                or provenance.get("source_hash") != source.source_hash
                or provenance.get("source_generation") != source.hotel_generation):
            raise StaleSource("local-guide source is no longer current and approved")
        grouped.setdefault(source_id, []).append(fact.fact_id)
    refs: list[dict[str, Any]] = []
    bindings: list[EvidenceBinding] = []
    for source_id, bound_ids in sorted(grouped.items()):
        source = sources[source_id]
        refs.append({"source": {
            "hotel_id": source.hotel_id, "source_id": source.source_id,
            "source_generation": source.hotel_generation,
            "source_version": source.source_version, "source_hash": source.source_hash,
            "status": source.status, "guest_approved": source.guest_approved,
            "valid_from": source.valid_from, "valid_to": source.valid_to,
            "localized_status": local_guide_source_status_label(source.status, locale),
        }, "fact_ids": sorted(bound_ids)})
        bindings.append(EvidenceBinding(source=source, fact_ids=tuple(sorted(bound_ids))))
    payload = asdict(result)
    payload["source_refs"] = refs
    payload["fact_ids"] = list(fact_ids)
    local_labels = resolve_local_guide_label_bundle(
        locale if isinstance(locale, str) else None,
        {key: value for key, value in (label_bundle or {}).items() if key in LOCAL_GUIDE_LABEL_KEYS},
    )
    for claim in payload["supported_claims"]:
        claim["localized_unknowns"] = [
            local_guide_unknown_label(code, locale, local_labels)
            for code in claim.get("unknown_codes", ())
        ]
    unknown_codes = tuple(dict.fromkeys(
        code for claim in payload["supported_claims"] for code in claim.get("unknown_codes", ())
    ))
    payload["localized_unknowns"] = [local_guide_unknown_label(code, locale, local_labels) for code in unknown_codes]
    payload["localized_conflicts"] = [
        local_guide_unknown_label("conflict_unconfirmed", locale, local_labels)
        for _conflict in payload.get("conflicts", ())
    ]
    return payload, bindings


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
        media_repository: Any | None = None, knowledge_retriever: KnowledgeRetriever | None = None,
        knowledge_fact_repository: PostgresKnowledgeFactRepository | None = None,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._orchestrator = orchestrator
        self._media_repository = media_repository or PostgresMediaRepository(engine)
        self._knowledge_retriever = knowledge_retriever
        self._knowledge_fact_repository = knowledge_fact_repository

    def lookup_hotel(self, hotel_slug: str) -> dict[str, Any]:
        try:
            hotel = get_hotel_by_slug(self._engine, hotel_slug)
        except Exception as exc:
            raise GuestChatError(503, "storage_unavailable", "Hotel lookup is unavailable.", retryable=True) from exc
        if not hotel:
            raise GuestChatError(404, "hotel_unavailable", "This hotel is not available.")
        public_config = dict(hotel["public_config"])
        public_config["booking_channel"] = _booking_channel(self._settings, hotel["slug"])
        return {
            "hotel_id": hotel["hotel_id"], "hotel_slug": hotel["slug"],
            "public_config": public_config, "config_version": hotel["config_version"],
            "guest_contract_version": "1",
        }

    def _room_advice_scope(self, session_id: str, token: str) -> str:
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
        if (not session or session["hotel_id"] != claims.hotel_id
                or session["expires_at"] <= datetime.now(UTC)):
            raise GuestChatError(401, "invalid_session", "A valid guest session is required.")
        return claims.hotel_id

    def read_room_advice(self, *, session_id: str, token: str) -> dict[str, Any]:
        hotel_id = self._room_advice_scope(session_id, token)
        try:
            result = get_room_advice_result(self._engine, session_id=session_id, hotel_id=hotel_id)
        except Exception as exc:
            raise GuestChatError(503, "room_advice_unavailable", "Room advice could not be loaded.", retryable=True) from exc
        if result is None:
            raise GuestChatError(404, "room_advice_unavailable", "No room advice is available yet.")
        return self._room_advice_response(result)

    def choose_room_advice_option(
        self, *, session_id: str, token: str, result_id: str,
        result_version: int, option_id: str,
    ) -> dict[str, Any]:
        hotel_id = self._room_advice_scope(session_id, token)
        try:
            selection = select_room_advice_option(
                self._engine, session_id=session_id, hotel_id=hotel_id,
                result_id=result_id, expected_result_version=result_version, option_id=option_id,
            )
        except VersionConflict as exc:
            raise GuestChatError(409, "room_advice_version_conflict", "This room suggestion changed. Refresh before choosing.") from exc
        except StaleSource as exc:
            raise GuestChatError(409, "room_advice_stale", "This room suggestion is out of date. Ask for an updated suggestion.") from exc
        except ScopeError as exc:
            raise GuestChatError(404, "room_advice_unavailable", "This room option is not available in this chat.") from exc
        except Exception as exc:
            raise GuestChatError(503, "room_advice_unavailable", "The room option could not be saved.", retryable=True) from exc
        return selection

    @staticmethod
    def _room_advice_response(record: dict[str, Any]) -> dict[str, Any]:
        payload = dict(record["payload"])
        payload.update({
            "result_id": record["result_id"], "session_id": record["session_id"],
            "hotel_id": record["hotel_id"], "result_version": record["result_version"],
            "brief_version": record["brief_version"], "source_generation": record["source_generation"],
            "config_version": record["config_version"], "policy_version": record.get("policy_version"),
            "price_version": record.get("price_version"),
            "dependency_fingerprint": record["dependency_fingerprint"],
            "currentness": record["currentness"], "selection": record.get("selection"),
        })
        return payload

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
            room_advice_currentness = None
            saved_room_advice = stored.get("room_advice")
            if isinstance(saved_room_advice, dict) and isinstance(saved_room_advice.get("result_id"), str):
                exact_room_result = get_room_advice_result(
                    self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                    result_id=saved_room_advice["result_id"],
                )
                room_advice_currentness = (
                    exact_room_result.get("currentness") if exact_room_result is not None else "stale"
                )
        except GuestChatError:
            raise
        except Exception as exc:
            raise GuestChatError(503, "freshness_unavailable", "Answer freshness could not be checked.", retryable=True) from exc
        room_stale = room_advice_currentness == "stale"
        eligible = bool(freshness.get("eligible") and not brief_stale and not preference_stale and not room_stale)
        return {
            "status": "current" if eligible else "stale",
            "answer_eligibility": "current" if eligible else "stale",
            **({"room_advice_currentness": room_advice_currentness}
               if room_advice_currentness is not None else {}),
        }

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
        public_config = dict(hotel["public_config"])
        public_config["booking_channel"] = _booking_channel(self._settings, hotel["slug"])
        return {
            "session_id": session_id, "access_token": token, "token_type": "Bearer",
            "expires_at": expires_at.isoformat(), "hotel": public_config,
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
            room_advice_stale = False
            cached_advice = cached.get("room_advice")
            if isinstance(cached_advice, dict) and isinstance(cached_advice.get("result_id"), str):
                try:
                    exact_room_result = await asyncio.to_thread(
                        get_room_advice_result, self._engine,
                        session_id=session_id, hotel_id=claims.hotel_id,
                        result_id=cached_advice["result_id"], timeout_seconds=_remaining_seconds(deadline),
                    )
                except Exception as exc:
                    raise GuestChatError(503, "freshness_unavailable", "Room advice freshness could not be checked.", retryable=True) from exc
                if exact_room_result is None:
                    room_advice_stale = True
                    cached_advice = {**cached_advice, "currentness": "stale", "selection": None}
                else:
                    cached_advice = self._room_advice_response(exact_room_result)
                    room_advice_stale = exact_room_result.get("currentness") != "current"
                cached["room_advice"] = cached_advice
                room_fact_ids = {
                    fact_id for ref in (exact_room_result or {}).get("source_refs", [])
                    for fact_id in (ref.get("fact_ids", []) if isinstance(ref, dict) else [])
                }
                if room_fact_ids:
                    filtered_bindings = []
                    for binding in bindings:
                        raw = asdict(binding) if isinstance(binding, EvidenceBinding) else dict(binding)
                        remaining_facts = set(raw.get("fact_ids", ())) - room_fact_ids
                        if remaining_facts or raw.get("media_ids"):
                            filtered_bindings.append({**raw, "fact_ids": sorted(remaining_facts)})
                    bindings = filtered_bindings
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
                else "stale" if presentation_stale or not decision.eligible or brief_stale or room_advice_stale
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
        room_advice_requested = False
        booking_requested = False
        pure_booking_request = False
        language_only_room_advice = False
        room_advice_response: dict[str, Any] | None = None
        room_advice_bindings: list[EvidenceBinding] = []
        local_guide_response: dict[str, Any] | None = None
        local_guide_bindings: list[EvidenceBinding] = []
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
                    saved_answer_payload = saved_receipt.get("answer_payload")
                    saved_turn_intents = (
                        saved_answer_payload.get("turn_intents")
                        if isinstance(saved_answer_payload, dict) else None
                    )
                    saved_authorized_targets = (
                        saved_answer_payload.get("authorized_targets")
                        if isinstance(saved_answer_payload, dict) else None
                    )
                    if (
                        not isinstance(saved_turn_intents, list) or not saved_turn_intents
                        or any(not isinstance(item, str) for item in saved_turn_intents)
                        or not isinstance(saved_authorized_targets, list)
                        or any(not isinstance(item, str) for item in saved_authorized_targets)
                    ):
                        raise GuestChatError(
                            409, "brief_resume_unavailable",
                            "The saved answer is missing its current-turn scope and cannot be resumed safely.",
                        )
                    room_advice_requested = "room_advice" in saved_turn_intents
                    booking_requested = "booking_request" in saved_turn_intents
                    pure_booking_request = tuple(saved_turn_intents) == ("booking_request",)
                    resumed_receipt = saved_receipt["receipt"]
                    committed_brief = await asyncio.to_thread(
                        get_guest_brief, self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                        timeout_seconds=_remaining_seconds(deadline),
                    )
                    receipt_id_for_answer = answer_only_receipt_id
                    if pure_booking_request:
                        answer = _booking_channel_only_answer(tuple(saved_turn_intents))
                    elif not room_advice_requested:
                        resumed_label_request = _answer_label_request(
                            current_language["language_tag"], tuple(saved_turn_intents),
                        )
                        answer = await self._orchestrator.answer_committed_turn(
                            hotel_id=claims.hotel_id, question=source_turn["content"], history=history,
                            brief=committed_brief, deadline=deadline,
                            preferred_language_tag=(current_language_row or {}).get("language_tag"),
                            missing_label_keys=resumed_label_request[0],
                            label_bundle_keys=resumed_label_request[1],
                            label_source_texts=resumed_label_request[2],
                            turn_intents=tuple(saved_turn_intents),
                            authorized_targets=tuple(saved_authorized_targets),
                        )
                    else:
                        answer = None
                else:
                    committed_brief = await asyncio.to_thread(
                        get_guest_brief, self._engine, session_id=session_id, hotel_id=claims.hotel_id,
                        timeout_seconds=_remaining_seconds(deadline),
                    )
                    source_utterance_id = str(uuid.uuid4())
                    language_before_turn = current_language["language_tag"]
                    prepared = await self._orchestrator.prepare_turn(
                        hotel_id=claims.hotel_id, question=transcript_question, history=history,
                        brief=committed_brief, deadline=deadline,
                        source_utterance_id=source_utterance_id,
                        preferred_language_tag=(current_language_row or {}).get("language_tag"),
                        missing_label_keys=tuple(missing_label_keys(current_language["language_tag"])),
                        label_bundle_keys=LABEL_KEYS,
                        label_source_texts=label_source_texts(tuple(missing_label_keys(current_language["language_tag"]))),
                    )
                    room_advice_requested = "room_advice" in prepared.turn_intents
                    booking_requested = "booking_request" in prepared.turn_intents
                    pure_booking_request = tuple(prepared.turn_intents) == ("booking_request",)
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
                        language_only_room_advice = (
                            room_advice_requested
                            and prepared.guest_patch is None
                            and set(prepared.turn_intents) == {"room_advice"}
                            and current_language["language_tag"] != language_before_turn
                        )
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
                            turn_intents=prepared.turn_intents,
                            authorized_targets=tuple(dict.fromkeys(
                                target for authorization in prepared.patch_authorizations
                                for target in authorization.get("target_fields", ())
                            )),
                        )
                        try:
                            validated = validate_guest_brief_proposal(committed_brief, prepared.guest_patch)
                        except ValueError as exc:
                            raise ConversationFailure(
                                "invalid_model_output", "The model returned an invalid guest brief edit.",
                            ) from exc
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
                        committed_label_request = _answer_label_request(
                            current_language["language_tag"], prepared.turn_intents,
                        )
                        answer = None if room_advice_requested else _booking_channel_only_answer(prepared.turn_intents, prepared) if pure_booking_request else await self._orchestrator.answer_committed_turn(
                            hotel_id=claims.hotel_id, question=transcript_question, history=history,
                            brief=committed_brief, deadline=deadline,
                            selected_fact_ids=prepared.selected_fact_ids,
                            preferred_language_tag=current_language["language_tag"] if current_language["source"] != "fallback" else None,
                            missing_label_keys=committed_label_request[0],
                            label_bundle_keys=committed_label_request[1],
                            label_source_texts=committed_label_request[2],
                            turn_intents=prepared.turn_intents,
                            authorized_targets=brief_context.authorized_targets,
                        )
                    elif prepared.provisional_answer is not None:
                        if room_advice_requested:
                            answer = None
                        elif pure_booking_request:
                            answer = _booking_channel_only_answer(prepared.turn_intents, prepared)
                        elif language_race or "local_guide" in prepared.turn_intents:
                            committed_label_request = _answer_label_request(
                                current_language["language_tag"], prepared.turn_intents,
                            )
                            answer = await self._orchestrator.answer_committed_turn(
                                hotel_id=claims.hotel_id, question=transcript_question, history=history,
                                brief=committed_brief, deadline=deadline,
                                selected_fact_ids=prepared.selected_fact_ids,
                                preferred_language_tag=current_language["language_tag"],
                                missing_label_keys=committed_label_request[0],
                                label_bundle_keys=committed_label_request[1],
                                label_source_texts=committed_label_request[2],
                                turn_intents=prepared.turn_intents,
                                authorized_targets=brief_context.authorized_targets if brief_context else (),
                            )
                        else:
                            answer = prepared.provisional_answer
                    else:
                        committed_label_request = _answer_label_request(
                            current_language["language_tag"], prepared.turn_intents,
                        )
                        answer = None if room_advice_requested else _booking_channel_only_answer(prepared.turn_intents, prepared) if pure_booking_request else await self._orchestrator.answer_committed_turn(
                            hotel_id=claims.hotel_id, question=transcript_question, history=history,
                            brief=committed_brief, deadline=deadline,
                            selected_fact_ids=prepared.selected_fact_ids,
                            preferred_language_tag=current_language["language_tag"] if current_language["source"] != "fallback" else None,
                            missing_label_keys=committed_label_request[0],
                            label_bundle_keys=committed_label_request[1],
                            label_source_texts=committed_label_request[2],
                            turn_intents=prepared.turn_intents,
                            authorized_targets=brief_context.authorized_targets if brief_context else (),
                        )
                if room_advice_requested:
                    if committed_brief is None or self._knowledge_retriever is None:
                        raise GuestChatError(503, "room_advice_unavailable", "Room advice context is unavailable.", retryable=True)
                    # Pin the hotel configuration alongside the committed brief before
                    # invoking the provider. A config read after generation would
                    # incorrectly bind an answer to settings it never saw.
                    pinned_hotel = await asyncio.to_thread(get_hotel_by_id, self._engine, claims.hotel_id)
                    if pinned_hotel is None:
                        raise StaleSource("hotel configuration disappeared before room advice generation")
                    pinned_config_version = pinned_hotel["config_version"]
                    if prepared is not None:
                        room_question = transcript_question
                        intent_tags = prepared.turn_intents
                    else:
                        room_question = source_turn["content"]
                        intent_tags = tuple(saved_turn_intents)
                    reusable = None
                    if language_only_room_advice:
                        reusable = await asyncio.to_thread(
                            get_room_advice_result, self._engine, session_id=session_id,
                            hotel_id=claims.hotel_id, timeout_seconds=_remaining_seconds(deadline),
                        )
                    if (reusable is not None and reusable.get("currentness") == "current"
                            and reusable.get("brief_version") == committed_brief.brief_version
                            and reusable.get("config_version") == pinned_config_version):
                        stored_payload = reusable.get("payload") or {}
                        persisted_advice = RoomAdviceResult(
                            status=stored_payload["status"],
                            brief_version=stored_payload["brief_version"],
                            source_generation=stored_payload["source_generation"],
                            source_refs=tuple(stored_payload.get("source_refs", ())),
                            options=tuple(stored_payload.get("options", ())),
                            questions=tuple(stored_payload.get("questions", ())),
                            explanation_inputs=stored_payload.get("explanation_inputs", {}),
                            availability=stored_payload.get("availability", "unknown"),
                            presentation_labels=stored_payload.get("presentation_labels", {}),
                            presentation_locale=stored_payload.get("presentation_locale"),
                        )
                        localized_advice, localization_generation = await self._orchestrator.translate_room_advice(
                            persisted_advice,
                            current_language["language_tag"] if current_language["source"] != "fallback" else None,
                            deadline=deadline,
                        )
                        localized_payload = _room_advice_json(localized_advice)
                        try:
                            reusable = await asyncio.to_thread(
                                update_room_advice_presentation, self._engine,
                                session_id=session_id, hotel_id=claims.hotel_id,
                                result_id=reusable["result_id"],
                                expected_result_version=reusable["result_version"],
                                expected_payload=stored_payload,
                                payload=localized_payload,
                                expected_language_revision=current_language["revision"],
                                timeout_seconds=_remaining_seconds(deadline),
                            )
                        except VersionConflict:
                            # A concurrent language choice or newer result wins. Re-read
                            # that current record instead of overwriting its presentation.
                            reusable = await asyncio.to_thread(
                                get_room_advice_result, self._engine,
                                session_id=session_id, hotel_id=claims.hotel_id,
                                timeout_seconds=_remaining_seconds(deadline),
                            )
                            if reusable is None:
                                raise StaleSource("room advice disappeared during localization")
                        sources_by_id = {source.source_id: source for source in snapshot.sources}
                        room_advice_bindings = [EvidenceBinding(
                            source=sources_by_id[ref["source"]["source_id"]],
                            fact_ids=tuple(ref.get("fact_ids", ())),
                        ) for ref in reusable.get("source_refs", [])
                          if isinstance(ref, dict) and isinstance(ref.get("source"), dict)
                          and ref["source"].get("source_id") in sources_by_id]
                        room_advice_response = self._room_advice_response(reusable)
                        answer = _booking_channel_only_answer(tuple(intent_tags), prepared)
                        if localization_generation is not None:
                            answer = replace(
                                answer, provider=localization_generation.provider,
                                deployment=localization_generation.deployment,
                                model=localization_generation.model,
                                provider_request_id=localization_generation.request_id,
                                usage=localization_generation.usage, calls=1,
                                provider_request_ids=(localization_generation.request_id,)
                                if localization_generation.request_id else (),
                            )
                    else:
                        current_facts = await asyncio.to_thread(
                            self._knowledge_retriever.list_current_facts,
                            claims.hotel_id, timeout_seconds=_remaining_seconds(deadline),
                        )
                        room_context = RoomAdviceContext(
                            hotel_id=claims.hotel_id, brief_version=committed_brief.brief_version,
                            brief_data=committed_brief.data, pending_fields=committed_brief.pending_fields,
                            source_generation=snapshot.generation, facts=tuple(current_facts),
                            question=room_question,
                            locale=current_language["language_tag"] if current_language["source"] != "fallback" else None,
                            turn_intents=tuple(intent_tags),
                            hotel_information_fact_ids=(
                                tuple(prepared.selected_fact_ids)
                                if prepared is not None and "hotel_information" in intent_tags else ()
                            ),
                        )
                        room_result, room_generation = await self._orchestrator.recommend_committed_room_advice(
                            context=room_context, deadline=deadline,
                        )
                        safe_source_refs = _room_advice_source_refs(room_result, snapshot, tuple(current_facts))
                        sources_by_id = {source.source_id: source for source in snapshot.sources}
                        room_advice_bindings = [EvidenceBinding(
                            source=sources_by_id[ref["source"]["source_id"]],
                            fact_ids=tuple(ref["fact_ids"]),
                        ) for ref in safe_source_refs]
                        try:
                            saved_room_result = await asyncio.to_thread(
                                save_room_advice_result, self._engine,
                                session_id=session_id, hotel_id=claims.hotel_id, request_id=request_id,
                                payload=_room_advice_json(room_result),
                                brief_version=room_result.brief_version,
                                source_generation=room_result.source_generation,
                                config_version=pinned_config_version,
                                source_refs=safe_source_refs,
                                policy_version=(room_result.explanation_inputs.get("policy_version")
                                                if isinstance(room_result.explanation_inputs.get("policy_version"), str) else None),
                                price_version=(room_result.explanation_inputs.get("price_version")
                                               if isinstance(room_result.explanation_inputs.get("price_version"), str) else None),
                                expected_state_version=int(session["state_version"]),
                                timeout_seconds=_remaining_seconds(deadline),
                            )
                        except Exception as exc:
                            if isinstance(exc, (StaleSource, VersionConflict, IdempotencyConflict, ScopeError)):
                                raise
                            raise GuestChatError(503, "room_advice_storage_unavailable", "Room advice could not be saved.", retryable=True) from exc
                        room_advice_response = self._room_advice_response(saved_room_result)
                        answer = ConversationAnswer(
                            answer="", citations=(), unknowns=(), provider=room_generation.provider,
                            deployment=room_generation.deployment, model=room_generation.model,
                            provider_request_id=room_generation.request_id, usage=room_generation.usage,
                            retrieval_fact_ids=(), calls=1,
                            provider_request_ids=(room_generation.request_id,) if room_generation.request_id else (),
                            brief_version_used=committed_brief.brief_version, brief_dependent=True,
                            turn_intents=tuple(intent_tags),
                        )
                        if "hotel_information" in intent_tags and room_result.hotel_answer is not None:
                            raw_hotel_answer = asdict(room_result.hotel_answer)
                            selected_ids = set(prepared.selected_fact_ids if prepared is not None else ())
                            facts_by_id = {str(fact.get("fact_id")): fact for fact in current_facts}
                            hotel_claims = raw_hotel_answer.get("supported_claims", [])
                            if any(not set(claim.get("fact_ids", ())) <= selected_ids
                                   or any(fact_id not in facts_by_id for fact_id in claim.get("fact_ids", ()))
                                   for claim in hotel_claims):
                                raise GuestChatError(503, "room_advice_unavailable", "The hotel answer could not be tied to the selected records.", retryable=True)
                            citations = tuple(facts_by_id[fact_id] for claim in hotel_claims for fact_id in claim.get("fact_ids", ()))
                            unique_citations = tuple({fact["fact_id"]: fact for fact in citations}.values())
                            answer_text = "\n".join(format_grounded_claim(
                                claim["text"], [facts_by_id[fact_id] for fact_id in claim.get("fact_ids", ())],
                            ) for claim in hotel_claims)
                            answer = replace(
                                answer, answer=answer_text, citations=unique_citations,
                                # This response contract has one uncertainty channel;
                                # preserve checked conflicts there rather than dropping them.
                                unknowns=tuple(raw_hotel_answer.get("unknowns", ()))
                                + tuple(raw_hotel_answer.get("conflicts", ())),
                            )
                # The orchestrator sets this only when its structured output cites
                # validated canonical brief fields. A supplied brief alone does not
                # make an ordinary grounded FAQ stale on a later trip edit.
                brief_dependent = bool(answer.brief_dependent)
                if answer.local_guide_result is not None:
                    try:
                        local_guide_response, local_guide_bindings = await asyncio.to_thread(
                            _local_guide_payload_and_bindings,
                            answer.local_guide_result, snapshot, self._knowledge_fact_repository,
                            timeout_seconds=_remaining_seconds(deadline), label_bundle=answer.label_bundle,
                        )
                    except StaleSource:
                        raise
                    except Exception as exc:
                        raise GuestChatError(503, "local_guide_unavailable", "The local guide could not be verified.", retryable=True) from exc
                    brief_dependent = True
                brief_version_used = (
                    answer.brief_version_used
                    if answer.brief_version_used is not None
                    else committed_brief.brief_version if brief_dependent and committed_brief is not None else None
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
                bindings = [*_evidence_bindings(evidence, media, snapshot), *room_advice_bindings, *local_guide_bindings]
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
                core_label_bundle = {
                    key: value for key, value in answer.label_bundle.items() if key in LABEL_KEYS
                }
                answer_labels = resolve_label_bundle(answer_locale, core_label_bundle)
                answer_presentation = {
                    "language_tag": answer_locale,
                    "direction": language_direction(answer_locale),
                    "preference_revision": current_language["revision"],
                    "labels": answer_labels,
                    "labels_fallback": labels_fallback(answer_locale),
                    "freshness": "current",
                    "receipt_id": receipt_id_for_answer,
                }
                if answer.local_guide_result is not None:
                    local_guide_bundle = {
                        key: value for key, value in answer.label_bundle.items()
                        if key in LOCAL_GUIDE_LABEL_KEYS
                    }
                    answer_presentation["local_guide_labels"] = resolve_local_guide_label_bundle(
                        answer_locale, local_guide_bundle,
                    )
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
                room_advice_fields = {"room_advice": room_advice_response} if room_advice_response is not None else {}
                local_guide_fields = {"local_guide": local_guide_response} if local_guide_response is not None else {}
                booking_fields = {"booking_request": {"requested": True}} if booking_requested else {}
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
                                     "answer_eligibility": "stale" if language_stale else "current",
                                     **brief_fields, **room_advice_fields, **local_guide_fields, **booking_fields},
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
