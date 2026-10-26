import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import {
  canAdvanceAfterKnownPartial,
  matchesRuntimeReceiptRequest,
  shouldOfferOperatorResume,
} from "./operator-resume-routing.mjs";

test("generic HTTP 503 does not route to answer-only continuation", () => {
  assert.equal(shouldOfferOperatorResume({
    responseReceived: true,
    httpStatus: 503,
    apiStatus: null,
    receiptId: null,
  }), false);
});

test("HTTP 502 partial response with a raw in-memory receipt routes to explicit continuation", () => {
  assert.equal(shouldOfferOperatorResume({
    responseReceived: true,
    httpStatus: 502,
    apiStatus: "partial_success",
    receiptId: "receipt-only-in-memory",
  }), true);
});

test("partial status without a receipt or without an HTTP response is not resumable", () => {
  assert.equal(shouldOfferOperatorResume({
    responseReceived: true,
    httpStatus: 502,
    apiStatus: "partial_success",
    receiptId: null,
  }), false);
  assert.equal(shouldOfferOperatorResume({
    responseReceived: false,
    httpStatus: 0,
    apiStatus: "partial_success",
    receiptId: "receipt-only-in-memory",
  }), false);
});

test("completed responses and overlong receipt values are not routed", () => {
  assert.equal(shouldOfferOperatorResume({
    responseReceived: true,
    httpStatus: 200,
    apiStatus: "completed",
    receiptId: "receipt",
  }), false);
  assert.equal(shouldOfferOperatorResume({
    responseReceived: true,
    httpStatus: 502,
    apiStatus: "partial_success",
    receiptId: "x".repeat(513),
  }), false);
});

test("explicit next may record a known persisted partial as failed without sending a request", () => {
  const requestHash = createHash("sha256").update("current-turn-request-id").digest("hex").slice(0, 16);
  const runtimeEvents = [
    { stage: "provider_call_started", guest_turn: 2, turn_request_id_sha256: requestHash },
    { stage: "provider_call_completed", guest_turn: 2, turn_request_id_sha256: requestHash },
  ];
  assert.equal(matchesRuntimeReceiptRequest({
    receiptIdHash: requestHash, runtimeEvents, turn: 2,
  }), true);
  assert.equal(canAdvanceAfterKnownPartial({
    responseReceived: true,
    httpStatus: 502,
    apiStatus: "partial_success",
    receiptStatus: "partial_success",
    receiptId: "receipt-only-in-memory",
    receiptMatchesRuntimeRequest: matchesRuntimeReceiptRequest({
      receiptIdHash: requestHash, runtimeEvents, turn: 2,
    }),
    persistedState: {
      run_id: "s6-codex-20261026-remediation-7",
      authorized_for_live_calls: true,
      guest_turns: 2,
      max_guest_turns: 9,
      codex_requests: 4,
      max_codex_requests: 18,
      max_calls_per_turn: 2,
    },
    expectedRunId: "s6-codex-20261026-remediation-7",
    turn: 2,
    nextPinnedTurnAvailable: true,
  }), true);
});

test("next cannot skip unknown, unpersisted, stale-state, or final-turn outcomes", () => {
  const valid = {
    responseReceived: true, httpStatus: 502, apiStatus: "partial_success",
    receiptStatus: "partial_success", receiptId: "receipt", receiptIdHash: "0123456789abcdef",
    receiptMatchesRuntimeRequest: true,
    persistedState: {
      run_id: "s6-codex-20261026-remediation-7", authorized_for_live_calls: true,
      guest_turns: 2, max_guest_turns: 9, codex_requests: 4,
      max_codex_requests: 18, max_calls_per_turn: 2,
    },
    expectedRunId: "s6-codex-20261026-remediation-7", turn: 2, nextPinnedTurnAvailable: true,
  };
  for (const patch of [
    { apiStatus: "unknown_error" },
    { receiptStatus: "failed" },
    { receiptId: null },
    { receiptMatchesRuntimeRequest: false },
    { responseReceived: false },
    { httpStatus: 0 },
    { persistedState: { ...valid.persistedState, run_id: "other-run" } },
    { persistedState: { ...valid.persistedState, guest_turns: 1 } },
    { persistedState: { ...valid.persistedState, codex_requests: 18 } },
    { nextPinnedTurnAvailable: false },
  ]) {
    assert.equal(canAdvanceAfterKnownPartial({ ...valid, ...patch }), false);
  }
});

test("receipt fingerprint must uniquely match a persisted provider request in this turn", () => {
  const currentHash = createHash("sha256").update("current-turn-request-id").digest("hex").slice(0, 16);
  const wrongHash = createHash("sha256").update("different-request-id").digest("hex").slice(0, 16);
  assert.equal(matchesRuntimeReceiptRequest({
    receiptIdHash: currentHash,
    runtimeEvents: [{ stage: "provider_call_started", guest_turn: 2, turn_request_id_sha256: wrongHash }],
    turn: 2,
  }), false);
  assert.equal(matchesRuntimeReceiptRequest({
    receiptIdHash: currentHash,
    runtimeEvents: [
      { stage: "provider_call_started", guest_turn: 2, turn_request_id_sha256: currentHash },
      { stage: "provider_call_started", guest_turn: 2, turn_request_id_sha256: wrongHash },
    ],
    turn: 2,
  }), false);
  assert.equal(matchesRuntimeReceiptRequest({
    receiptIdHash: currentHash,
    runtimeEvents: [{ stage: "provider_call_started", guest_turn: 1, turn_request_id_sha256: currentHash }],
    turn: 2,
  }), false);
});
