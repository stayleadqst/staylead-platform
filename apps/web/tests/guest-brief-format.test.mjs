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
