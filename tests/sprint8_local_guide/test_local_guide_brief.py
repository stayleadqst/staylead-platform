from __future__ import annotations

import pytest

from staylead_platform.domains.hospitality.schemas.guest_brief import (
    HospitalityGuestBriefPatch,
    validate_guest_brief_proposal,
    validate_guest_patch_authorization,
)
from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefProposal,
    GuestBriefSnapshot,
)


def test_typed_local_guide_patch_keeps_venue_kind_and_preserves_unedited_hard_needs() -> None:
    current = GuestBriefSnapshot(brief_version=3, data={
        "dates": {"check_in": "2026-11-01", "check_out": "2026-11-03", "nights": 2},
        "party": {"adults": 2, "children": []},
        "local_guide_preferences": {"hard_accessibility_needs": ["step_free"], "allergy_requirements": ["peanut"]},
    })
    operation = {
        "op": "set_local_guide_preferences", "venue_kinds": ["dining"], "interests": ["quiet", "budget"],
        "budget_amount": 150000, "budget_currency": "VND", "budget_basis": "per_person",
        "budget_strength": "hard", "current_turn_quote": "Find quiet dining under 150000 VND per person",
    }
    typed = HospitalityGuestBriefPatch.model_validate({"ops": [operation]})
    proposal = GuestBriefProposal((typed.ops[0].model_dump(exclude={"current_turn_quote"}),))
    validate_guest_patch_authorization(proposal.operations, ({
        "operation_index": 0, "op": operation["op"],
        "target_fields": [
            "local_guide_preferences.venue_kinds", "local_guide_preferences.interests",
            "local_guide_preferences.budget_amount", "local_guide_preferences.budget_currency",
            "local_guide_preferences.budget_basis", "local_guide_preferences.budget_strength",
        ], "intent": "explicit_request", "current_turn_quote": operation["current_turn_quote"],
    },), operation["current_turn_quote"])
    result = validate_guest_brief_proposal(current, proposal)
    prefs = result.data["local_guide_preferences"]
    assert prefs["venue_kinds"] == ["dining"]
    assert prefs["hard_accessibility_needs"] == ["step_free"]
    assert prefs["allergy_requirements"] == ["peanut"]
    assert result.applied_delta["local_guide_preferences"]["venue_kinds"] == ["dining"]


def test_local_guide_patch_rejects_unknown_categories_and_incomplete_budget_units() -> None:
    with pytest.raises(ValueError):
        HospitalityGuestBriefPatch.model_validate({"ops": [{
            "op": "set_local_guide_preferences", "venue_kinds": ["hotel"],
        }]})
    with pytest.raises(ValueError):
        HospitalityGuestBriefPatch.model_validate({"ops": [{
            "op": "set_local_guide_preferences", "budget_amount": 150000,
        }]})


def test_local_guide_clear_only_patch_preserves_other_fields() -> None:
    current = GuestBriefSnapshot(1, {"dates": {}, "party": {"children": []}, "local_guide_preferences": {
        "interests": ["culture"], "hard_accessibility_needs": ["step_free"],
    }})
    result = validate_guest_brief_proposal(current, GuestBriefProposal(({
        "op": "set_local_guide_preferences", "clear_fields": ["interests"],
    },)))
    assert result.data["local_guide_preferences"] == {"hard_accessibility_needs": ["step_free"]}
    assert result.applied_delta["local_guide_preferences"] == {"interests": None}
