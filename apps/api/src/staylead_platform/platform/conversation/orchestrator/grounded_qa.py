"""Bounded M3 knowledge Q&A with conditional semantic fact selection."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from staylead_platform.platform.contracts.ai_provider import (
    AIProvider,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)
from staylead_platform.platform.knowledge.retrieval.retriever import KnowledgeRetriever

_NUMBER = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")
_URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
_FACT_REFERENCE = re.compile(r"\[(F-[A-Za-z0-9-]+)\]")
_FACT_TOKEN = re.compile(r"(?<![A-Za-z0-9])F-[A-Za-z0-9-]+")
_MODEL_FACT_FIELDS = ("fact_id", "topic", "subject", "field", "value", "conditions", "status")


class ConversationFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


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


def _numeric_forms(text: str) -> set[str]:
    return {re.sub(r"\D", "", item) for item in _NUMBER.findall(text) if re.search(r"\d", item)}


def _validate_supported_literals(answer: str, cited_facts: list[dict[str, Any]]) -> None:
    trusted = json.dumps([
        {"value": fact.get("value"), "conditions": fact.get("conditions", {})}
        for fact in cited_facts
    ], ensure_ascii=False)
    without_citations = re.sub(r"\[F-[A-Za-z0-9-]+\]", "", answer)
    if _numeric_forms(without_citations) - _numeric_forms(trusted):
        raise ConversationFailure("unsupported_output", "The model returned an unsupported number.")
    evidence_urls = {url.rstrip(".,;:!?)") for url in _URL.findall(trusted)}
    if any(url.rstrip(".,;:!?)") not in evidence_urls for url in _URL.findall(answer)):
        raise ConversationFailure("unsupported_output", "The model returned an unsupported URL.")


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


class GroundedQAOrchestrator:
    def __init__(
        self,
        *,
        provider: AIProvider,
        retriever: KnowledgeRetriever,
        instructions: str,
        response_schema: type[BaseModel],
        selection_instructions: str,
        selection_schema: type[BaseModel],
        max_output_tokens: int = 700,
    ) -> None:
        self._provider = provider
        self._retriever = retriever
        self._instructions = instructions
        self._response_schema = response_schema
        self._selection_instructions = selection_instructions
        self._selection_schema = selection_schema
        self._max_output_tokens = min(max(max_output_tokens, 100), 1200)

    async def answer(
        self, *, hotel_id: str, question: str, history: list[dict[str, str]],
        deadline: float | None = None,
    ) -> ConversationAnswer:
        retrieved = await asyncio.to_thread(
            self._retriever.retrieve, hotel_id, question, history,
            timeout_seconds=self._remaining(deadline),
        )
        provider_results: list[GenerationResult] = []
        relevant_facts = list(retrieved.facts)
        if retrieved.candidate_index and retrieved.term_coverage < 0.45:
            selection_input = json.dumps({
                "hotel_id": hotel_id,
                "question": question,
                "recent_context": history[-4:],
                "candidate_index": list(retrieved.candidate_index),
            }, ensure_ascii=False, separators=(",", ":"))
            try:
                selected = await self._provider.generate(GenerationRequest(
                    instructions=self._selection_instructions,
                    input_text=selection_input,
                    max_output_tokens=140,
                ))
                provider_results.append(selected)
                selection = self._selection_schema.model_validate_json(selected.text)
                allowed_ids = {item["fact_id"] for item in retrieved.candidate_index}
                selected_ids = set(selection.fact_ids)
                if len(selected_ids) != len(selection.fact_ids) or not selected_ids <= allowed_ids:
                    raise ConversationFailure("invalid_retrieval_selection", "The model selected invalid evidence.")
                if selected_ids:
                    relevant_facts = list(await asyncio.to_thread(
                        self._retriever.get_by_ids, hotel_id, selected_ids,
                        timeout_seconds=self._remaining(deadline),
                    ))
            except ProviderError:
                raise
            except TimeoutError:
                raise
            except (ValidationError, ValueError) as exc:
                raise ConversationFailure("invalid_retrieval_selection", "The model returned an invalid evidence selection.") from exc
            except Exception as exc:
                raise ConversationFailure("provider_failure", "Semantic evidence selection failed.") from exc
        evidence = json.dumps({
            "hotel_id": hotel_id,
            "question": question,
            "recent_context": history[-8:],
            "facts": [_model_fact_projection(fact) for fact in relevant_facts],
            "conflicts": list(retrieved.conflicts),
        }, ensure_ascii=False, separators=(",", ":"))
        if len(evidence) > 18000:
            evidence = json.dumps({
                "hotel_id": hotel_id, "question": question,
                "recent_context": history[-4:],
                "facts": [_model_fact_projection(fact) for fact in relevant_facts],
                "conflicts": list(retrieved.conflicts),
            }, ensure_ascii=False, separators=(",", ":"))
        if len(evidence) > 22000:
            raise ConversationFailure("context_limit", "The relevant context exceeds the request limit.")
        try:
            generated = await self._provider.generate(GenerationRequest(
                instructions=self._instructions,
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
            raise ConversationFailure("invalid_model_output", "The model returned an invalid answer.") from exc
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
            _validate_supported_literals(claim.text, [facts_by_id[item] for item in claim_ids])
            cited.extend(claim_ids)
            labels = " ".join(f"[{fact_id}]" for fact_id in claim_ids)
            rendered_claims.append(claim.text if references else f"{claim.text} {labels}")
        for text in (*payload.unknowns, *payload.conflicts):
            _validate_untrusted_field(text, facts_by_id)
        cited = list(dict.fromkeys(cited))
        if not rendered_claims and not payload.unknowns and not payload.conflicts:
            raise ConversationFailure("invalid_model_output", "A response without supporting facts must state unknowns or conflicts.")
        cited_facts = [facts_by_id[fact_id] for fact_id in cited]
        answer_parts = [*rendered_claims, *payload.unknowns, *payload.conflicts]
        answer_text = "\n".join(answer_parts)
        usage = Usage(
            input_tokens=sum(item.usage.input_tokens or 0 for item in provider_results) or None,
            output_tokens=sum(item.usage.output_tokens or 0 for item in provider_results) or None,
            total_tokens=sum(item.usage.total_tokens or 0 for item in provider_results) or None,
        )
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
        )

    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("The AI turn deadline expired.")
        return remaining
