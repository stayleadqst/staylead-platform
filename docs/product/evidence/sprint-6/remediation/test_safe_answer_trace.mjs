import assert from "node:assert/strict";
import test from "node:test";
import { safeAnswerTrace } from "./safe-answer-trace.mjs";

test("safe trace retains only the backend validation classification and rejection count", () => {
  assert.deepEqual(safeAnswerTrace({
    answer_validation: "safe_portion",
    guest_claims_rejected: 2,
    rejected_claims: ["private guest text"],
    raw_output: "private model body",
  }), { answer_validation: "safe_portion", guest_claims_rejected: 2 });
  assert.deepEqual(safeAnswerTrace({ answer_validation: "fully_validated", guest_claims_rejected: 0 }),
    { answer_validation: "fully_validated", guest_claims_rejected: 0 });
});

test("unknown trace values are omitted instead of copied into evidence", () => {
  assert.deepEqual(safeAnswerTrace({ answer_validation: "unexpected/private", guest_claims_rejected: -1, text: "secret" }),
    { answer_validation: null, guest_claims_rejected: null });
  assert.equal(safeAnswerTrace(null), null);
});
