"""Read-only PostgreSQL snapshot for the Codex Sprint 5 acceptance session.

From the repository root, after the browser run is complete::

    PYTHONPATH=apps/api/src apps/api/.venv/bin/python \
      docs/product/evidence/sprint-5/codex_db_observation.py \
      2ae411dd-30ae-4eec-a37a-3c8effd8141d

The command prints sanitized JSON to stdout. To preserve the final snapshot, the
coordinator may redirect stdout to ``codex-db-observation.json``. It reads the
existing private runtime config only in memory, opens a PostgreSQL read-only
transaction, and excludes source utterance text, response payloads, and secrets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RUNTIME = Path("/tmp/staylead-sprint5-runtime.json")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def snapshot(session_id: str) -> dict[str, Any]:
    try:
        runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
        database_url = runtime["database_url"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit("Private local runtime config is unavailable or invalid.") from exc

    from sqlalchemy import create_engine, select
    from sqlalchemy.exc import SQLAlchemyError
    from staylead_platform.infrastructure.persistence.store import (
        guest_brief_receipts,
        guest_briefs,
        sessions,
    )

    engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
    try:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            session = connection.execute(select(
                sessions.c.session_id,
                sessions.c.hotel_id,
                sessions.c.state_version,
                sessions.c.created_at,
            ).where(sessions.c.session_id == session_id)).mappings().first()
            if session is None:
                raise SystemExit("Requested session was not found in the database.")

            brief = connection.execute(select(
                guest_briefs.c.brief_version,
                guest_briefs.c.data,
                guest_briefs.c.pending_fields,
                guest_briefs.c.updated_at,
            ).where(
                guest_briefs.c.session_id == session_id,
                guest_briefs.c.hotel_id == session["hotel_id"],
            )).mappings().first()

            receipts = connection.execute(select(
                guest_brief_receipts.c.request_id,
                guest_brief_receipts.c.status,
                guest_brief_receipts.c.brief_version_before,
                guest_brief_receipts.c.brief_version_after,
                guest_brief_receipts.c.applied_delta,
                guest_brief_receipts.c.source_utterance_id,
                guest_brief_receipts.c.source_fields,
                guest_brief_receipts.c.answer_status,
                guest_brief_receipts.c.brief_version_used,
                guest_brief_receipts.c.brief_dependent,
                guest_brief_receipts.c.created_at,
            ).where(
                guest_brief_receipts.c.session_id == session_id,
                guest_brief_receipts.c.hotel_id == session["hotel_id"],
            ).order_by(guest_brief_receipts.c.created_at, guest_brief_receipts.c.request_id)
            ).mappings().all()

            return {
                "observation": "read_only_postgresql_snapshot",
                "session": {
                    "session_id": session["session_id"],
                    "hotel_id": session["hotel_id"],
                    "state_version": session["state_version"],
                    "created_at": _iso(session["created_at"]),
                },
                "guest_brief": None if brief is None else {
                    "brief_version": brief["brief_version"],
                    "data": brief["data"],
                    "pending_fields": brief["pending_fields"],
                    "updated_at": _iso(brief["updated_at"]),
                },
                "receipt_count": len(receipts),
                "receipts": [{
                    "request_id": row["request_id"],
                    "status": row["status"],
                    "brief_version_before": row["brief_version_before"],
                    "brief_version_after": row["brief_version_after"],
                    "applied_delta": row["applied_delta"],
                    "source_utterance_id": row["source_utterance_id"],
                    "source_fields": row["source_fields"],
                    "answer_status": row["answer_status"],
                    "brief_version_used": row["brief_version_used"],
                    "brief_dependent": row["brief_dependent"],
                    "created_at": _iso(row["created_at"]),
                } for row in receipts],
                "source_utterance_text_included": False,
                "answer_payload_included": False,
            }
    except SQLAlchemyError as exc:
        # Database exceptions can contain connection details. Keep them out of output.
        raise SystemExit(f"Read-only database snapshot failed ({type(exc).__name__}).") from None
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", help="Guest session ID from the acceptance run")
    args = parser.parse_args()
    result = snapshot(args.session_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
