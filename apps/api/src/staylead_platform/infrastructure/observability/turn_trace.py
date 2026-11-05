"""Bounded, allowlisted observability for one guest request."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

_STAGES = {"admission", "retrieval", "capability", "provider", "response"}
_STATUSES = {"started", "ok", "error", "cancelled", "denied"}
_SAFE_CODE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
_SAFE_METADATA = {
    "request_id", "session_id", "hotel_id", "provider", "deployment", "model",
    "provider_request_id", "calls", "input_tokens", "output_tokens", "total_tokens",
    "config_version", "prompt_version", "answer_schema_version", "source_generation", "brief_version",
    "cost_status", "limits_version", "context_chars", "turn_timeout_ms", "provider_timeout_ms",
    "max_output_tokens",
}
_MAX_EVENTS = 20


def _safe_metadata(values: dict[str, Any]) -> dict[str, Any]:
    """Copy only small, typed identifiers/counters; never accept arbitrary log payloads."""
    result: dict[str, Any] = {}
    for key, value in values.items():
        if key not in _SAFE_METADATA:
            continue
        if value is None or isinstance(value, bool):
            result[key] = value
        elif isinstance(value, int):
            result[key] = max(0, value)
        elif isinstance(value, str):
            cleaned = value.strip()
            if cleaned and len(cleaned) <= 128 and not any(ord(char) < 32 for char in cleaned):
                result[key] = cleaned
    return result


@dataclass
class TurnTrace:
    """In-memory trace whose serialized shape excludes prompts, messages and exceptions."""

    started_at: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    outcome: str | None = None
    failure_stage: str | None = None
    failure_code: str | None = None
    elapsed_ms: int | None = None
    _closed: bool = False

    @property
    def closed(self) -> bool:
        return self._closed

    def set_metadata(self, **values: Any) -> None:
        if not self._closed:
            self.metadata.update(_safe_metadata(values))

    def record(
        self, stage: str, status: str, *, duration_ms: int | None = None,
        code: str | None = None, **metadata: Any,
    ) -> None:
        if self._closed or stage not in _STAGES or status not in _STATUSES:
            return
        if len(self.events) >= _MAX_EVENTS:
            return
        event: dict[str, Any] = {"stage": stage, "status": status}
        if duration_ms is not None:
            event["duration_ms"] = max(0, int(duration_ms))
        if code is not None and _SAFE_CODE.fullmatch(code):
            event["code"] = code
        event.update(_safe_metadata(metadata))
        self.events.append(event)

    def close(self, *, outcome: str, failure_stage: str | None = None, failure_code: str | None = None) -> dict[str, Any]:
        normalized_outcome = outcome if outcome in {"ok", "error", "cancelled"} else "error"
        if not self._closed or (self.outcome == "ok" and normalized_outcome != "ok"):
            self._closed = True
            self.outcome = normalized_outcome
            self.failure_stage = (
                failure_stage if failure_stage in _STAGES
                else "response" if normalized_outcome in {"error", "cancelled"} else None
            )
            self.failure_code = failure_code if failure_code and _SAFE_CODE.fullmatch(failure_code) else None
            if self.elapsed_ms is None:
                self.elapsed_ms = max(0, int((time.monotonic() - self.started_at) * 1000))
        return self.as_dict()

    def snapshot(
        self, *, outcome: str, failure_stage: str | None = None, failure_code: str | None = None,
    ) -> dict[str, Any]:
        """Build a terminal persistence snapshot without closing the live trace."""
        result = self.as_dict()
        result["outcome"] = outcome if outcome in {"ok", "error", "cancelled"} else "error"
        result["elapsed_ms"] = max(0, int((time.monotonic() - self.started_at) * 1000))
        result["failure_stage"] = failure_stage if failure_stage in _STAGES else None
        result["failure_code"] = (
            failure_code if failure_code and _SAFE_CODE.fullmatch(failure_code) else None
        )
        return result

    def as_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-safe snapshot suitable for response persistence/replay."""
        return {
            "schema_version": 1,
            **dict(self.metadata),
            "outcome": self.outcome or "in_progress",
            "elapsed_ms": self.elapsed_ms,
            "failure_stage": self.failure_stage,
            "failure_code": self.failure_code,
            "events": [dict(event) for event in self.events],
        }
