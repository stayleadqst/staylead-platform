"""Hotel-scoped multilingual lexical retrieval over imported atomic facts."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from staylead_platform.platform.contracts.knowledge import KnowledgeFact, KnowledgeFactRepository

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _terms(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(text) if len(token) > 1]


def _fact_text(fact: dict[str, Any]) -> str:
    return " ".join((
        str(fact.get("topic", "")), str(fact.get("subject", "")), str(fact.get("field", "")),
        json.dumps(fact.get("value"), ensure_ascii=False),
        json.dumps(fact.get("conditions", {}), ensure_ascii=False),
    ))


@dataclass(frozen=True)
class RetrievalResult:
    hotel_id: str
    facts: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]
    query_terms: int
    term_coverage: float
    candidate_index: tuple[dict[str, str], ...]


class KnowledgeRetriever:
    def __init__(self, repository: KnowledgeFactRepository, *, max_facts: int = 20) -> None:
        self._repository = repository
        self._max_facts = max_facts

    @staticmethod
    def _wire(fact: KnowledgeFact) -> dict[str, Any]:
        return {
            "fact_id": fact.fact_id, "hotel_id": fact.hotel_id, "topic": fact.topic,
            "subject": fact.subject, "field": fact.field, "value": fact.value,
            "conditions": fact.conditions, "status": fact.status,
            "valid_from": fact.valid_from, "valid_to": fact.valid_to,
            "provenance": fact.provenance,
        }

    def retrieve(
        self, hotel_id: str, question: str, context: list[dict[str, str]],
        *, timeout_seconds: float | None = None,
    ) -> RetrievalResult:
        # Include recent turns for pronouns and references; never search another session's context.
        query = " ".join([question, *(item["content"][:800] for item in context[-4:])])[:4000]
        query_terms = Counter(_terms(query))
        all_facts = [self._wire(fact) for fact in self._repository.list_guest_facts(
            hotel_id, timeout_seconds=timeout_seconds,
        )]
        if not query_terms or not all_facts:
            return RetrievalResult(hotel_id, (), (), len(query_terms), 0.0, ())
        documents = [_terms(_fact_text(fact)) for fact in all_facts]
        document_frequency: Counter[str] = Counter()
        for document in documents:
            document_frequency.update(set(document))
        count = len(documents)
        average_length = sum(map(len, documents)) / max(count, 1)
        scored: list[tuple[float, int, dict[str, Any]]] = []
        matched_terms: set[str] = set()
        for index, (fact, terms) in enumerate(zip(all_facts, documents, strict=True)):
            term_frequency = Counter(terms)
            score = 0.0
            for term, query_frequency in query_terms.items():
                frequency = term_frequency[term]
                if not frequency:
                    continue
                matched_terms.add(term)
                inverse = math.log(1 + (count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                length_norm = frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(terms) / max(average_length, 1)))
                score += inverse * length_norm * min(query_frequency, 2)
            if score:
                scored.append((score, index, fact))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [item[2] for item in scored[: self._max_facts]]
        conflicts: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for fact in selected:
            key = (str(fact.get("subject")), str(fact.get("topic")), str(fact.get("field")))
            grouped[key].append(fact)
            conflicts[key].add(json.dumps(fact.get("value"), ensure_ascii=False, sort_keys=True))
        explicit_conflicts = tuple({
            "subject": key[0], "topic": key[1], "field": key[2],
            "fact_ids": [item["fact_id"] for item in grouped[key]],
        } for key, values in conflicts.items() if len(values) > 1)
        return RetrievalResult(
            hotel_id, tuple(selected), explicit_conflicts, len(query_terms),
            len(matched_terms) / len(query_terms),
            tuple({"fact_id": fact["fact_id"], "subject": fact["subject"],
                   "topic": fact["topic"], "field": fact["field"]} for fact in all_facts),
        )

    def get_by_ids(
        self, hotel_id: str, fact_ids: set[str], *, timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], ...]:
        facts = self._repository.get_guest_facts(hotel_id, fact_ids, timeout_seconds=timeout_seconds)
        return tuple(self._wire(fact) for fact in facts)
