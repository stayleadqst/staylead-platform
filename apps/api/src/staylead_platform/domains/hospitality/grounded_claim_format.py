"""Deterministic, language-neutral formatting for cited Hospitality claims."""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_CLOCK = re.compile(r"(?<![0-9A-Za-z_])([01]?[0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?(?![0-9A-Za-z_])")
_URL = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
_FIELD = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FACT_LABELS = {
    "name": "Property name",
    "address": "Address",
    "property_type": "Property type",
    "check_in_window": "Check-in window",
    "check_out_time": "Check-out time",
    "early_check_in": "Early check-in",
    "late_checkout": "Late checkout",
    "breakfast_hours": "Breakfast hours",
    "staffed_hours": "Reception staffed hours",
    "quiet_hours": "Quiet hours",
    "luggage_storage": "Luggage storage",
    "cancellation": "Cancellation terms",
    "booking_changes": "Booking changes",
    "deposit": "Deposit",
    "accepted_methods": "Accepted payment methods",
    "invoice_request": "Invoice request",
    "extra_person": "Extra-person occupancy",
    "child_age_definition": "Child age definition",
    "minor_guardian": "Minor guest policy",
    "step_free_access": "Step-free access",
    "reservation_required": "Reservation required",
    "minimum_age": "Minimum age",
    "maximum_age": "Maximum age",
    "applicability": "Applies to",
    "season": "Season",
}
_PROVENANCE_ONLY_CONDITIONS = {"synthetic", "source_checked_at"}


def _safe_scalar(value: Any) -> str | None:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and value and len(value) <= 600 and not any(
        unicodedata.category(char) in {"Cc", "Cf"} for char in value
    ):
        return value
    return None


def _condition_text(conditions: Any) -> str | None:
    if not isinstance(conditions, dict):
        return None if conditions is None else ""
    details = []
    for key, value in conditions.items():
        if key in _PROVENANCE_ONLY_CONDITIONS:
            continue
        if not isinstance(key, str) or not _FIELD.fullmatch(key) or key.endswith(("_id", "_ids", "_code")):
            return ""
        if key == "timezone":
            rendered = _valid_timezone(value)
            if rendered is None:
                return ""
            details.append(f"timezone {rendered}")
            continue
        rendered = _safe_scalar(value)
        if rendered is None and isinstance(value, dict) and set(value) == {"start", "end"}:
            start, end = _safe_scalar(value.get("start")), _safe_scalar(value.get("end"))
            if start and end:
                rendered = f"{start} to {end}"
        if rendered is None:
            return ""
        label = _FACT_LABELS.get(key, key.replace("_", " ").capitalize())
        details.append(f"{label.lower()} {rendered}")
    return ", ".join(details) if details else None


def project_grounded_fact(fact: dict[str, Any]) -> str | None:
    """Render a current M1 Hospitality fact without using model-authored prose.

    Only a small set of guest-safe labels and scalar values are projected. Local
    guide facts use their typed server-side cards, while unsupported or complex
    values become a safe confirmation prompt instead of being serialized.
    """
    if not isinstance(fact, dict) or str(fact.get("topic", "")).startswith("local_guide."):
        return None
    field = fact.get("field")
    if not isinstance(field, str) or not _FIELD.fullmatch(field) or field.endswith(("_id", "_ids", "_code")):
        return None
    label = _FACT_LABELS.get(field, field.replace("_", " ").capitalize())
    if fact.get("status") != "confirmed":
        return f"The current approved hotel record does not confirm {label.lower()}; please verify it with the hotel."
    value = fact.get("value")
    rendered = None
    if field == "check_in_window" and isinstance(value, dict) and set(value) <= {"start", "end"}:
        start, end = _safe_scalar(value.get("start")), _safe_scalar(value.get("end"))
        if start and end:
            rendered = f"{start} to {end}"
    if rendered is None:
        rendered = _safe_scalar(value)
    if rendered is None:
        return f"The current approved hotel record for {label.lower()} cannot be summarized safely; please confirm this detail with the hotel."
    conditions = _condition_text(fact.get("conditions"))
    if conditions == "":
        return f"The current approved hotel record for {label.lower()} cannot be summarized safely; please confirm this detail with the hotel."
    suffix = f" ({conditions})" if conditions else ""
    return f"{label}: {rendered}{suffix}."


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
