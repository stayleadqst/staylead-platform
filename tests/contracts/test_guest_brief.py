from __future__ import annotations

from uuid import UUID

from staylead_platform.domains.hospitality.schemas.guest_brief import (
    validate_guest_brief_proposal,
)
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefProposal,
    GuestBriefSnapshot,
)


def test_explicit_dates_and_checkout_only_correction_reuse_checkin() -> None:
    empty = GuestBriefSnapshot(0, {
        "dates": {"check_in": None, "check_out": None, "nights": None},
        "party": {"adults": None, "children": []},
    })
    initial = validate_guest_brief_proposal(empty, GuestBriefProposal(({
        "op": "set_dates", "check_in": "2027-05-10", "check_out": "2027-05-13",
    },)))
    assert initial.data["dates"] == {
        "check_in": "2027-05-10", "check_out": "2027-05-13", "nights": 3,
    }
    corrected = validate_guest_brief_proposal(
        GuestBriefSnapshot(1, initial.data, initial.pending_fields),
        GuestBriefProposal(({"op": "set_dates", "check_out": "2027-05-15"},)),
    )
    assert corrected.data["dates"] == {
        "check_in": "2027-05-10", "check_out": "2027-05-15", "nights": 5,
    }
    assert corrected.applied_delta["dates"] == {"check_out": "2027-05-15", "nights": 5}
    assert corrected.source_fields == ("dates.check_out",)


def test_missing_child_age_persists_stable_member_and_pending_field() -> None:
    base = GuestBriefSnapshot(1, {
        "dates": {"check_in": "2027-05-10", "check_out": "2027-05-13", "nights": 3},
        "party": {"adults": 2, "children": []},
    })
    result = validate_guest_brief_proposal(base, GuestBriefProposal(({"op": "add_child", "age": None},)))
    child = result.data["party"]["children"][0]
    UUID(child["member_id"])
    assert child["age"] is None
    assert result.status == "partial_success"
    assert result.pending_fields == (f"party.children.{child['member_id']}.age",)
    assert result.data["dates"] == base.data["dates"]
    assert result.data["party"]["adults"] == 2


def test_ambiguous_dates_preserve_confirmed_values_and_negation_is_noop() -> None:
    base = GuestBriefSnapshot(4, {
        "dates": {"check_in": "2027-05-10", "check_out": "2027-05-13", "nights": 3},
        "party": {"adults": 2, "children": []},
    })
    ambiguous = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "clarify", "field": "dates.check_out", "reason": "Relative date needs clarification.",
    },)))
    assert ambiguous.data == base.data
    assert ambiguous.pending_fields == ("dates.check_out",)
    assert ambiguous.status == "clarification"
    negated = validate_guest_brief_proposal(base, GuestBriefProposal(()))
    assert negated.data == base.data
    assert negated.pending_fields == base.pending_fields
    assert negated.status == "no_change"


def test_child_edit_requires_known_stable_member_id() -> None:
    base = GuestBriefSnapshot(1, {
        "dates": {"check_in": None, "check_out": None, "nights": None},
        "party": {"adults": 2, "children": []},
    })
    try:
        validate_guest_brief_proposal(base, GuestBriefProposal(({
            "op": "set_child_age", "member_id": "invented", "age": 8,
        },)))
    except ValueError as exc:
        assert "stable member ID" in str(exc)
    else:
        raise AssertionError("Unknown child references must be rejected.")


def test_resolved_adults_pending_is_cleared_without_clearing_other_pending() -> None:
    base = GuestBriefSnapshot(2, {
        "dates": {"check_in": None, "check_out": None, "nights": None},
        "party": {"adults": None, "children": []},
    }, ("dates.check_in", "party.adults"))
    result = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "set_adults", "count": 2,
    },)))
    assert result.data["party"]["adults"] == 2
    assert result.pending_fields == ("dates.check_in",)
    assert result.status == "applied"


def test_precise_child_age_and_removal_resolve_member_pending_only() -> None:
    member_id = "71fd84ef-0256-4ed1-9904-63137459fa93"
    base = GuestBriefSnapshot(2, {
        "dates": {"check_in": None, "check_out": None, "nights": None},
        "party": {"adults": 2, "children": [{"member_id": member_id, "age": None}]},
    }, ("dates.check_out", "party.children.member", f"party.children.{member_id}.age"))
    age = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "set_child_age", "member_id": member_id, "age": 7,
    },)))
    assert age.pending_fields == ("dates.check_out",)
    assert age.data["party"]["children"][0]["age"] == 7

    removal = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "remove_child", "member_id": member_id,
    },)))
    assert removal.pending_fields == ("dates.check_out",)
    assert removal.data["party"]["children"] == []


def test_partial_date_capture_persists_either_endpoint_across_turns() -> None:
    empty = GuestBriefSnapshot(0, {
        "dates": {"check_in": None, "check_out": None, "nights": None},
        "party": {"adults": None, "children": []},
    })
    check_in = validate_guest_brief_proposal(empty, GuestBriefProposal(({
        "op": "set_dates", "check_in": "2027-05-10",
    },)))
    assert check_in.data["dates"] == {
        "check_in": "2027-05-10", "check_out": None, "nights": None,
    }
    assert check_in.pending_fields == ("dates.check_out",)
    assert check_in.applied_delta["dates"] == {"check_in": "2027-05-10"}
    assert check_in.status == "partial_success"

    complete = validate_guest_brief_proposal(
        GuestBriefSnapshot(1, check_in.data, check_in.pending_fields),
        GuestBriefProposal(({"op": "set_dates", "check_out": "2027-05-13"},)),
    )
    assert complete.data["dates"] == {
        "check_in": "2027-05-10", "check_out": "2027-05-13", "nights": 3,
    }
    assert complete.pending_fields == ()
    assert complete.applied_delta["dates"] == {"check_out": "2027-05-13", "nights": 3}

    check_out_first = validate_guest_brief_proposal(empty, GuestBriefProposal(({
        "op": "set_dates", "check_out": "2027-05-13",
    },)))
    assert check_out_first.data["dates"] == {
        "check_in": None, "check_out": "2027-05-13", "nights": None,
    }
    assert check_out_first.pending_fields == ("dates.check_in",)


def test_conflicting_explicit_date_preserves_confirmed_endpoint_and_marks_only_disputed() -> None:
    base = GuestBriefSnapshot(3, {
        "dates": {"check_in": "2027-05-10", "check_out": "2027-05-13", "nights": 3},
        "party": {"adults": 2, "children": []},
    })
    result = validate_guest_brief_proposal(base, GuestBriefProposal(({
        "op": "set_dates", "check_in": "2027-05-15",
    },)))
    assert result.data["dates"] == base.data["dates"]
    assert result.pending_fields == ("dates.check_in",)
    assert result.applied_delta == {}
    assert result.status == "clarification"
