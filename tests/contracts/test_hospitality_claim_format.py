from staylead_platform.domains.hospitality.grounded_claim_format import (
    format_grounded_claim,
)

TIMEZONE = "Asia/Ho_Chi_Minh"


def fact(*, value="Breakfast starts at 07:00", timezone=TIMEZONE, window=None):
    conditions = {}
    if timezone is not None:
        conditions["timezone"] = timezone
    if window is not None:
        conditions["window"] = window
    return {"fact_id": "F-DINING-HOURS", "value": value, "conditions": conditions}


def test_appends_timezone_from_a_matching_cited_fact_only():
    claim = "Breakfast starts at 07:00."
    assert format_grounded_claim(claim, [fact()]) == f"{claim} ({TIMEZONE})"
    assert format_grounded_claim(claim, []) == claim
    assert format_grounded_claim(claim, [fact(value="Breakfast starts at 08:00")]) == claim


def test_matches_a_cited_time_in_conditions_window():
    claim = "Dining is available until 21:00."
    source = fact(value="Dining hours", window="07:00-21:00")
    assert format_grounded_claim(claim, [source]) == f"{claim} ({TIMEZONE})"


def test_missing_invalid_or_ambiguous_timezone_leaves_claim_unchanged():
    claim = "Breakfast starts at 07:00."
    assert format_grounded_claim(claim, [fact(timezone=None)]) == claim
    assert format_grounded_claim(claim, [fact(timezone="Not/A_Real_Zone")]) == claim
    assert format_grounded_claim(claim, [fact(), fact(timezone="Asia/Tokyo")]) == claim


def test_every_claim_time_needs_its_own_consistent_valid_cited_timezone():
    claim = "Breakfast 07:00; pool 08:00."
    breakfast = fact(value="Breakfast starts 07:00")
    pool_without_timezone = fact(value="Pool opens 08:00", timezone=None)
    pool_with_invalid_timezone = fact(value="Pool opens 08:00", timezone="Not/A_Real_Zone")
    assert format_grounded_claim(claim, [breakfast, pool_without_timezone]) == claim
    assert format_grounded_claim(claim, [breakfast, pool_with_invalid_timezone]) == claim
    assert format_grounded_claim(claim, [breakfast, fact(value="Pool opens 08:00")]) == f"{claim} ({TIMEZONE})"
    assert format_grounded_claim(claim, [breakfast, fact(value="Pool opens 08:00", timezone="Asia/Tokyo")]) == claim
    assert format_grounded_claim("Breakfast 07:00.", [breakfast, pool_without_timezone]) == f"Breakfast 07:00. ({TIMEZONE})"


def test_unrelated_claim_time_and_url_clock_are_not_modified():
    assert format_grounded_claim("Breakfast is included.", [fact()]) == "Breakfast is included."
    assert format_grounded_claim("The pool opens at 08:00.", [fact()]) == "The pool opens at 08:00."
    claim = "See https://hotel.example/open?at=07:00 for details."
    assert format_grounded_claim(claim, [fact()]) == claim
    claim_with_time_and_url = "Breakfast starts 07:00; details at https://hotel.example/open?at=07:00."
    assert format_grounded_claim(claim_with_time_and_url, [fact()]) == f"{claim_with_time_and_url} ({TIMEZONE})"


def test_preserves_unicode_clock_text_and_avoids_duplicate_timezone():
    claim = "早餐于０７:００开始；网址 https://hotel.example/07:00"
    expected = f"{claim} ({TIMEZONE})"
    assert format_grounded_claim(claim, [fact()]) == expected
    assert format_grounded_claim(f"{claim} ({TIMEZONE})", [fact()]) == f"{claim} ({TIMEZONE})"
