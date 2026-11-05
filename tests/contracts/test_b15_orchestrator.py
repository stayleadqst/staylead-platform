"""Independent property-level expectations for the B15 claim guard.

These cases are authored from the B15 AC and existing labeled synthetic facts.
They do not import or execute the exhausted scratch prototype.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from staylead_platform.domains.hospitality.claim_consistency import (
    validate_hospitality_claim,
)
from staylead_platform.platform.contracts.claim_consistency import (
    ClaimConsistencyStatus,
)

FACTS_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1" / "facts.json"
_ALL_FACTS = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
_BY_ID = {fact["fact_id"]: fact for fact in _ALL_FACTS}
PARKING = _BY_ID["F-HTL-CITY01-046"]
DEPOSIT = _BY_ID["F-HTL-CITY01-013"]
CURRENT_FACTS = [PARKING, DEPOSIT]


@pytest.mark.parametrize(
    ("case", "claim", "cited_facts", "expected"),
    [
        ("negative_free_guaranteed", "Parking is free and a space is guaranteed. [F-HTL-CITY01-046]", CURRENT_FACTS, {("fee.amount", "contradicted"), ("parking.reservation", "contradicted")}),
        ("negative_wrong_amount", "Parking costs 120000 VND per vehicle per night. [F-HTL-CITY01-046]", CURRENT_FACTS, {("amount", "contradicted")}),
        ("negative_wrong_basis", "Parking costs 100000 VND per stay. [F-HTL-CITY01-046]", CURRENT_FACTS, {("basis", "contradicted")}),
        ("negative_invented_citation", "Covered parking is available. [F-HTL-CITY01-999]", CURRENT_FACTS, {(None, "unknown")}),
        ("negative_unsupported_reservation", "A parking space can be reserved on request. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.reservation", "contradicted")}),
        ("positive_full_translation_vi", "Bãi đỗ xe có mái che, phí 100000 VND cho mỗi xe mỗi đêm. [F-HTL-CITY01-046] Bãi xe không bảo lưu chỗ. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.covered", "verified"), ("amount_currency_basis", "verified"), ("parking.reservation", "verified")}),
        ("positive_negated", "Parking is not free and a space is not guaranteed. [F-HTL-CITY01-046]", CURRENT_FACTS, {("fee.amount", "verified"), ("parking.reservation", "verified")}),
        ("positive_covered_only", "Covered parking is available. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.covered", "verified")}),
        ("positive_basis_reordered", "Parking costs 100000 VND per night per vehicle. [F-HTL-CITY01-046]", CURRENT_FACTS, {("amount_currency_basis", "verified")}),
        ("positive_question_quote", "You asked, “Is parking free?” The parking area is covered. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.covered", "verified"), (None, "unknown")}),
        ("positive_translation_outside_predicates", "屋根付き駐車場があります。 [F-HTL-CITY01-046]", CURRENT_FACTS, {(None, "unknown")}),
        ("typed_fact_wrong_amount", "The deposit is 600000 VND per room per stay. [F-HTL-CITY01-013]", CURRENT_FACTS, {("amount", "contradicted")}),
        # F013 supports the amount and contradicts unconditional refund;
        # the negative sibling must prevent release of the whole span.
        ("q_deposit_unconditional_refund", "The deposit is 500000 VND per room per stay and is unconditionally refundable. [F-HTL-CITY01-013]", CURRENT_FACTS, {("amount_currency_basis", "verified"), ("refund_after_reconciliation", "contradicted")}),
        ("question_suffix_bypass", "Parking is free. [F-HTL-CITY01-046] Any questions?", CURRENT_FACTS, {("fee.amount", "contradicted"), (None, "unknown")}),
        ("quotation_bypass", "You asked “Is parking free?” Parking is free. [F-HTL-CITY01-046]", CURRENT_FACTS, {("fee.amount", "contradicted")}),
        ("negation_cross_assertion", "Parking is not free. [F-HTL-CITY01-046] Parking is free. [F-HTL-CITY01-046]", CURRENT_FACTS, {("fee.amount", "verified"), ("fee.amount", "contradicted")}),
        ("wrong_time_basis", "Parking costs 100000 VND per vehicle per stay. [F-HTL-CITY01-046]", CURRENT_FACTS, {("basis", "contradicted")}),
        ("wrong_currency", "Parking costs 100000 USD per vehicle per night. [F-HTL-CITY01-046]", CURRENT_FACTS, {("amount", "contradicted")}),
        ("bad_sibling_kept_good", "Parking is free. [F-HTL-CITY01-046] The parking area is covered. [F-HTL-CITY01-046]", CURRENT_FACTS, {("fee.amount", "contradicted"), ("parking.covered", "verified")}),
        # Q's static counterexamples and additional independent quality cases.
        ("q_covered_but_uncovered", "Parking is not covered. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.covered", "contradicted")}),
        ("q_underground", "Parking is underground. [F-HTL-CITY01-046]", CURRENT_FACTS, {(None, "unknown")}),
        ("q_second_currency", "Parking costs 100000 VND per vehicle per night, or 100000 USD. [F-HTL-CITY01-046]", CURRENT_FACTS, {("amount_currency_basis", "verified"), ("amount", "contradicted")}),
        ("q_wrong_subject_same_value", "Parking costs 500000 VND per room per stay. [F-HTL-CITY01-013]", CURRENT_FACTS, {(None, "unknown")}),
        ("q_emdash_question", "Parking costs 100000 VND per night [F-HTL-CITY01-046] — any questions?", CURRENT_FACTS, {("basis", "contradicted"), (None, "unknown")}),
        ("q_unknown_source_grammar", "Parking is covered. [F-HTL-CITY01-046]", [{**PARKING, "value": "Parking record; conditions not parsed."}], {(None, "unknown")}),
        ("q_unmatched_staffing_span", "Parking is covered, guarded by licensed staff. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.covered", "verified"), (None, "unknown")}),
        ("q_unmatched_second_subject", "Parking is covered and the swimming pool is covered. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.covered", "verified"), (None, "unknown")}),
        ("valid_helpful_negation", "Parking is not free. [F-HTL-CITY01-046] Parking costs 100000 VND per vehicle per night. [F-HTL-CITY01-046]", CURRENT_FACTS, {("fee.amount", "verified"), ("amount_currency_basis", "verified")}),
        ("valid_concise", "Parking is covered and costs 100000 VND per vehicle per night. [F-HTL-CITY01-046]", CURRENT_FACTS, {("parking.covered", "verified"), ("amount_currency_basis", "verified")}),
    ],
)
def test_property_assertions_match_independent_expectation(case, claim, cited_facts, expected) -> None:
    result = validate_hospitality_claim(claim, cited_facts)
    observed = {(item.property_name, item.status.value) for item in result.assertions}
    assert expected <= observed, case
    by_text = {}
    for item in result.assertions:
        by_text.setdefault(item.text, set()).add(item.status.value)
    for statuses in by_text.values():
        # A multi-outcome span cannot be promoted by one verified proposition
        # if a sibling assertion on the same span is unknown or contradicted.
        if "unknown" in statuses or "contradicted" in statuses:
            assert "verified" not in statuses, case
    for item in result.assertions:
        assert isinstance(item.status, ClaimConsistencyStatus)


def test_verified_assertions_keep_full_property_binding() -> None:
    result = validate_hospitality_claim(
        "Parking costs 100000 VND per vehicle per night. [F-HTL-CITY01-046]", CURRENT_FACTS,
    )
    assert len(result.assertions) == 1
    assertion = result.assertions[0]
    assert assertion.status is ClaimConsistencyStatus.VERIFIED
    assert assertion.fact_ids == ("F-HTL-CITY01-046",)
    assert assertion.subject == "parking"
    assert assertion.property_name is not None


def test_native_grounded_claim_uses_validated_external_fact_ids_without_inline_citation() -> None:
    # The production wire shape carries fact_ids beside claim text; inline
    # citation labels are appended by the response formatter, not required in
    # raw claim text.
    result = validate_hospitality_claim("Parking is covered.", [PARKING])
    assert len(result.assertions) == 1
    assertion = result.assertions[0]
    assert assertion.status is ClaimConsistencyStatus.VERIFIED
    assert assertion.fact_ids == ("F-HTL-CITY01-046",)
    assert assertion.subject == "parking"
    assert assertion.property_name == "parking.covered"


def test_japanese_valid_but_unrecognized_case_is_counted_as_unknown() -> None:
    expected_supported_propositions = 1  # The source-derived Japanese proposition is true.
    result = validate_hospitality_claim("屋根付き駐車場があります。 [F-HTL-CITY01-046]", CURRENT_FACTS)
    verified_propositions = sum(item.status is ClaimConsistencyStatus.VERIFIED for item in result.assertions)
    false_rejection = expected_supported_propositions - verified_propositions
    assert result.assertions[0].status is ClaimConsistencyStatus.UNKNOWN
    assert false_rejection == 1


def test_deposit_amount_does_not_support_unconditional_refund_claim() -> None:
    # F013 makes the refund subject to reconciliation after checkout.
    result = validate_hospitality_claim(
        "The deposit is 500000 VND per room per stay and is unconditionally refundable. [F-HTL-CITY01-013]",
        CURRENT_FACTS,
    )
    refund_clause = [item for item in result.assertions if "refund" in item.text.casefold()]
    assert refund_clause
    assert all(item.status is not ClaimConsistencyStatus.VERIFIED for item in refund_clause)


@pytest.mark.parametrize(
    ("case", "claim", "expected_properties", "expected_false_rejection"),
    [
        ("positive_full_translation_vi", "Bãi đỗ xe có mái che, phí 100000 VND cho mỗi xe mỗi đêm. [F-HTL-CITY01-046] Bãi xe không bảo lưu chỗ. [F-HTL-CITY01-046]", {"parking.covered", "amount_currency_basis", "parking.reservation"}, 0),
        ("positive_negated", "Parking is not free and a space is not guaranteed. [F-HTL-CITY01-046]", {"fee.amount", "parking.reservation"}, 0),
        ("positive_covered_only", "Covered parking is available. [F-HTL-CITY01-046]", {"parking.covered"}, 0),
        ("positive_basis_reordered", "Parking costs 100000 VND per night per vehicle. [F-HTL-CITY01-046]", {"amount_currency_basis"}, 0),
        # The quoted question is not an assertive claim; only the supported
        # parking statement belongs in the positive-claim denominator.
        ("positive_question_quote", "You asked, “Is parking free?” The parking area is covered. [F-HTL-CITY01-046]", {"parking.covered"}, 0),
        ("positive_translation_outside_predicates", "屋根付き駐車場があります。 [F-HTL-CITY01-046]", {"parking.covered"}, 1),
        ("valid_helpful_negation", "Parking is not free. [F-HTL-CITY01-046] Parking costs 100000 VND per vehicle per night. [F-HTL-CITY01-046]", {"fee.amount", "amount_currency_basis"}, 0),
        ("valid_concise", "Parking is covered and costs 100000 VND per vehicle per night. [F-HTL-CITY01-046]", {"parking.covered", "amount_currency_basis"}, 0),
        ("valid_deposit_condition", "The deposit is 500000 VND per room per stay and is refundable after reconciliation after checkout. [F-HTL-CITY01-013]", {"amount_currency_basis", "refund_after_reconciliation"}, 0),
    ],
)
def test_valid_answer_quality_counts_false_rejection_per_supported_property(
    case, claim, expected_properties, expected_false_rejection,
) -> None:
    result = validate_hospitality_claim(claim, CURRENT_FACTS)
    by_span = {}
    for item in result.assertions:
        by_span.setdefault(item.text, []).append(item)
    false_rejections = 0
    for property_name in expected_properties:
        matches = [item for item in result.assertions if item.property_name == property_name]
        if not matches:
            false_rejections += 1
            continue
        any_verified = any(item.status is ClaimConsistencyStatus.VERIFIED for item in matches)
        fully_verified = any(
            all(peer.status is ClaimConsistencyStatus.VERIFIED for peer in by_span[item.text])
            for item in matches if item.status is ClaimConsistencyStatus.VERIFIED
        )
        false_rejections += int(not fully_verified)
        assert any_verified or expected_false_rejection > 0, (case, property_name, result.assertions)
    assert false_rejections == expected_false_rejection, case
