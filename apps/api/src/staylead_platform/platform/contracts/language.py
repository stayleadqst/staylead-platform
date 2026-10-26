"""Provider-neutral language preference and answer presentation contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

LanguageSource = Literal["explicit", "inferred", "fallback"]
AnswerEligibility = Literal["current", "pending", "stale"]
_TAG = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


def normalize_language_tag(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 64 or not _TAG.fullmatch(candidate):
        return None
    parts = candidate.split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(part.upper() if len(part) == 2 and part.isalpha() else part.title() if len(part) == 4 and part.isalpha() else part.lower())
    return "-".join(normalized)


def language_direction(language_tag: str) -> Literal["ltr", "rtl"]:
    rtl = {"Arab", "Hebr", "Thaa", "Nkoo", "Adlm", "Rohg", "Syrc"}
    parts = language_tag.split("-")
    explicit_script = next((part for part in parts[1:] if len(part) == 4 and part.isalpha()), None)
    if explicit_script is not None:
        return "rtl" if explicit_script.title() in rtl else "ltr"
    return "rtl" if parts[0] in {"ar", "he", "fa", "ur", "ps", "yi", "sd", "ug"} else "ltr"


@dataclass(frozen=True)
class LanguagePreference:
    language_tag: str
    source: LanguageSource
    revision: int


@dataclass(frozen=True)
class AnswerPresentation:
    language_tag: str
    direction: Literal["ltr", "rtl"]
    preference_revision: int
    labels: dict[str, str]
    labels_fallback: bool
    freshness: Literal["current", "stale"]
    receipt_id: str | None = None

