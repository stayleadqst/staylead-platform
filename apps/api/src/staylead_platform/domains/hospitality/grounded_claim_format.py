"""Deterministic, language-neutral formatting for cited Hospitality claims."""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_CLOCK = re.compile(r"(?<![0-9A-Za-z_])([01]?[0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?(?![0-9A-Za-z_])")
_URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)


def _ascii_decimal_digits(text: str) -> str:
    """Normalize only Unicode decimal digits so clock values can be compared."""
    normalized: list[str] = []
    for char in text:
        try:
            normalized.append(str(unicodedata.decimal(char)))
        except (TypeError, ValueError):
            normalized.append(char)
    return "".join(normalized)


def _clock_times(text: str) -> set[str]:
    without_urls = _URL.sub(" ", text)
    normalized = _ascii_decimal_digits(without_urls)
    return {match.group(0) for match in _CLOCK.finditer(normalized)}


def _valid_timezone(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return value


def format_grounded_claim(text: str, cited_facts: list[dict[str, Any]]) -> str:
    """Append one cited timezone to a time claim, preserving all claim text.

    The caller supplies only facts already validated as citations for this
    claim. A zone is added only when the claim clock appears literally in that
    fact's value or conditions.window and the matching fact has a valid IANA
    timezone. Missing or conflicting matching zones leave the claim unchanged.
    """
    if not text or not cited_facts:
        return text
    if not isinstance(text, str):
        return text
    claim_times = _clock_times(text)
    if not claim_times:
        return text

    zones_by_claim_time: dict[str, set[str]] = {clock_time: set() for clock_time in claim_times}
    for fact in cited_facts:
        if not isinstance(fact, dict):
            continue
        conditions = fact.get("conditions")
        value = fact.get("value")
        window = conditions.get("window") if isinstance(conditions, dict) else None
        source_times: set[str] = set()
        if isinstance(value, str):
            source_times.update(_clock_times(value))
        if isinstance(window, str):
            source_times.update(_clock_times(window))
        matching_times = claim_times.intersection(source_times)
        if not matching_times:
            continue
        zone = _valid_timezone(conditions.get("timezone")) if isinstance(conditions, dict) else None
        if zone is None:
            return text
        for clock_time in matching_times:
            zones_by_claim_time[clock_time].add(zone)

    if any(len(zones) != 1 for zones in zones_by_claim_time.values()):
        return text
    all_zones = {next(iter(zones)) for zones in zones_by_claim_time.values()}
    if len(all_zones) != 1:
        return text
    timezone = next(iter(all_zones))
    if timezone in text:
        return text
    return f"{text.rstrip()} ({timezone})"
