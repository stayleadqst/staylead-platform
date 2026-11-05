import assert from "node:assert/strict";
import test from "node:test";

import { formatHospitalityBriefConfirmationChanges, formatHospitalityBriefDelta } from "../src/domains/hospitality/registration/brief-format.ts";

test("checkout-only receipt reports only changed fields and never implies a missing check-in", () => {
  const summary = formatHospitalityBriefDelta({
    dates: { check_out: "2026-12-14", nights: 4 },
  });

  assert.equal(summary, "Check-out changed to 2026-12-14. Stay length is 4 nights.");
  assert.doesNotMatch(summary, /check-in|not set/i);
});

test("receipt date wording includes both dates only when both were changed", () => {
  const summary = formatHospitalityBriefDelta({
    dates: { check_in: "2026-12-10", check_out: "2026-12-14", nights: 4 },
  });

  assert.equal(summary, "Check-in changed to 2026-12-10. Check-out changed to 2026-12-14. Stay length is 4 nights.");
});

test("applied room delta reports view clearing and changed budget fields only", () => {
  const summary = formatHospitalityBriefDelta({
    room_requirements: {
      preferred_views: null,
      budget_amount: 5000000,
      budget_currency: "VND",
      budget_basis: "stay_total",
      budget_strength: "hard",
      budget_inclusions: ["breakfast", "taxes"],
      hard_accessibility_needs: ["step-free entry"],
    },
  });

  assert.equal(
    summary,
    "View preferences: Not set. Room budget amount: 5000000. Room budget currency: VND. "
      + "Room budget basis: stay_total. Room budget requirement: hard. Included in room budget: "
      + "breakfast, taxes. Required room accessibility: step-free entry.",
  );
  assert.doesNotMatch(summary, /preferred_views|budget_basis|budget_inclusions/);
});

test("applied room delta preserves the explicit preferred view value", () => {
  assert.equal(
    formatHospitalityBriefDelta({ room_requirements: { preferred_views: ["city view"] } }),
    "View preferences: city view.",
  );
});

test("applied room delta reports every supported room requirement with exact values", () => {
  const summary = formatHospitalityBriefDelta({
    room_requirements: {
      preferred_views: ["city view"],
      budget_amount: 5000000,
      budget_currency: "VND",
      budget_basis: "stay_total",
      budget_strength: "target",
      budget_inclusions: ["breakfast"],
      sharing: "prefer",
      hard_accessibility_needs: ["step_free"],
      preferred_accessibility_needs: ["near_lift"],
      hard_bed_types: ["king"],
      preferred_bed_types: ["twin"],
      avoided_bed_types: ["bunk"],
      max_rooms: 2,
    },
  });

  assert.equal(
    summary,
    "View preferences: city view. Room budget amount: 5000000. Room budget currency: VND. "
      + "Room budget basis: stay_total. Room budget requirement: target. "
      + "Included in room budget: breakfast. Bed-sharing preference: prefer. "
      + "Required room accessibility: step_free. Preferred room accessibility: near_lift. "
      + "Required bed types: king. Preferred bed types: twin. Bed types to avoid: bunk. "
      + "Maximum rooms: 2.",
  );
  assert.doesNotMatch(summary, /preferred_views|hard_bed_types|preferred_bed_types|max_rooms/);
});

test("confirmation review formats nested room and guide changes into readable field rows", () => {
  const rows = formatHospitalityBriefConfirmationChanges([{
    field: "local_guide_preferences",
    before_present: false,
    before: null,
    after_present: true,
    after: {
      allergy_requirements: ["peanut"],
      hard_accessibility_needs: ["step_free"],
      budget_amount: 100000,
      budget_currency: "VND",
    },
  }, {
    field: "room_requirements",
    before_present: true,
    before: { hard_accessibility_needs: ["step-free entry"] },
    after_present: true,
    after: {},
  }]);

  assert.deepEqual(rows, [
    { field: "Allergy requirements", before: "Not set", after: "peanut" },
    { field: "Budget amount", before: "Not set", after: "100000" },
    { field: "Budget currency", before: "Not set", after: "VND" },
    { field: "Required venue accessibility", before: "Not set", after: "step_free" },
    { field: "Required room accessibility", before: "step-free entry", after: "Not set" },
  ]);
  assert.equal(JSON.stringify(rows).includes("member_id"), false);
});
