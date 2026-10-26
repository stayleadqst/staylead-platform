"""Bounded M3 knowledge Q&A with conditional semantic fact selection."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ValidationError

from staylead_platform.platform.contracts.ai_provider import (
    AIProvider,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefProposal,
    GuestBriefSnapshot,
    PreparedGuestTurn,
)
from staylead_platform.platform.knowledge.retrieval.retriever import KnowledgeRetriever

# Keep punctuation that carries literal meaning. Numeric boundaries stop only
# adjacent digits so CJK text and attached units cannot truncate the literal.
# Dates are lexical (no parsing); time ranges remain two independent times.
_NUMBER = re.compile(
    r"(?<!\d)(?:\d+(?:[-/]\d+){2}|\d{1,2}:\d{2}(?::\d{2})?|\d+(?:[.,]\d+)*)(?!\d)"
)
_URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
_FACT_REFERENCE = re.compile(r"\[(F-[A-Za-z0-9-]+)\]")
_FACT_TOKEN = re.compile(r"(?<![A-Za-z0-9])F-[A-Za-z0-9-]+")
_MODEL_FACT_FIELDS = ("fact_id", "topic", "subject", "field", "value", "conditions", "status")
_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_DIAGNOSTIC_ERROR_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_VALIDATION_FIELDS = frozenset({
    "supported_claims", "text", "fact_ids", "unknowns", "conflicts", "guest_patch", "ops", "op",
    "set_dates", "set_adults", "add_child", "set_child_age", "remove_child", "clarify",
    "check_in", "check_out", "count", "age", "member_id", "reason", "guest_claims", "refs",
    "guest_brief_refs", "explicit_language_tag", "inferred_language_tag", "label_bundle",
})


class ValidationDiagnosticError(TypedDict):
    loc: list[str | int]
    type: str


class ValidationDiagnostics(TypedDict):
    code: Literal["model_validation"]
    error_count: int
    errors: list[ValidationDiagnosticError]


def _validation_diagnostics(error: ValidationError) -> ValidationDiagnostics:
    """Return bounded schema paths/types only; omit model-provided values and context."""
    details = error.errors(include_url=False, include_context=False, include_input=False)
    sanitized: list[ValidationDiagnosticError] = []
    for item in details[:8]:
        loc: list[str | int] = []
        for part in item.get("loc", ())[:12]:
            if isinstance(part, int) or isinstance(part, str) and part in _SAFE_VALIDATION_FIELDS:
                loc.append(part)
            else:
                loc.append("<key>")
        error_type = item.get("type")
        sanitized.append({
            "loc": loc,
            "type": error_type if isinstance(error_type, str) and _DIAGNOSTIC_ERROR_TYPE.fullmatch(error_type)
            else "validation_error",
        })
    return {"code": "model_validation", "error_count": len(details), "errors": sanitized}


def _clean_language_tag(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 64 or not _LANGUAGE_TAG.fullmatch(candidate):
        return None
    parts = candidate.split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(part.upper() if len(part) == 2 and part.isalpha() else part.title() if len(part) == 4 and part.isalpha() else part.lower())
    return "-".join(normalized)


def _complete_usage_sum(results: list[GenerationResult], metric: str) -> int | None:
    values = [getattr(item.usage, metric) for item in results]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


class ConversationFailure(RuntimeError):
    def __init__(
        self, code: str, message: str, *, retryable: bool = False,
        validation_diagnostics: ValidationDiagnostics | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.validation_diagnostics = validation_diagnostics
        self.reason = reason


@dataclass(frozen=True)
class ConversationAnswer:
    answer: str
    citations: tuple[dict[str, Any], ...]
    unknowns: tuple[str, ...]
    provider: str
    deployment: str
    model: str | None
    provider_request_id: str | None
    usage: Usage
    retrieval_fact_ids: tuple[str, ...]
    calls: int
    provider_request_ids: tuple[str, ...]
    guest_patch: GuestBriefProposal | None = None
    guest_claims: tuple[dict[str, Any], ...] = ()
    rejected_guest_claims: int = 0
    brief_version_used: int | None = None
    brief_dependent: bool = False
    guest_brief_refs: tuple[str, ...] = ()
    explicit_language_tag: str | None = None
    inferred_language_tag: str | None = None
    label_bundle: dict[str, str] = field(default_factory=dict)


def _numeric_forms(text: str) -> set[str]:
    forms: set[str] = set()
    for item in _NUMBER.findall(text):
        canonical = "".join(
            str(unicodedata.decimal(char)) if char.isdecimal() else char
            for char in item
        )
        if any(char.isdecimal() for char in item):
            forms.add(canonical)
    return forms


def _validate_supported_literals(answer: str, cited_facts: list[dict[str, Any]]) -> None:
    trusted = json.dumps([
        {"value": fact.get("value"), "conditions": fact.get("conditions", {})}
        for fact in cited_facts
    ], ensure_ascii=False)
    without_citations = re.sub(r"\[F-[A-Za-z0-9-]+\]", "", answer)
    evidence_urls = {url.rstrip(".,;:!?)") for url in _URL.findall(trusted)}
    if any(url.rstrip(".,;:!?)") not in evidence_urls for url in _URL.findall(answer)):
        raise ConversationFailure(
            "unsupported_output", "The model returned an unsupported URL.", reason="unsupported_url",
        )
    if _numeric_forms(without_citations) - _numeric_forms(trusted):
        raise ConversationFailure(
            "unsupported_output", "The model returned an unsupported number.", reason="unsupported_number",
        )


def _question_url_fact_ids(
    question: str, hotel_id: str, facts: tuple[dict[str, Any], ...], allowed_ids: set[str],
) -> set[str]:
    """Keep preliminary same-hotel URL evidence available after semantic selection.

    Retrieval supplies current guest-visible facts. The ID must also be in the candidate
    index, and the exact URL must occur in both question and fact. Claims still cite it.
    """
    question_urls = {url.rstrip(".,;:!?)") for url in _URL.findall(question)}
    if not question_urls:
        return set()
    matched: set[str] = set()
    for fact in facts:
        fact_id = fact.get("fact_id")
        if fact.get("hotel_id") != hotel_id or fact_id not in allowed_ids:
            continue
        trusted = " ".join((
            str(fact.get("value", "")),
            json.dumps(fact.get("conditions", {}), ensure_ascii=False),
        ))
        if question_urls.intersection(url.rstrip(".,;:!?)") for url in _URL.findall(trusted)):
            matched.add(fact_id)
    return matched


def _validate_untrusted_field(text: str, facts_by_id: dict[str, dict[str, Any]]) -> None:
    """Check model-authored unknown/conflict prose before it reaches the guest."""
    references = _FACT_REFERENCE.findall(text)
    tokens = _FACT_TOKEN.findall(text)
    if tokens != references or any(fact_id not in facts_by_id for fact_id in references):
        raise ConversationFailure("invalid_model_output", "The model referenced evidence outside this hotel context.")
    cited_facts = [facts_by_id[fact_id] for fact_id in dict.fromkeys(references)]
    _validate_supported_literals(text, cited_facts)


def _model_fact_projection(fact: dict[str, Any]) -> dict[str, Any]:
    """Send only semantic evidence fields to M3; retain the full row server-side."""
    return {key: fact.get(key) for key in _MODEL_FACT_FIELDS}


def _answer_context(
    history: list[dict[str, str]], allowed_fact_ids: set[str], *, limit: int,
) -> list[dict[str, str]]:
    """Keep guest turns and only prior assistant lines grounded by current evidence."""
    projected: list[dict[str, str]] = []
    for item in history[-limit:]:
        if item.get("role") != "assistant":
            projected.append(item)
            continue
        kept_lines = []
        for line in item.get("content", "").splitlines():
            references = _FACT_REFERENCE.findall(line)
            tokens = _FACT_TOKEN.findall(line)
            if tokens != references:
                continue
            if references and not set(references) <= allowed_fact_ids:
                continue
            if line.strip():
                kept_lines.append(line)
        if kept_lines:
            projected.append({**item, "content": "\n".join(kept_lines)})
    return projected


class GroundedQAOrchestrator:
    def __init__(
        self,
        *,
        provider: AIProvider,
        retriever: KnowledgeRetriever,
        instructions: str,
        committed_instructions: str,
        response_schema: type[BaseModel],
        selection_instructions: str,
        committed_selection_instructions: str,
        selection_schema: type[BaseModel],
        claim_formatter: Callable[[str, list[dict[str, Any]]], str] | None = None,
        max_output_tokens: int = 700,
    ) -> None:
        self._provider = provider
        self._retriever = retriever
        self._instructions = instructions
        self._committed_instructions = committed_instructions
        self._response_schema = response_schema
        self._selection_instructions = selection_instructions
        self._committed_selection_instructions = committed_selection_instructions
        self._selection_schema = selection_schema
        self._claim_formatter = claim_formatter
        self._max_output_tokens = min(max(max_output_tokens, 100), 1200)

    async def answer(
        self, *, hotel_id: str, question: str, history: list[dict[str, str]],
        deadline: float | None = None,
        brief: GuestBriefSnapshot | None = None,
        extract_guest_patch: bool = False,
        selected_fact_ids: tuple[str, ...] | None = None,
        prefetched_facts: list[dict[str, Any]] | None = None,
        preferred_language_tag: str | None = None,
        missing_label_keys: tuple[str, ...] = (),
        label_bundle_keys: tuple[str, ...] = (),
    ) -> ConversationAnswer:
        provider_results: list[GenerationResult] = []
        retrieved = None
        if prefetched_facts is not None:
            relevant_facts = list(prefetched_facts)
        elif selected_fact_ids is not None:
            relevant_facts = list(await asyncio.to_thread(
                self._retriever.get_by_ids, hotel_id, set(selected_fact_ids),
                timeout_seconds=self._remaining(deadline),
            )) if selected_fact_ids else []
        else:
            retrieved = await asyncio.to_thread(
                self._retriever.retrieve, hotel_id, question, history,
                timeout_seconds=self._remaining(deadline),
            )
            relevant_facts = list(retrieved.facts)
        if retrieved is not None and retrieved.candidate_index and retrieved.term_coverage < 0.45:
            selection_input = json.dumps({
                "hotel_id": hotel_id,
                "question": question,
                "recent_context": history[-4:],
                "candidate_index": list(retrieved.candidate_index),
                "guest_brief": _brief_projection(brief),
                "guest_brief_patch_enabled": extract_guest_patch,
            }, ensure_ascii=False, separators=(",", ":"))
            try:
                selected = await self._provider.generate(GenerationRequest(
                    instructions=(
                        self._selection_instructions
                        if extract_guest_patch else self._committed_selection_instructions
                    ),
                    input_text=selection_input,
                    max_output_tokens=140,
                ))
                provider_results.append(selected)
                selection = self._selection_schema.model_validate_json(selected.text)
                allowed_ids = {item["fact_id"] for item in retrieved.candidate_index}
                selected_ids = set(selection.fact_ids)
                if len(selected_ids) != len(selection.fact_ids) or not selected_ids <= allowed_ids:
                    raise ConversationFailure("invalid_retrieval_selection", "The model selected invalid evidence.")
                selected_ids |= _question_url_fact_ids(
                    question, hotel_id, tuple(retrieved.facts), allowed_ids,
                )
                if extract_guest_patch and getattr(selection, "guest_patch", None) is not None:
                    # If called through the standard one-call API, keep going to the answer call.
                    # prepare_turn uses the selector result directly to reserve call two for post-commit.
                    selected_patch = _proposal(selection.guest_patch)
                else:
                    selected_patch = None
                if selected_ids:
                    relevant_facts = list(await asyncio.to_thread(
                        self._retriever.get_by_ids, hotel_id, selected_ids,
                        timeout_seconds=self._remaining(deadline),
                    ))
                else:
                    relevant_facts = []
            except ProviderError:
                raise
            except TimeoutError:
                raise
            except (ValidationError, ValueError) as exc:
                raise ConversationFailure("invalid_retrieval_selection", "The model returned an invalid evidence selection.") from exc
            except Exception as exc:
                raise ConversationFailure("provider_failure", "Semantic evidence selection failed.") from exc
        else:
            selected_patch = None
        conflicts = self._retriever.conflicts_for(relevant_facts)
        answer_history = _answer_context(
            history, {fact["fact_id"] for fact in relevant_facts}, limit=8,
        )
        evidence = json.dumps({
            "hotel_id": hotel_id,
            "question": question,
            "recent_context": answer_history,
            "facts": [_model_fact_projection(fact) for fact in relevant_facts],
            "conflicts": list(conflicts),
            "guest_brief": _brief_projection(brief),
            "guest_brief_patch_enabled": extract_guest_patch,
            "preferred_language_tag": preferred_language_tag,
            "missing_label_keys": list(missing_label_keys),
            "label_bundle_keys": list(label_bundle_keys),
        }, ensure_ascii=False, separators=(",", ":"))
        if len(evidence) > 18000:
            evidence = json.dumps({
                "hotel_id": hotel_id, "question": question,
                "recent_context": answer_history[-4:],
                "facts": [_model_fact_projection(fact) for fact in relevant_facts],
                "conflicts": list(conflicts),
                "guest_brief": _brief_projection(brief),
                "guest_brief_patch_enabled": extract_guest_patch,
                "preferred_language_tag": preferred_language_tag,
                "missing_label_keys": list(missing_label_keys),
                "label_bundle_keys": list(label_bundle_keys),
            }, ensure_ascii=False, separators=(",", ":"))
        if len(evidence) > 22000:
            raise ConversationFailure("context_limit", "The relevant context exceeds the request limit.")
        language_instruction = ""
        if preferred_language_tag:
            if extract_guest_patch:
                language_instruction = (
                    f"\nThe committed guest response-language preference is {preferred_language_tag!r}; "
                    "follow it unless this guest explicitly requests a different response language in this turn."
                )
            else:
                language_instruction = (
                    f"\nThe committed guest response-language preference is {preferred_language_tag!r} "
                    "and is authoritative for this answer. Do not override it based on a language request "
                    "in the current or historical question/context, and do not return a different explicit_language_tag."
                )
        try:
            generated = await self._provider.generate(GenerationRequest(
                instructions=(self._instructions if extract_guest_patch else self._committed_instructions)
                + language_instruction,
                input_text=evidence,
                max_output_tokens=self._max_output_tokens,
            ))
        except (ConversationFailure, ProviderError):
            raise
        except Exception as exc:
            raise ConversationFailure("provider_failure", "The answer provider failed.") from exc
        provider_results.append(generated)
        try:
            payload = self._response_schema.model_validate_json(generated.text)
        except (ValidationError, ValueError) as exc:
            diagnostics = _validation_diagnostics(exc) if isinstance(exc, ValidationError) else None
            raise ConversationFailure(
                "invalid_model_output", "The model returned an invalid answer.",
                validation_diagnostics=diagnostics,
            ) from exc
        facts_by_id = {fact["fact_id"]: fact for fact in relevant_facts}
        cited: list[str] = []
        rendered_claims: list[str] = []
        for claim in payload.supported_claims:
            claim_ids = list(dict.fromkeys(claim.fact_ids))
            if not claim_ids or any(fact_id not in facts_by_id for fact_id in claim_ids):
                raise ConversationFailure("invalid_model_output", "The model cited evidence outside this hotel context.")
            references = _FACT_REFERENCE.findall(claim.text)
            tokens = _FACT_TOKEN.findall(claim.text)
            if tokens != references or (references and set(references) != set(claim_ids)):
                raise ConversationFailure("invalid_model_output", "A supported claim includes invalid evidence references.")
            cited_claim_facts = [facts_by_id[item] for item in claim_ids]
            _validate_supported_literals(claim.text, cited_claim_facts)
            formatted_text = (
                self._claim_formatter(claim.text, cited_claim_facts)
                if self._claim_formatter is not None else claim.text
            )
            if not isinstance(formatted_text, str):
                raise ConversationFailure("invalid_model_output", "The claim formatter returned invalid text.")
            formatted_references = _FACT_REFERENCE.findall(formatted_text)
            formatted_tokens = _FACT_TOKEN.findall(formatted_text)
            if formatted_tokens != formatted_references or formatted_references != references:
                raise ConversationFailure("invalid_model_output", "The claim formatter changed evidence references.")
            _validate_supported_literals(formatted_text, cited_claim_facts)
            cited.extend(claim_ids)
            labels = " ".join(f"[{fact_id}]" for fact_id in claim_ids)
            rendered_claims.append(formatted_text if references else f"{formatted_text} {labels}")
        for text in (*payload.unknowns, *payload.conflicts):
            _validate_untrusted_field(text, facts_by_id)
        raw_brief_refs = getattr(payload, "guest_brief_refs", ())
        raw_guest_claims = getattr(payload, "guest_claims", ())
        if (raw_brief_refs or raw_guest_claims) and brief is None:
            raise ConversationFailure("invalid_model_output", "The model referenced a guest brief that was not supplied.")
        rejected_guest_claims = 0
        rejected_guest_claim_failure: ConversationFailure | None = None
        if brief is not None:
            guest_claims, rejected_guest_claims, rejected_guest_claim_failure = _validated_guest_claims(
                raw_guest_claims, brief,
                discard_unsupported_literals=not extract_guest_patch,
            )
        else:
            guest_claims = ()
        claim_refs = tuple(dict.fromkeys(ref for claim in guest_claims for ref in claim["refs"]))
        declared_refs = _validated_brief_refs(raw_brief_refs, brief) if brief is not None else ()
        brief_refs = tuple(dict.fromkeys((*declared_refs, *claim_refs)))
        cited = list(dict.fromkeys(cited))
        proposed_patch = getattr(payload, "guest_patch", None) if extract_guest_patch else None
        patch_has_operations = bool(getattr(proposed_patch, "ops", None))
        rendered_guest_claims = [claim["text"] for claim in guest_claims]
        has_meaningful_text = any(
            _FACT_REFERENCE.sub("", part).strip() for part in (
                *rendered_claims, *rendered_guest_claims, *payload.unknowns, *payload.conflicts,
            )
        )
        if not has_meaningful_text and not patch_has_operations:
            if rejected_guest_claim_failure is not None:
                raise rejected_guest_claim_failure
            raise ConversationFailure("invalid_model_output", "A response without supporting facts must state unknowns or conflicts.")
        cited_facts = [facts_by_id[fact_id] for fact_id in cited]
        answer_parts = [*rendered_claims, *rendered_guest_claims, *payload.unknowns, *payload.conflicts]
        answer_text = "\n".join(answer_parts)
        usage = Usage(
            input_tokens=_complete_usage_sum(provider_results, "input_tokens"),
            output_tokens=_complete_usage_sum(provider_results, "output_tokens"),
            total_tokens=_complete_usage_sum(provider_results, "total_tokens"),
        )
        raw_label_bundle = getattr(payload, "label_bundle", None)
        label_bundle = dict(raw_label_bundle) if isinstance(raw_label_bundle, dict) else {}
        return ConversationAnswer(
            answer=answer_text,
            citations=tuple(cited_facts),
            unknowns=tuple(payload.unknowns),
            provider=generated.provider,
            deployment=generated.deployment,
            model=generated.model,
            provider_request_id=generated.request_id,
            usage=usage,
            retrieval_fact_ids=tuple(facts_by_id),
            calls=len(provider_results),
            provider_request_ids=tuple(item.request_id for item in provider_results if item.request_id),
            guest_patch=_proposal(proposed_patch) if patch_has_operations else selected_patch,
            guest_claims=guest_claims,
            rejected_guest_claims=rejected_guest_claims,
            brief_version_used=brief.brief_version if brief_refs and brief is not None else None,
            brief_dependent=bool(brief_refs),
            guest_brief_refs=brief_refs,
            explicit_language_tag=_clean_language_tag(getattr(payload, "explicit_language_tag", None)),
            inferred_language_tag=_clean_language_tag(getattr(payload, "inferred_language_tag", None)),
            label_bundle=label_bundle,
        )

    async def prepare_turn(
        self, *, hotel_id: str, question: str, history: list[dict[str, str]],
        brief: GuestBriefSnapshot, deadline: float | None = None,
        source_utterance_id: str | None = None,
        preferred_language_tag: str | None = None,
        missing_label_keys: tuple[str, ...] = (),
        label_bundle_keys: tuple[str, ...] = (),
    ) -> PreparedGuestTurn:
        """Combine low-overlap selection with patch understanding in call one."""
        retrieved = await asyncio.to_thread(
            self._retriever.retrieve, hotel_id, question, history,
            timeout_seconds=self._remaining(deadline),
        )
        if retrieved.candidate_index and retrieved.term_coverage < 0.45:
            selection_input = json.dumps({
                "hotel_id": hotel_id, "question": question,
                "recent_context": history[-4:],
                "candidate_index": list(retrieved.candidate_index),
                "guest_brief": _brief_projection(brief),
                "guest_brief_patch_enabled": True,
                "preferred_language_tag": preferred_language_tag,
            }, ensure_ascii=False, separators=(",", ":"))
            try:
                selected = await self._provider.generate(GenerationRequest(
                    instructions=self._selection_instructions,
                    input_text=selection_input, max_output_tokens=self._max_output_tokens,
                ))
                payload = self._selection_schema.model_validate_json(selected.text)
                allowed_ids = {item["fact_id"] for item in retrieved.candidate_index}
                selected_ids = tuple(dict.fromkeys(payload.fact_ids))
                if len(selected_ids) != len(payload.fact_ids) or not set(selected_ids) <= allowed_ids:
                    raise ConversationFailure("invalid_retrieval_selection", "The model selected invalid evidence.")
                selected_ids = tuple(dict.fromkeys((
                    *selected_ids,
                    *_question_url_fact_ids(question, hotel_id, tuple(retrieved.facts), allowed_ids),
                )))
                patch = _proposal(getattr(payload, "guest_patch", None))
                return PreparedGuestTurn(
                    provisional_answer=None, guest_patch=patch,
                    selected_fact_ids=selected_ids, source_utterance_id=source_utterance_id,
                    preparation_calls=1,
                    retrieval_fact_ids=tuple(item["fact_id"] for item in retrieved.facts),
                    provider=selected.provider, deployment=selected.deployment,
                    model=selected.model,
                    provider_request_ids=(selected.request_id,) if selected.request_id else (),
                    input_tokens=selected.usage.input_tokens,
                    output_tokens=selected.usage.output_tokens,
                    total_tokens=selected.usage.total_tokens,
                    explicit_language_tag=_clean_language_tag(payload.explicit_language_tag),
                    inferred_language_tag=_clean_language_tag(payload.inferred_language_tag),
                )
            except (ProviderError, TimeoutError, ConversationFailure):
                raise
            except Exception as exc:
                raise ConversationFailure("invalid_retrieval_selection", "The model returned invalid preparation data.") from exc
        answer = await self.answer(
            hotel_id=hotel_id, question=question, history=history, deadline=deadline,
            brief=brief, extract_guest_patch=True, prefetched_facts=list(retrieved.facts),
            preferred_language_tag=preferred_language_tag,
            missing_label_keys=missing_label_keys,
            label_bundle_keys=label_bundle_keys,
        )
        return PreparedGuestTurn(
            provisional_answer=answer, guest_patch=answer.guest_patch,
            selected_fact_ids=answer.retrieval_fact_ids, source_utterance_id=source_utterance_id,
            preparation_calls=answer.calls,
            retrieval_fact_ids=answer.retrieval_fact_ids,
            provider=answer.provider, deployment=answer.deployment, model=answer.model,
            provider_request_ids=answer.provider_request_ids,
            input_tokens=answer.usage.input_tokens, output_tokens=answer.usage.output_tokens,
            total_tokens=answer.usage.total_tokens,
            explicit_language_tag=answer.explicit_language_tag,
            inferred_language_tag=answer.inferred_language_tag,
        )

    async def answer_committed_turn(
        self, *, hotel_id: str, question: str, history: list[dict[str, str]],
        brief: GuestBriefSnapshot, deadline: float | None = None,
        selected_fact_ids: tuple[str, ...] | None = None,
        preferred_language_tag: str | None = None,
        missing_label_keys: tuple[str, ...] = (),
        label_bundle_keys: tuple[str, ...] = (),
    ) -> ConversationAnswer:
        """Generate the final grounded answer from committed brief state, without patch use."""
        return await self.answer(
            hotel_id=hotel_id, question=question, history=history, deadline=deadline,
            brief=brief, extract_guest_patch=False, selected_fact_ids=selected_fact_ids,
            preferred_language_tag=preferred_language_tag,
            missing_label_keys=missing_label_keys,
            label_bundle_keys=label_bundle_keys,
        )

    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("The AI turn deadline expired.")
        return remaining


def _brief_projection(brief: GuestBriefSnapshot | None) -> dict[str, Any] | None:
    if brief is None:
        return None
    return {"brief_version": brief.brief_version, "data": brief.data,
            "pending_fields": list(brief.pending_fields)}


def _proposal(value: Any) -> GuestBriefProposal | None:
    if value is None:
        return None
    operations = getattr(value, "ops", None)
    if operations is None:
        return None
    return GuestBriefProposal(tuple(item.model_dump(mode="json") for item in operations))


def _validated_brief_refs(
    refs: Any, brief: GuestBriefSnapshot | None,
) -> tuple[str, ...]:
    if not refs:
        return ()
    if brief is None or not isinstance(refs, list) or len(refs) != len(set(refs)):
        raise ConversationFailure("invalid_model_output", "The model returned invalid guest brief references.")
    allowed = {
        "dates.check_in": brief.data.get("dates", {}).get("check_in"),
        "dates.check_out": brief.data.get("dates", {}).get("check_out"),
        "dates.nights": brief.data.get("dates", {}).get("nights"),
        "party.adults": brief.data.get("party", {}).get("adults"),
        "party.children.count": len(brief.data.get("party", {}).get("children", [])),
    }
    for child in brief.data.get("party", {}).get("children", []):
        member_id = child.get("member_id")
        allowed[f"party.children.{member_id}.age"] = child.get("age")
    if any(ref not in allowed or allowed[ref] is None for ref in refs):
        raise ConversationFailure("invalid_model_output", "The model referenced a missing guest brief field.")
    return tuple(refs)


def _validated_guest_claims(
    claims: Any, brief: GuestBriefSnapshot | None, *, discard_unsupported_literals: bool = False,
) -> tuple[tuple[dict[str, Any], ...], int, ConversationFailure | None]:
    if not claims:
        return (), 0, None
    if brief is None:
        raise ConversationFailure("invalid_model_output", "Guest claims require a supplied canonical brief.")
    validated: list[dict[str, Any]] = []
    rejected = 0
    first_rejection: ConversationFailure | None = None
    for claim in claims:
        refs = _validated_brief_refs(claim.refs, brief)
        values = [_brief_ref_value(ref, brief) for ref in refs]
        try:
            _validate_supported_literals(claim.text, [{"value": value} for value in values])
        except ConversationFailure as exc:
            if not discard_unsupported_literals or exc.reason != "unsupported_number":
                raise
            rejected += 1
            first_rejection = first_rejection or exc
            continue
        validated.append({"text": claim.text, "refs": list(refs)})
    return tuple(validated), rejected, first_rejection


def _brief_ref_value(ref: str, brief: GuestBriefSnapshot) -> Any:
    allowed = {
        "dates.check_in": brief.data.get("dates", {}).get("check_in"),
        "dates.check_out": brief.data.get("dates", {}).get("check_out"),
        "dates.nights": brief.data.get("dates", {}).get("nights"),
        "party.adults": brief.data.get("party", {}).get("adults"),
        "party.children.count": len(brief.data.get("party", {}).get("children", [])),
    }
    for child in brief.data.get("party", {}).get("children", []):
        allowed[f"party.children.{child.get('member_id')}.age"] = child.get("age")
    if ref not in allowed or allowed[ref] is None:
        raise ConversationFailure("invalid_model_output", "The model referenced a missing guest brief field.")
    return allowed[ref]
