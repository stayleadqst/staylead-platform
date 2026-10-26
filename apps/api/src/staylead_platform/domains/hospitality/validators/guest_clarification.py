"""Hospitality-specific validation for a checkout-choice clarification."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from staylead_platform.domains.hospitality.schemas.grounded_answer import GuestClarification

_CHECKOUT_CHOICE = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)")
_URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
_FACT_TOKEN = re.compile(r"(?<![A-Za-z0-9])F-[A-Za-z0-9-]+")
_NUMBER_TOKEN = re.compile(r"(?<!\d)\d+(?:(?:[-/:.,])\d+)*(?!\d)")


def _number_tokens(text: str) -> list[str]:
    return [
        "".join(
            str(unicodedata.decimal(char)) if unicodedata.category(char) == "Nd" else char
            for char in match.group()
        )
        for match in _NUMBER_TOKEN.finditer(text)
    ]


def validate_checkout_clarification(
    clarification: Any,
    question: str,
    brief_data: dict[str, Any] | None,
    pending_fields: tuple[str, ...],
) -> tuple[str, tuple[str, ...]] | None:
    """Bind a typed checkout question to two choices in this utterance only."""
    if (
        not isinstance(clarification, GuestClarification)
        or brief_data is None
        or clarification.field != "dates.check_out"
        or clarification.field not in pending_fields
    ):
        return None
    choices = _CHECKOUT_CHOICE.findall(question)
    if len(choices) != 1 or choices[0][0] == choices[0][1]:
        return None
    expected = list(choices[0])
    if clarification.options != expected:
        return None
    text = clarification.text.strip()
    if (
        not text or _URL.search(text) or _FACT_TOKEN.search(text)
        or any(char in text for char in "<>{}/")
        or any(unicodedata.category(char) in {"Cc", "Cf"} for char in text)
    ):
        return None
    forms = _number_tokens(text)
    option_forms = [_number_tokens(option)[0] for option in expected]
    allowed = set(option_forms)
    refs: tuple[str, ...] = ()
    check_in = (brief_data.get("dates") or {}).get("check_in")
    if "dates.check_in" not in pending_fields and isinstance(check_in, str):
        match = re.fullmatch(r"(\d{4})-\d{2}-\d{2}", check_in)
        if match:
            allowed.add(match.group(1))
            if match.group(1) in forms:
                refs = ("dates.check_in",)
    if not set(option_forms) <= set(forms) or not set(forms) <= allowed:
        return None
    return text, refs
