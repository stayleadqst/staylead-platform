"""Applicability boundary for finite Hospitality claim-property profiles."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_PROFILE_FIELDS = frozenset({"parking", "deposit"})
_PROFILE_TEXT = re.compile(
    r"\bparking\b|\bcar\s+park\b|bãi\s+(?:đỗ\s+)?xe|đỗ\s+xe|"
    r"\bdeposit\b|khoản\s+bảo\s+đảm",
    re.IGNORECASE,
)


def hospitality_claim_consistency_applies(
    claim_text: str, cited_current_facts: Iterable[dict[str, Any]],
) -> bool:
    """Return whether this finite checker has an active property profile.

    Applicability comes from the cited/current fact's semantic field or an
    explicit parking/deposit subject in the claim. Other Hospitality topics
    continue through the existing citation, literal, URL, and status guards;
    absence of a finite profile is never reported as semantic verification.
    """
    if _PROFILE_TEXT.search(claim_text):
        return True
    return any(
        str(fact.get("field", "")).casefold() in _PROFILE_FIELDS
        or str(fact.get("topic", "")).casefold() in _PROFILE_FIELDS
        for fact in cited_current_facts
    )
