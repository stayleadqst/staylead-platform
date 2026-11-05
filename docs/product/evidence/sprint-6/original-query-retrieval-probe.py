"""Read-only original-query lexical baseline against the imported S6 PG corpus.

Run after the synthetic overlay has been explicitly imported and before live
acceptance. This uses the real Postgres fact repository and production lexical
retriever with bounded prior guest-turn context. It does not start the API or
invoke an LLM. The SQL wrapper marks every retrieval transaction read-only.

    PYTHONPATH=apps/api/src apps/api/.venv/bin/python \
      docs/product/evidence/sprint-6/original-query-retrieval-probe.py \
      > docs/product/evidence/sprint-6/codex-retrieval-baseline.json
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
MATRIX = ROOT / "docs/product/evidence/sprint-6/live-cases.json"
RUNTIME = Path("/private/tmp/staylead-sprint6-runtime.json")
EXPECTED_FACTS = {
    1: ["F-HTL-CITY01-040"],
    4: ["F-HTL-CITY01-040"],
    5: ["F-HTL-CITY01-021"],
    6: ["F-HTL-CITY01-046", "F-HTL-CITY01-S6-URL-001"],
}


class _ReadOnlyEngine:
    """Tiny adapter so every repository transaction is PostgreSQL READ ONLY."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    @contextmanager
    def begin(self) -> Iterator[Any]:
        with self._engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            yield connection


def main() -> None:
    try:
        config = json.loads(RUNTIME.read_text(encoding="utf-8"))
        database_url = config["database_url"]
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit("Private runtime config or pinned matrix is missing/invalid.") from exc

    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError
    from staylead_platform.infrastructure.persistence.knowledge_repository import (
        PostgresKnowledgeFactRepository,
    )
    from staylead_platform.platform.knowledge.retrieval.retriever import (
        KnowledgeRetriever,
    )

    raw_engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
    engine = _ReadOnlyEngine(raw_engine)
    retriever = KnowledgeRetriever(PostgresKnowledgeFactRepository(engine), max_facts=20)
    previous: list[dict[str, str]] = []
    turns = []
    try:
        for case in matrix["turns"]:
            result = retriever.retrieve(
                matrix["hotel_id"], case["utterance"], previous[-4:], timeout_seconds=5.0,
            )
            selected_ids = [fact["fact_id"] for fact in result.facts]
            expected = EXPECTED_FACTS.get(case["turn"], [])
            present = [fact_id for fact_id in expected if fact_id in selected_ids]
            turns.append({
                "turn": case["turn"],
                "expected_fact_ids": expected,
                "candidate_fact_ids": selected_ids,
                "expected_fact_coverage": len(present) / len(expected) if expected else None,
                "missing_expected_fact_ids": [fact_id for fact_id in expected if fact_id not in selected_ids],
                "query_term_count": result.query_terms,
                "term_coverage": round(result.term_coverage, 6),
                "candidate_index": list(result.candidate_index),
                "conflicts": list(result.conflicts),
            })
            previous.append({"role": "user", "content": case["utterance"]})
        print(json.dumps({
            "result": "completed",
            "probe": "original_query_lexical_retrieval_baseline",
            "database_transaction_mode": "read_only",
            "llm_calls": 0,
            "provider_calls": 0,
            "hotel_id": matrix["hotel_id"],
            "history_policy": "last 4 preceding pinned guest utterances; bounded context only",
            "guest_utterances_included_in_output": False,
            "turns": turns,
        }, ensure_ascii=False, indent=2))
    except SQLAlchemyError as exc:
        raise SystemExit(f"Read-only retrieval probe failed ({type(exc).__name__}).") from None
    finally:
        raw_engine.dispose()


if __name__ == "__main__":
    main()
