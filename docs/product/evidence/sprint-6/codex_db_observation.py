"""Read-only, secret-safe PostgreSQL observation for Sprint 6 acceptance.

Run from the repository root after the browser matrix has created a session::

    PYTHONPATH=apps/api/src apps/api/.venv/bin/python \
      docs/product/evidence/sprint-6/codex_db_observation.py SESSION_ID

The private runtime config is read in memory. The query uses a read-only
transaction, reports language preference and receipt/version metadata, and
does not include request/answer bodies, bearer/session tokens, raw source
utterances, applied deltas, or arbitrary guest profile fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

RUNTIME = Path("/private/tmp/staylead-sprint6-runtime.json")
def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _safe_id(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", value):
        return value
    return None


def _brief_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"data_shape": type(data).__name__}
    result: dict[str, Any] = {}
    dates = data.get("dates")
    if isinstance(dates, dict):
        result["dates"] = {
            key: dates.get(key) for key in ("check_in", "check_out", "nights") if key in dates
        }
    party = data.get("party")
    if isinstance(party, dict):
        children = party.get("children")
        result["party"] = {"adults": party.get("adults")}
        if isinstance(children, list):
            result["party"]["children"] = [
                {
                    "child_id_sha256": hashlib.sha256(str(child.get("child_id", child.get("id", ""))).encode()).hexdigest()[:16]
                    if isinstance(child, dict) else None,
                    "age": child.get("age") if isinstance(child, dict) and isinstance(child.get("age"), int) else None,
                }
                for child in children
            ]
    # Legacy or alternate flat keys are whitelisted to keep the snapshot useful
    # if an older database predates the structured dates/party representation.
    for key in ("check_in", "check_out", "check_in_date", "check_out_date", "arrival_date", "departure_date", "adults", "adult_count"):
        value = data.get(key)
        if key in data and (isinstance(value, (str, int, float, bool)) or value is None):
            result[key] = value
    return result


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
        guest_language_preferences,
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

            preference = connection.execute(select(
                guest_language_preferences.c.language_tag,
                guest_language_preferences.c.source,
                guest_language_preferences.c.revision,
                guest_language_preferences.c.updated_at,
            ).where(
                guest_language_preferences.c.session_id == session_id,
                guest_language_preferences.c.hotel_id == session["hotel_id"],
            )).mappings().first()

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
                guest_brief_receipts.c.answer_status,
                guest_brief_receipts.c.brief_version_used,
                guest_brief_receipts.c.brief_dependent,
                guest_brief_receipts.c.created_at,
            ).where(
                guest_brief_receipts.c.session_id == session_id,
                guest_brief_receipts.c.hotel_id == session["hotel_id"],
            ).order_by(guest_brief_receipts.c.created_at, guest_brief_receipts.c.request_id)
            ).mappings().all()

            pending = []
            if brief is not None and isinstance(brief["pending_fields"], (list, tuple)):
                pending = [str(item) for item in brief["pending_fields"] if isinstance(item, (str, int))]
            elif brief is not None and isinstance(brief["pending_fields"], dict):
                pending = sorted(str(item) for item in brief["pending_fields"])

            return {
                "observation": "read_only_postgresql_snapshot",
                "session": {
                    "session_id": session["session_id"],
                    "hotel_id": session["hotel_id"],
                    "state_version": session["state_version"],
                    "created_at": _iso(session["created_at"]),
                },
                "language_preference": {
                    "language_tag": preference["language_tag"] if preference else "und",
                    "source": preference["source"] if preference else "fallback",
                    "revision": preference["revision"] if preference else 0,
                    "updated_at": _iso(preference["updated_at"]) if preference else None,
                },
                "guest_brief": None if brief is None else {
                    "brief_version": brief["brief_version"],
                    "state_summary": _brief_summary(brief["data"]),
                    "pending_field_names": pending,
                    "updated_at": _iso(brief["updated_at"]),
                },
                "receipt_count": len(receipts),
                "receipts": [{
                    "request_id": _safe_id(row["request_id"]),
                    "status": row["status"],
                    "brief_version_before": row["brief_version_before"],
                    "brief_version_after": row["brief_version_after"],
                    "answer_status": row["answer_status"],
                    "brief_version_used": row["brief_version_used"],
                    "brief_dependent": row["brief_dependent"],
                    "created_at": _iso(row["created_at"]),
                } for row in receipts],
                "source_utterance_text_included": False,
                "answer_payload_included": False,
                "applied_deltas_included": False,
                "secrets_included": False,
            }
    except SQLAlchemyError as exc:
        # Database exceptions may include connection parameters; never echo them.
        raise SystemExit(f"Read-only database snapshot failed ({type(exc).__name__}).") from None
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", help="Guest session ID from the acceptance run")
    args = parser.parse_args()
    print(json.dumps(snapshot(args.session_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
