"""Small, bounded translated UI label cache with whole-bundle validation."""

from __future__ import annotations

import re
import unicodedata
from threading import Lock

LABEL_KEYS = (
    "send", "sending", "copy", "copied", "copy_failed", "retry_answer", "check_status",
    "brief", "stay", "nights", "adults", "children", "age", "unknown", "pending_age",
    "updated", "partial_success", "stale_answer", "ai_notice", "synthetic_notice",
)
ENGLISH_LABELS = {
    "send": "Send", "sending": "Sending…", "copy": "Copy", "copied": "Copied",
    "copy_failed": "Could not copy", "retry_answer": "Retry answer", "check_status": "Check status",
    "brief": "Trip details", "stay": "Stay", "nights": "nights", "adults": "adults",
    "children": "children", "age": "age", "unknown": "Unknown", "pending_age": "What is the child's age?",
    "updated": "Updated", "partial_success": "Trip details saved; answer pending",
    "stale_answer": "This answer may be out of date", "ai_notice": "AI-generated answer",
    "synthetic_notice": "Sample hotel information",
}
_URL = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_CACHE: dict[str, dict[str, str]] = {}
_LOCK = Lock()


def missing_label_keys(language_tag: str) -> list[str]:
    with _LOCK:
        cached = _CACHE.get(language_tag, {})
        return [key for key in LABEL_KEYS if key not in cached]


def resolve_label_bundle(language_tag: str, proposed: object) -> dict[str, str]:
    """Accept and cache a complete missing-key bundle atomically, else return safe fallback."""
    with _LOCK:
        cached = dict(_CACHE.get(language_tag, {}))
        missing = [key for key in LABEL_KEYS if key not in cached]
        valid = isinstance(proposed, dict) and set(proposed) == set(missing)
        if valid:
            for value in proposed.values():
                if (not isinstance(value, str) or not value.strip() or len(value) > 80
                        or any(unicodedata.category(char).startswith("C") for char in value)
                        or any(char in value for char in "<>{}") or _URL.search(value)):
                    valid = False
                    break
        if valid and missing:
            merged = {**cached, **{key: value.strip() for key, value in proposed.items()}}
            if language_tag not in _CACHE and len(_CACHE) >= 32:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[language_tag] = merged
            cached = merged
        return {key: cached.get(key, ENGLISH_LABELS[key]) for key in LABEL_KEYS}


def labels_fallback(language_tag: str) -> bool:
    with _LOCK:
        cached = _CACHE.get(language_tag, {})
        return language_tag.split("-")[0] != "en" and any(key not in cached for key in LABEL_KEYS)
