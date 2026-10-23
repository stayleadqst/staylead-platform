import assert from "node:assert/strict";
import test from "node:test";

import {
  canStartRequest,
  claimRequest,
  classifyFailure,
  classifySessionFailure,
  hasUnresolvedRequest,
  isCurrentGeneration,
  releaseRequest,
  retryModeForFailure,
} from "../src/shared/chat/chat-state.ts";

test("ambiguous network outcomes and pending requests keep their request ID", () => {
  assert.equal(classifyFailure({ outcome: "unknown" }).retryMode, "same-request");
  assert.equal(classifyFailure({ code: "request_in_progress", outcome: "rejected" }).retryMode, "same-request");
});

test("a confirmed terminal request failure offers a new request only on explicit retry", () => {
  assert.equal(classifyFailure({ code: "request_failed", outcome: "rejected" }).retryMode, "new-request");
});

test("stale sources require a guest initiated turn and never auto-retry", () => {
  const stale = classifyFailure({ code: "stale_source", outcome: "rejected" });
  assert.equal(stale.retryMode, "none");
  assert.match(stale.message, /latest records/);
});

test("retryable errors require same-ID verification until the server confirms terminal failure", () => {
  for (const code of ["provider_timeout", "provider_rate_limited", "provider_failure",
    "storage_unavailable", "freshness_unavailable", "brief_apply_outcome_unknown"]) {
    const result = classifyFailure({ code, outcome: "rejected", retryable: true });
    assert.equal(result.retryMode, "same-request", `${code} must first check the original request`);
    assert.match(result.message, /same request/);
  }
  assert.equal(classifyFailure({ code: "brief_apply_no_effect", retryable: true }).retryMode, "new-request");
  assert.equal(classifyFailure({ code: "request_failed" }).retryMode, "new-request");
  assert.equal(
    classifyFailure({ code: "request_in_progress", outcome: "rejected", retryable: true }).retryMode,
    "same-request",
  );
  for (const code of ["storage_unavailable", "freshness_unavailable"]) {
    assert.equal(classifyFailure({ code, outcome: "rejected", retryable: true }).retryMode, "same-request");
  }
});

test("a committed partial result never offers resubmitting the original edit under a new ID", () => {
  const originalEditFailure = classifyFailure({ code: "provider_failure", outcome: "rejected", retryable: true });
  assert.equal(originalEditFailure.retryMode, "same-request");
  assert.equal(retryModeForFailure(originalEditFailure.retryMode, true), undefined);
  assert.equal(retryModeForFailure("same-request", true), undefined);
  assert.equal(retryModeForFailure("new-request", false), "new-request");
});

test("uncertain brief-apply completion stays on the same request until scoped recovery resolves it", () => {
  const uncertain = classifyFailure({ code: "brief_apply_outcome_unknown", outcome: "rejected", retryable: true });
  assert.equal(uncertain.retryMode, "same-request");
  assert.match(uncertain.message, /same request/);
  const confirmedNoEffect = classifyFailure({ code: "brief_apply_no_effect", outcome: "rejected", retryable: true });
  assert.equal(confirmedNoEffect.retryMode, "new-request");
});

test("an unresolved same-ID retry blocks the composer until resolved or a new chat starts", () => {
  const pendingTurn = { retryMode: classifyFailure({ outcome: "unknown" }).retryMode };
  assert.equal(hasUnresolvedRequest([pendingTurn]), true);
  assert.equal(canStartRequest(true, false, hasUnresolvedRequest([pendingTurn])), false);
  assert.equal(claimRequest(5, { current: null }), true); // explicit retry remains available

  const terminalTurn = { retryMode: classifyFailure({ code: "request_failed", outcome: "rejected" }).retryMode };
  assert.equal(hasUnresolvedRequest([terminalTurn]), false);
  assert.equal(canStartRequest(true, false, hasUnresolvedRequest([terminalTurn])), true);
});

test("a contract mismatch has a clear deterministic error and no transient retry", () => {
  const mismatch = classifySessionFailure({ code: "contract_mismatch", outcome: "rejected" });
  assert.equal(mismatch.retryable, false);
  assert.match(mismatch.message, /incompatible versions/);
  const network = classifySessionFailure({ outcome: "unknown" });
  assert.equal(network.retryable, true);
});

test("an unknown hotel link explains that the hotel has not been registered", () => {
  const failure = classifySessionFailure({ code: "hotel_unavailable", outcome: "rejected" });
  assert.equal(failure.retryable, false);
  assert.match(failure.message, /hotel is not available/);
});

test("provider authentication failure does not trigger guest session renewal", () => {
  const result = classifyFailure({ code: "provider_auth", outcome: "rejected", retryable: false });
  assert.equal(result.retryMode, "none");
  assert.match(result.message, /temporarily unavailable/);
});

test("an expired guest session asks for an explicit new session", () => {
  assert.equal(classifyFailure({ code: "invalid_session", outcome: "rejected" }).retryMode, "new-session");
});

test("the request lock rejects a second in-flight send and releases on completion", () => {
  const lock = { current: null };
  assert.equal(claimRequest(3, lock), true);
  assert.equal(claimRequest(3, lock), false);
  releaseRequest(3, lock);
  assert.equal(claimRequest(3, lock), true);
});

test("hotel changes reject late session creation responses", () => {
  let generation = 3;
  let currentSession = { hotel: "city" };
  const lateCitySession = { hotel: "city" };
  generation = 4;
  currentSession = { hotel: "beach" };
  if (isCurrentGeneration(3, generation)) currentSession = lateCitySession;
  assert.deepEqual(currentSession, { hotel: "beach" });
});

test("requests require a session and stale response generations are rejected", () => {
  assert.equal(canStartRequest(true, false), true);
  assert.equal(canStartRequest(true, true), false);
  assert.equal(canStartRequest(false, false), false);
  assert.equal(isCurrentGeneration(3, 3), true);
  assert.equal(isCurrentGeneration(2, 3), false);
});
