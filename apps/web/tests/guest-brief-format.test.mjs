import assert from "node:assert/strict";
import test from "node:test";

import { formatHospitalityBriefDelta } from "../src/domains/hospitality/registration/brief-format.ts";

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
