import assert from "node:assert/strict";
import test from "node:test";
import { shouldOfferOperatorResume } from "./operator-resume-routing.mjs";

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
