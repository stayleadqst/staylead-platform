"""Finite source-property checks for factual Hospitality answer assertions.

Unrecognized source grammar or answer semantics is unknown, never implicitly
supported. This is not a general natural-language entailment checker.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from staylead_platform.platform.contracts.claim_consistency import (
    AssertionConsistency,
    ClaimConsistencyResult,
    ClaimConsistencyStatus,
)

_FACT_REF = re.compile(r"\[F-[A-Za-z0-9-]+\]")
_QUOTE = re.compile(r'"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’')
_PARKING = re.compile(r"\bparking\b|\bcar park\b|bãi\s+(?:đỗ\s+)?xe|đỗ\s+xe", re.IGNORECASE)
_DEPOSIT = re.compile(r"\bdeposit\b|khoản\s+bảo\s+đảm", re.IGNORECASE)
_CURRENCIES = ("VND", "USD", "EUR", "JPY", "CNY", "GBP", "AUD", "CAD", "SGD", "THB")
_MONEY = re.compile(
    r"(?<!\d)(?P<amount>\d[\d.,\u0660-\u0669\u06f0-\u06f9]*)\s*(?P<currency>"+
    "|".join(_CURRENCIES)+r")\b|\b(?P<currency_first>"+"|".join(_CURRENCIES)+
    r")\s*(?P<amount_first>\d[\d.,\u0660-\u0669\u06f0-\u06f9]*)(?!\d)", re.IGNORECASE,
)
_DIMENSION_TERMS = {
    "vehicle": ("vehicle", "car", "xe"),
    "night": ("night", "đêm"),
    "stay": ("stay", "lưu trú"),
    "room": ("room", "phòng"),
}
_DIMENSION = re.compile(
    r"\b(?:per|par)\s+(?P<en>vehicle|car|night|stay|room|véhicule|nuit|séjour|chambre)\b|"
    r"\bmỗi\s+(?P<vi>xe|đêm|lưu trú|phòng)\b", re.IGNORECASE,
)
_FREE = re.compile(r"\bfree\b|\bcomplimentary\b|\bno\s+charge\b|miễn\s+phí|\bgratuit\b", re.IGNORECASE)
_COVERED = re.compile(r"\bcovered\b|\broofed\b|\bcouvert\b|mái\s+che", re.IGNORECASE)
_NOT_COVERED = re.compile(r"\bnot\s+covered\b|\buncovered\b|\bnon[- ]couvert\b|\bpas\s+couvert\b|không\s+có\s+mái\s+che", re.IGNORECASE)
_RESERVATION = re.compile(
    r"\bguarantee(?:d)?\b|\breserv(?:e|ed|ation)\b|\bbook(?:ed)?\s+(?:a\s+)?space\b|"
    r"bảo\s+lưu|giữ\s+chỗ|đặt\s+chỗ", re.IGNORECASE,
)
_REFUND = re.compile(r"\brefund(?:able)?\b|\brefundable\b|hoàn", re.IGNORECASE)
_NEGATION = re.compile(r"(?:^|\b)(?:not|no|isn't|aren't|cannot|can't|không|chưa)(?:\s+\w+){0,2}\s*$", re.IGNORECASE)
_CONJUNCTION = re.compile(r"\s+(?:and|but|or)\s+", re.IGNORECASE)
_ELLIPTICAL_START = re.compile(
    r"^(?:(?:and|or|but)\s+)?(?:a\s+space|the\s+space|space|it|not\b|no\b|free\b|complimentary\b|"
    r"guaranteed\b|reserved\b|reservation\b|fee\b|costs?\b|is\b|are\b|\d|VND\b|USD\b|"
    r"không\b|chưa\b|được\b|phí\b|mỗi\b)", re.IGNORECASE,
)
_OTHER_SUBJECT = re.compile(r"\b(?:swimming\s+pool|pool|breakfast|restaurant|room|check[- ]?in)\b", re.IGNORECASE)
_MONEY_TEXT = r"\d[\d.,]*\s*(?:VND|USD|EUR|JPY|CNY|GBP|AUD|CAD|SGD|THB)"
_BASIS_TEXT = r"(?:per\s+(?:vehicle|car)\s+per\s+night|per\s+night\s+per\s+(?:vehicle|car)|cho\s+mỗi\s+xe\s+mỗi\s+đêm|per\s+room\s+per\s+stay)"


@dataclass(frozen=True)
class _FactProfile:
    fact_id: str
    hotel_id: str
    subject: str
    field: str
    amount: int | None
    currency: str | None
    basis: tuple[str, ...]
    covered: bool | None
    no_reservation: bool | None
    refund_after_reconciliation: bool | None
    source_recognized: bool


def _digits(value: str) -> str:
    return "".join(str(unicodedata.decimal(char)) if char.isdecimal() else char for char in value)


def _normalized_amount(value: str) -> int | None:
    digits = _digits(value)
    if not digits.isdecimal():
        return None
    return int(digits)


def _money_occurrences(text: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for match in _MONEY.finditer(text):
        raw_amount = match.group("amount") or match.group("amount_first")
        currency = match.group("currency") or match.group("currency_first")
        amount = _normalized_amount(raw_amount)
        if amount is not None and currency:
            found.append((amount, currency.upper(), match.group(0)))
    return found


def _dimensions(text: str) -> tuple[str, ...]:
    result: list[str] = []
    for match in _DIMENSION.finditer(text):
        en, vi = match.group("en"), match.group("vi")
        if en:
            result.append({"car": "vehicle", "véhicule": "vehicle", "nuit": "night", "séjour": "stay", "chambre": "room"}.get(en.casefold(), en.casefold()))
        elif vi:
            result.append({"xe": "vehicle", "đêm": "night", "lưu trú": "stay", "phòng": "room"}[vi.casefold()])
    return tuple(result)


def _source_profile(fact: dict[str, Any]) -> _FactProfile:
    """Extract only explicitly supported source properties; never infer availability from lifecycle status."""
    fact_id = fact.get("fact_id")
    hotel_id = fact.get("hotel_id")
    subject = str(fact.get("topic") or fact.get("subject") or "")
    field = str(fact.get("field") or "")
    value = str(fact.get("value") or "")
    conditions = fact.get("conditions") if isinstance(fact.get("conditions"), dict) else {}
    source_money = _money_occurrences(value)
    amount = source_money[0][0] if len(source_money) == 1 else None
    currency = source_money[0][1] if len(source_money) == 1 else None
    unit = str(conditions.get("unit") or conditions.get("basis") or "")
    basis = _dimensions(unit)
    is_parking = subject == "parking" or field == "parking"
    recognized = bool(
        isinstance(fact_id, str) and isinstance(hotel_id, str)
        and fact.get("status") == "confirmed" and value
    )
    if is_parking:
        recognized = recognized and amount is not None and currency is not None and len(basis) == 2
        covered = True if re.search(r"có\s+mái\s+che|covered\s+parking", value, re.IGNORECASE) else None
        no_reservation = True if re.search(r"không\s+bảo\s+lưu\s+chỗ|no\s+spaces?\s+reserved", value, re.IGNORECASE) else None
        recognized = recognized and covered is True and no_reservation is True
        refund_after_reconciliation = None
    else:
        # Generic exact money profile is usable only when both amount and typed basis are present.
        recognized = recognized and amount is not None and currency is not None and bool(basis)
        covered = None
        no_reservation = None
        refund_after_reconciliation = (
            True if re.search(r"hoàn\s+theo\s+đối\s+soát\s+sau\s+trả\s+phòng", value, re.IGNORECASE)
            or re.search(r"refundable\s+after\s+reconciliation\s+after\s+checkout", value, re.IGNORECASE)
            else None
        )
    return _FactProfile(
        fact_id=str(fact_id or ""), hotel_id=str(hotel_id or ""), subject=subject,
        field=field, amount=amount, currency=currency, basis=basis,
        covered=covered, no_reservation=no_reservation, source_recognized=bool(recognized),
        refund_after_reconciliation=refund_after_reconciliation,
    )


def _is_negated(text: str, start: int) -> bool:
    prefix = text[:start].casefold().rstrip()
    return bool(
        _NEGATION.search(prefix)
        or re.search(r"(?:n['’]est\s+pas|ne\s+\w+\s+pas|pas)\s*$", prefix, re.IGNORECASE)
    )


def _split_assertions(text: str) -> list[str]:
    """Split at sentence/dash boundaries outside quotes; retain original snippets."""
    pieces: list[str] = []
    start = 0
    quote_end: str | None = None
    pairs = {"“": "”", "‘": "’", '"': '"'}
    for index, char in enumerate(text):
        if quote_end is not None:
            if char == quote_end:
                quote_end = None
            continue
        if char in pairs:
            quote_end = pairs[char]
            continue
        if char in ".!?;" or (
            char in "—–" and index > 0 and index + 1 < len(text)
            and text[index - 1].isspace() and text[index + 1].isspace()
        ) or (
            char == "," and index > 0 and index + 1 < len(text)
            and not text[index - 1].isdigit() and not text[index + 1].isdigit()
        ):
            pieces.append(text[start:index+1].strip())
            start = index + 1
    if text[start:].strip():
        pieces.append(text[start:].strip())
    assertions: list[str] = []
    for piece in pieces:
        visible_piece = _QUOTE.sub(" ", _FACT_REF.sub(" ", piece))
        if not visible_piece.strip():
            assertions.append(piece)
            continue
        # Split coordinated factual assertions, carrying an explicit prior subject
        # only to interpret elliptical siblings such as “and a space is guaranteed”.
        clauses = _CONJUNCTION.split(piece)
        assertions.extend(re.sub(r"^(?:and|or|but)\s+", "", clause.strip(), flags=re.IGNORECASE)
                          for clause in clauses if clause.strip())
    return assertions


def _nonassertive(original: str, visible: str, *, has_inherited_subject: bool = False) -> bool:
    if not visible.strip():
        return True
    if visible.rstrip().endswith("?"):
        return True
    if re.match(r"^(?:what|where|when|why|how|do|does)\b", visible.strip(), re.IGNORECASE):
        return True
    # A leading verb can be a question, or an elliptical declarative clause after
    # an explicit subject-bearing sibling (“and is refundable…”).
    return bool(
        not has_inherited_subject
        and re.match(r"^(?:is|are|can)\b", visible.strip(), re.IGNORECASE)
    )


def _subject_for(text: str) -> str | None:
    # Denominator dimensions describe the price basis, not the claim's entity.
    entity_text = _MONEY.sub(" ", text)
    entity_text = re.sub(
        r"\b(?:per|par)\s+(?:room|stay|vehicle|car|night)(?:\s+per\s+(?:room|stay|vehicle|car|night))*\b",
        " ", entity_text, flags=re.IGNORECASE,
    )
    entity_text = re.sub(r"\bmỗi\s+(?:xe|đêm|lưu trú|phòng)(?:\s+mỗi\s+(?:xe|đêm|lưu trú|phòng))*\b", " ", entity_text, flags=re.IGNORECASE)
    other = _OTHER_SUBJECT.search(entity_text)
    if other:
        return f"other:{other.group(0).casefold()}"
    subjects = []
    if _PARKING.search(entity_text):
        subjects.append("parking")
    if _DEPOSIT.search(entity_text):
        subjects.append("deposit")
    return subjects[0] if len(set(subjects)) == 1 else None


def _resolve_subject(text: str, inherited: str | None) -> str | None:
    explicit = _subject_for(text)
    if explicit is not None:
        return explicit
    return inherited if inherited and _ELLIPTICAL_START.search(text.strip()) else None


def _parking_span_fully_recognized(text: str) -> bool:
    """Accept only complete finite assertion forms; extra factual wording is unknown."""
    value = _FACT_REF.sub("", _QUOTE.sub(" ", text)).strip().rstrip(".!?;,").casefold()
    patterns = (
        r"(?:the\s+)?(?:parking(?:\s+area)?|car\s+park)\s+(?:is\s+)?(?:covered|roofed)",
        r"covered\s+parking(?:\s+area)?(?:\s+is\s+available)?",
        r"bãi\s+(?:đỗ\s+)?xe\s+có\s+mái\s+che",
        r"(?:the\s+)?(?:parking(?:\s+fee)?|fee)\s+(?:costs?\s+|is\s+)?"+_MONEY_TEXT+r"\s+"+_BASIS_TEXT,
        r"(?:parking\s+)?costs?\s+"+_MONEY_TEXT+r"\s+"+_BASIS_TEXT,
        r"phí\s+"+_MONEY_TEXT+r"\s+cho\s+mỗi\s+xe\s+mỗi\s+đêm",
        r"(?:the\s+)?parking\s+is\s+(?:not\s+)?(?:free|complimentary)",
        r"parking\s+is\s+not\s+free",
        r"(?:a\s+)?(?:parking\s+)?space\s+is\s+(?:not\s+)?(?:guaranteed|reserved)",
        r"(?:the\s+)?parking\s+is\s+(?:not\s+)?(?:guaranteed|reserved)",
        r"reservation\s+is\s+(?:not\s+)?guaranteed",
        r"(?:không\s+)?bảo\s+lưu\s+chỗ",
        r"(?:không\s+)?được\s+giữ\s+chỗ",
        r"bãi\s+(?:đỗ\s+)?xe\s+không\s+bảo\s+lưu\s+chỗ",
        r"(?:parking\s+)?(?:un)?covered",
        r"(?:the\s+)?parking\s+(?:is\s+)?not\s+covered",
        _MONEY_TEXT,
    )
    return any(re.fullmatch(pattern, value, re.IGNORECASE) for pattern in patterns)


def _deposit_span_fully_recognized(text: str) -> bool:
    value = _FACT_REF.sub("", _QUOTE.sub(" ", text)).strip().rstrip(".!?;, ").casefold()
    patterns = (
        r"(?:the\s+)?deposit\s+(?:is\s+)?" + _MONEY_TEXT + r"\s+per\s+room\s+per\s+stay",
        r"(?:it\s+)?is\s+refundable\s+after\s+reconciliation\s+after\s+checkout",
        r"refundable\s+after\s+reconciliation\s+after\s+checkout",
        r"(?:it\s+)?is\s+unconditionally\s+refundable",
        _MONEY_TEXT,
    )
    return any(re.fullmatch(pattern, value, re.IGNORECASE) for pattern in patterns)


def _outcome(
    text: str,
    status: ClaimConsistencyStatus,
    fact_ids: tuple[str, ...],
    subject: str | None,
    field: str | None,
    property_name: str | None,
    reason: str,
    *,
    assertive: bool = True,
) -> AssertionConsistency:
    return AssertionConsistency(
        text=text, status=status, fact_ids=fact_ids, subject=subject, field=field,
        property_name=property_name, reason=reason, assertive=assertive,
    )


def _classify_assertion(
    text: str,
    facts: list[dict[str, Any]],
    channel: str,
    fact_ids: tuple[str, ...],
    inherited_subject: str | None = None,
) -> list[AssertionConsistency]:
    visible = _QUOTE.sub(" ", _FACT_REF.sub(" ", text)).strip()
    if _nonassertive(text, visible, has_inherited_subject=inherited_subject is not None):
        return [_outcome(text, ClaimConsistencyStatus.UNKNOWN, fact_ids, None, None, None, "non_assertive_question_or_quote", assertive=False)]
    subject = _subject_for(visible) or inherited_subject
    candidates = [_source_profile(fact) for fact in facts]
    matching = [profile for profile in candidates if subject and profile.subject == subject]
    if not subject:
        return [_outcome(text, ClaimConsistencyStatus.UNKNOWN, (), subject, None, None, "subject_or_fact_binding_unknown")]
    if not matching:
        return [_outcome(text, ClaimConsistencyStatus.UNKNOWN, (), subject, None, None, "property_fact_not_cited")]
    if len(matching) != 1:
        return [_outcome(text, ClaimConsistencyStatus.UNKNOWN, (), subject, None, None, "subject_or_fact_binding_unknown")]
    profile = matching[0]
    if profile.fact_id not in fact_ids:
        return [_outcome(text, ClaimConsistencyStatus.UNKNOWN, (), subject, profile.field, None, "property_fact_not_cited")]
    bound_fact_ids = (profile.fact_id,)
    if not profile.source_recognized:
        return [_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, None, "source_property_parse_unknown")]

    outcomes: list[AssertionConsistency] = []
    # Every currency occurrence in this assertion is checked against the bound source property.
    money = _money_occurrences(visible)
    if money:
        observed_dims = _dimensions(visible)
        for amount, currency, _raw in money:
            if amount != profile.amount or currency != profile.currency:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.CONTRADICTED, bound_fact_ids, subject, profile.field, "amount", "amount_or_currency_mismatch"))
            elif sorted(observed_dims) != sorted(profile.basis):
                outcomes.append(_outcome(text, ClaimConsistencyStatus.CONTRADICTED, bound_fact_ids, subject, profile.field, "basis", "basis_dimension_mismatch"))
            else:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.VERIFIED, bound_fact_ids, subject, profile.field, "amount_currency_basis", "money_property_match"))

    if subject == "parking":
        for match in _FREE.finditer(visible):
            negated = _is_negated(visible, match.start())
            if profile.amount is None:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, "fee.amount", "fee_property_unknown"))
            else:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.VERIFIED if negated else ClaimConsistencyStatus.CONTRADICTED, bound_fact_ids, subject, profile.field, "fee.amount", "fee_not_free" if negated else "unsupported_fee_free_assertion"))
        for match in _NOT_COVERED.finditer(visible):
            if profile.covered is True and not _is_negated(visible, match.start()):
                outcomes.append(_outcome(text, ClaimConsistencyStatus.CONTRADICTED, bound_fact_ids, subject, profile.field, "parking.covered", "covered_property_mismatch"))
        for match in _COVERED.finditer(visible):
            if profile.covered is not True:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, "parking.covered", "covered_property_unknown"))
            elif not _NOT_COVERED.search(visible):
                outcomes.append(_outcome(text, ClaimConsistencyStatus.VERIFIED, bound_fact_ids, subject, profile.field, "parking.covered", "covered_property_match"))
        for match in _RESERVATION.finditer(visible):
            if profile.no_reservation is None:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, "parking.reservation", "reservation_property_unknown"))
            else:
                negated = _is_negated(visible, match.start())
                outcomes.append(_outcome(text, ClaimConsistencyStatus.VERIFIED if negated else ClaimConsistencyStatus.CONTRADICTED, bound_fact_ids, subject, profile.field, "parking.reservation", "reservation_not_guaranteed" if negated else "reservation_constraint_mismatch"))
        if not _parking_span_fully_recognized(visible) and re.search(
            r"\bunderground\b|\bavailable\b|\bopen\b|\bclosed\b|\bclean\b|\bnearby\b", visible, re.IGNORECASE,
        ):
            outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, None, "parking_status_or_constraint_outside_profile"))
        if not _parking_span_fully_recognized(visible):
            outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, None, "factual_span_not_fully_covered"))
        if not outcomes:
            outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, None, "parking_assertion_outside_profile"))
        return outcomes

    if subject == "deposit":
        if _REFUND.search(visible):
            if profile.refund_after_reconciliation is None:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, "refund_after_reconciliation", "refund_condition_unknown"))
            elif re.search(r"unconditionally\s+refundable|refundable\s+immediately|hoàn\s+vô\s+điều\s+kiện", visible, re.IGNORECASE):
                outcomes.append(_outcome(text, ClaimConsistencyStatus.CONTRADICTED, bound_fact_ids, subject, profile.field, "refund_after_reconciliation", "source_requires_reconciliation_after_checkout"))
            elif re.search(r"refundable\s+after\s+reconciliation\s+after\s+checkout|hoàn\s+theo\s+đối\s+soát\s+sau\s+trả\s+phòng", visible, re.IGNORECASE):
                outcomes.append(_outcome(text, ClaimConsistencyStatus.VERIFIED, bound_fact_ids, subject, profile.field, "refund_after_reconciliation", "refund_condition_match"))
            else:
                outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, "refund_after_reconciliation", "refund_condition_parse_unknown"))
        fully_recognized = _deposit_span_fully_recognized(visible)
        if not fully_recognized:
            outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, None, "factual_span_not_fully_covered"))
        if not outcomes:
            outcomes.append(_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, None, "deposit_assertion_outside_profile"))
        return outcomes

    if money:
        return outcomes
    return [_outcome(text, ClaimConsistencyStatus.UNKNOWN, bound_fact_ids, subject, profile.field, None, "claim_property_outside_profile")]


def validate_hospitality_claim(
    claim_text: str, cited_current_facts: list[dict[str, Any]], channel: str = "supported_claim",
) -> ClaimConsistencyResult:
    """Return per-assertion outcomes bound to cited/current facts for this channel."""
    inline_fact_ids = tuple(dict.fromkeys(match[1:-1] for match in _FACT_REF.findall(claim_text)))
    fact_ids = inline_fact_ids or tuple(dict.fromkeys(
        str(fact.get("fact_id")) for fact in cited_current_facts if isinstance(fact.get("fact_id"), str)
    ))
    segments = _split_assertions(_FACT_REF.sub(" ", claim_text)) or [claim_text]
    assertions: list[AssertionConsistency] = []
    subject_hint: str | None = None
    for segment in segments:
        visible = _QUOTE.sub(" ", _FACT_REF.sub(" ", segment)).strip()
        subject_hint = _resolve_subject(visible, subject_hint)
        assertions.extend(_classify_assertion(segment, cited_current_facts, channel, fact_ids, subject_hint))
    return ClaimConsistencyResult(tuple(assertions))
