"""Focused product tests for B15 source-property/claim consistency."""

import json
from pathlib import Path

from staylead_platform.domains.hospitality.claim_consistency import validate_hospitality_claim
from staylead_platform.platform.contracts.claim_consistency import ClaimConsistencyStatus as Status


def facts():
    path = Path(__file__).parents[2] / "fixtures/hospitality/knowledge-v1/facts.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    return {
        "parking": next(record for record in records if record.get("hotel_id") == "HTL-CITY01" and record.get("field") == "parking"),
        "deposit": next(record for record in records if record.get("hotel_id") == "HTL-CITY01" and record.get("field") == "deposit"),
    }


def statuses(text: str, *, topic: str = "parking"):
    fact = facts()[topic]
    result = validate_hospitality_claim(f"{text} [{fact['fact_id']}]", [fact])
    return result.assertions


def test_f046_free_and_reservation_contradictions_are_property_bound() -> None:
    result = statuses("Parking is free and a space is guaranteed.")
    assert [item.status for item in result] == [Status.CONTRADICTED, Status.CONTRADICTED]
    assert {item.property_name for item in result} == {"fee.amount", "parking.reservation"}


def test_fee_negation_is_scoped_to_each_assertion() -> None:
    result = statuses("Parking is not free. Parking is free.")
    assert [item.status for item in result] == [Status.VERIFIED, Status.CONTRADICTED]


def test_covered_parking_is_verified_but_underground_is_unknown() -> None:
    assert statuses("Covered parking is available.")[0].status == Status.VERIFIED
    assert statuses("Parking is not covered.")[0].status == Status.CONTRADICTED
    assert statuses("Parking is underground.")[0].status == Status.UNKNOWN


def test_full_span_requires_every_factual_clause_to_be_covered() -> None:
    guarded = statuses("Parking is covered, guarded by licensed staff.")
    assert [item.status for item in guarded] == [Status.VERIFIED, Status.UNKNOWN]

    other_subject = statuses("Parking is covered and the swimming pool is covered.")
    assert [item.status for item in other_subject] == [Status.VERIFIED, Status.UNKNOWN]
    assert other_subject[1].subject == "other:swimming pool"


def test_money_binds_every_occurrence_currency_and_all_basis_dimensions() -> None:
    wrong_basis = statuses("Parking costs 100000 VND per vehicle per stay.")
    assert wrong_basis[0].status == Status.CONTRADICTED
    assert wrong_basis[0].reason == "basis_dimension_mismatch"

    wrong_currency = statuses("Parking costs 100000 USD per vehicle per night.")
    assert wrong_currency[0].status == Status.CONTRADICTED
    assert wrong_currency[0].reason == "amount_or_currency_mismatch"

    multiple = statuses("Parking costs 100000 VND per vehicle per night, or 100000 USD.")
    assert any(item.status == Status.VERIFIED and item.property_name == "amount_currency_basis" for item in multiple)
    assert any(item.status == Status.CONTRADICTED and item.reason == "amount_or_currency_mismatch" for item in multiple)
    assert not all(item.status == Status.VERIFIED for item in multiple)


def test_money_with_matching_value_but_wrong_subject_or_fact_is_not_verified() -> None:
    wrong_subject = statuses("Parking costs 500000 VND per room per stay.")
    assert wrong_subject[0].status == Status.CONTRADICTED

    wrong_fact = facts()["deposit"]
    result = validate_hospitality_claim(
        f"Parking costs 500000 VND per room per stay. [{wrong_fact['fact_id']}]", [wrong_fact],
    )
    assert result.assertions[0].status == Status.UNKNOWN
    assert result.assertions[0].reason == "property_fact_not_cited"


def test_question_quote_and_em_dash_do_not_mask_sibling_assertions() -> None:
    quoted_question = statuses('You asked “Is parking free?” Parking is free.')
    assert any(item.status == Status.CONTRADICTED for item in quoted_question)

    dash_question = statuses("Parking is free — any questions?")
    assert dash_question[0].status == Status.CONTRADICTED
    assert dash_question[-1].assertive is False

    question_only = statuses('“Is parking free?”')
    assert question_only and all(not item.assertive for item in question_only)


def test_unknown_source_parse_is_not_promoted_by_matching_answer_keywords() -> None:
    fact = dict(facts()["parking"])
    fact["conditions"] = {"unit": ""}
    result = validate_hospitality_claim(f"Covered parking is available. [{fact['fact_id']}]", [fact])
    assert result.assertions[0].status == Status.UNKNOWN
    assert result.assertions[0].reason == "source_property_parse_unknown"


def test_existing_typed_deposit_amount_uses_its_own_basis() -> None:
    correct = statuses("The deposit is 500000 VND per room per stay.", topic="deposit")
    assert correct[0].status == Status.VERIFIED
    wrong = statuses("The deposit is 600000 VND per room per stay.", topic="deposit")
    assert wrong[0].status == Status.CONTRADICTED


def test_deposit_condition_is_checked_as_a_separate_property() -> None:
    correct = statuses(
        "The deposit is 500000 VND per room per stay and is refundable after reconciliation after checkout.",
        topic="deposit",
    )
    assert any(item.status == Status.VERIFIED and item.property_name == "amount_currency_basis" for item in correct)
    assert any(item.status == Status.VERIFIED and item.property_name == "refund_after_reconciliation" for item in correct)

    unconditional = statuses(
        "The deposit is 500000 VND per room per stay and is unconditionally refundable.", topic="deposit",
    )
    assert any(item.status == Status.CONTRADICTED and item.property_name == "refund_after_reconciliation" for item in unconditional)


def test_validated_fact_binding_does_not_require_inline_label() -> None:
    fact = facts()["parking"]
    result = validate_hospitality_claim("Covered parking is available.", [fact])
    assert any(item.status == Status.VERIFIED and item.property_name == "parking.covered" for item in result.assertions)
