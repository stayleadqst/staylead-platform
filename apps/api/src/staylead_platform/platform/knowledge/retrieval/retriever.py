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


def _conflicts(facts: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        key = (str(fact.get("subject")), str(fact.get("topic")), str(fact.get("field")))
        grouped[key].append(fact)
    return tuple({
        "subject": key[0], "topic": key[1], "field": key[2],
        "fact_ids": [item["fact_id"] for item in group],
    } for key, group in grouped.items()
        if len({json.dumps(item.get("value"), ensure_ascii=False, sort_keys=True) for item in group}) > 1)


def _include_conflict_versions(
    all_facts: list[dict[str, Any]], selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    keys = {(fact["subject"], fact["topic"], fact["field"]) for fact in selected}
    values: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for fact in all_facts:
        key = (fact["subject"], fact["topic"], fact["field"])
        if key in keys:
            values[key].add(json.dumps(fact.get("value"), ensure_ascii=False, sort_keys=True))
    conflict_keys = {key for key, group_values in values.items() if len(group_values) > 1}
    included = {fact["fact_id"] for fact in selected}
    return [*selected, *(
        fact for fact in all_facts
        if (fact["subject"], fact["topic"], fact["field"]) in conflict_keys
        and fact["fact_id"] not in included
    )]


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
    def conflicts_for(facts: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        return _conflicts(facts)

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
        # The current turn drives ranking; recent turns contribute lightly for references.
        question_terms = Counter(_terms(question[:2400]))
        context_terms = Counter(_terms(" ".join(item["content"][:800] for item in context[-4:])))
        query_terms = question_terms + Counter({term: count * 0.2 for term, count in context_terms.items()})
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
        for index, (fact, terms) in enumerate(zip(all_facts, documents, strict=True)):
            term_frequency = Counter(terms)
            score = 0.0
            for term, query_frequency in query_terms.items():
                frequency = term_frequency[term]
                if not frequency:
                    continue
                inverse = math.log(1 + (count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                length_norm = frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(terms) / max(average_length, 1)))
                score += inverse * length_norm * min(query_frequency, 2)
            if score:
                scored.append((score, index, fact))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [item[2] for item in scored[: self._max_facts]]
        selected = _include_conflict_versions(all_facts, selected)
        # Coverage reflects whether any one fact directly matches each question clause.
        # Corpus-wide token union falsely looks complete when unrelated facts share generic words.
        idf = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        unknown_idf = math.log(1 + (count + 0.5) / 0.5)
        clauses = [Counter(_terms(part)) for part in re.split(r"[?!.;。？！；]+", question[:2400])]
        clauses = [clause for clause in clauses if clause]
        clause_coverages = []
        for clause in clauses:
            denominator = sum(idf.get(term, unknown_idf) * frequency for term, frequency in clause.items())
            if denominator == 0:
                continue
            best = max((
                sum(idf.get(term, unknown_idf) * min(frequency, doc_counter[term])
                    for term, frequency in clause.items()) / denominator
                for doc_counter in (Counter(doc) for doc in documents)
            ), default=0.0)
            clause_coverages.append(best)
        term_coverage = min(clause_coverages, default=0.0)
        return RetrievalResult(
            hotel_id, tuple(selected), _conflicts(selected), len(question_terms),
            term_coverage,
            tuple({"fact_id": fact["fact_id"], "subject": fact["subject"],
                   "topic": fact["topic"], "field": fact["field"]} for fact in all_facts),
        )

    def get_by_ids(
        self, hotel_id: str, fact_ids: set[str], *, timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], ...]:
        all_facts = [self._wire(fact) for fact in self._repository.list_guest_facts(
            hotel_id, timeout_seconds=timeout_seconds,
        )]
        selected = [fact for fact in all_facts if fact["fact_id"] in fact_ids]
        # list_guest_facts is bounded by the repository limit; final prompt size is checked
        # by the orchestrator, so conflict versions are never silently truncated here.
        return tuple(_include_conflict_versions(all_facts, selected))

    def list_current_facts(
        self, hotel_id: str, *, limit: int = 400, timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Return the bounded, repository-filtered current guest fact projection."""
        facts = self._repository.list_guest_facts(
            hotel_id, limit=min(max(limit, 1), 400), timeout_seconds=timeout_seconds,
        )
        return tuple(self._wire(fact) for fact in facts)
