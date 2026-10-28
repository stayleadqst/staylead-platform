import assert from "node:assert/strict";
import test from "node:test";

import { ApiError, checkGuestFreshness, confirmGuestBriefEdit, createGuestSession, fetchGuestMedia, getGuestHotel, sendGuestMessage } from "../src/shared/api/client.ts";

const target = {
  domain: "hospitality",
  guestContractVersion: "2",
  apiBasePath: "/api/guest",
};

test("session creation verifies real target metadata before sending hotel data", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return Response.json({ status: "ok", domain: "hospitality", guest_contract_version: "1" });
  };

  try {
    await assert.rejects(
      createGuestSession({ hotelSlug: "harbor-city-demo", target }),
      (error) => error instanceof ApiError && error.code === "contract_mismatch" && error.status === 409,
    );
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/api/guest/health");
    assert.equal(calls[0].init.method, undefined);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("direct hotel lookup is data-driven and unknown hotels surface the backend error", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return Response.json({ hotel_id: "HTL-FOUR", hotel_slug: "new-hotel", public_config: {},
      config_version: "1", guest_contract_version: "2" });
  };
  try {
    assert.equal((await getGuestHotel({ hotelSlug: "new-hotel", target })).hotel_id, "HTL-FOUR");
    assert.equal(calls[0].url, "/api/guest/hotels/new-hotel");
    globalThis.fetch = async () => Response.json({ error: { code: "hotel_unavailable", message: "This hotel is not available." } }, { status: 404 });
    await assert.rejects(getGuestHotel({ hotelSlug: "unknown", target }), (error) => error instanceof ApiError && error.status === 404);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("brief confirmation uses a separate scoped action request", async () => {
  const originalFetch = globalThis.fetch;
  let call;
  const response = { request_id: "confirm-1", status: "completed", answer: "Updated." };
  globalThis.fetch = async (url, init) => {
    call = { url, init };
    return Response.json(response);
  };
  try {
    assert.deepEqual(await confirmGuestBriefEdit({
      sessionId: "12345678-1234-4234-8234-123456789abc", accessToken: "guest-token",
      requestId: "confirm-1", confirmationToken: "signed-challenge", target,
    }), response);
    assert.equal(call.url, "/api/guest/sessions/12345678-1234-4234-8234-123456789abc/brief-confirmations");
    assert.equal(call.init.headers.authorization, "Bearer guest-token");
    assert.deepEqual(JSON.parse(call.init.body), { request_id: "confirm-1", confirmation_token: "signed-challenge" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("binary media fetch uses authenticated same-origin route and returns bytes as Blob", async () => {
  const originalFetch = globalThis.fetch;
  const bytes = new Uint8Array([0, 255, 13, 10, 1]);
  const media = { media_id: "IMG-1", source_id: "SRC-1", source_version: "2", source_hash: "a".repeat(64), source_generation: 7, sha256: "b".repeat(64) };
  let call;
  globalThis.fetch = async (url, init) => {
    call = { url, init };
    return new Response(bytes, { headers: { "content-type": "image/png", "cache-control": "no-store" } });
  };
  try {
    const blob = await fetchGuestMedia({ sessionId: "12345678-1234-4234-8234-123456789abc",
      media, accessToken: "guest-token", target, signal: new AbortController().signal });
    assert.equal(call.url, `/api/guest/sessions/12345678-1234-4234-8234-123456789abc/media/IMG-1?generation=7&source_id=SRC-1&source_version=2&source_hash=${"a".repeat(64)}&sha256=${"b".repeat(64)}`);
    assert.equal(call.init.headers.authorization, "Bearer guest-token");
    assert.equal(new URL(call.url, "https://local.test").searchParams.get("sha256"), media.sha256);
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("message client forwards bearer and preserves the API response shape", async () => {
  const originalFetch = globalThis.fetch;
  let call;
  const expected = {
    request_id: "turn-1",
    status: "completed",
    answer: "Breakfast is served.",
    evidence: [{ fact_id: "F-1", hotel_id: "H-1", source_id: "S-1", source_version: "1", source_hash: "a".repeat(64), source_generation: 1,
      section: "Dining", fact_version: "1.0", imported_at: "2026-10-22T00:00:00Z" }],
    media: [],
    unknowns: [],
    trace: {},
    config_version: "1",
    state_version: 1,
    source_generation: 1,
    language_preference: { language_tag: "zh-Hant", source: "explicit", revision: 3 },
    presentation: { language_tag: "zh-Hant", direction: "ltr", preference_revision: 3,
      labels: { send: "发送", copy: "复制" }, freshness: "current", receipt_id: "receipt-3" },
    answer_eligibility: "current",
  };
  globalThis.fetch = async (url, init) => {
    call = { url, init };
    return Response.json(expected);
  };

  try {
    assert.deepEqual(await sendGuestMessage({
      sessionId: "12345678-1234-4234-8234-123456789abc",
      accessToken: "guest-token",
      requestId: "turn-1",
      question: "When is breakfast?",
      target,
    }), expected);
    assert.equal(call.url, "/api/guest/sessions/12345678-1234-4234-8234-123456789abc/messages");
    assert.equal(call.init.headers.authorization, "Bearer guest-token");
    assert.deepEqual(JSON.parse(call.init.body), { request_id: "turn-1", question: "When is breakfast?" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("freshness check sends only the scoped evidence bindings", async () => {
  const originalFetch = globalThis.fetch;
  let call;
  globalThis.fetch = async (url, init) => {
    call = { url, init };
    return Response.json({ status: "stale" });
  };
  try {
    assert.deepEqual(await checkGuestFreshness({
      sessionId: "12345678-1234-4234-8234-123456789abc", accessToken: "guest-token", requestId: "turn-1", target,
    }), { status: "stale" });
    assert.equal(call.url, "/api/guest/sessions/12345678-1234-4234-8234-123456789abc/freshness");
    assert.equal(call.init.headers.authorization, "Bearer guest-token");
    assert.deepEqual(JSON.parse(call.init.body), { request_id: "turn-1" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("proxy gateway failures and lost responses are unknown outcomes", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ error: {
    code: "api_proxy_timeout", message: "The guest API did not respond in time.", retryable: true,
  } }, { status: 504 });
  try {
    await assert.rejects(
      sendGuestMessage({
        sessionId: "12345678-1234-4234-8234-123456789abc",
        accessToken: "guest-token", requestId: "turn-1", question: "When is breakfast?", target,
      }),
      (error) => error instanceof ApiError && error.outcome === "unknown" && error.code === "api_proxy_timeout",
    );

    globalThis.fetch = async () => { throw new TypeError("connection closed"); };
    await assert.rejects(
      sendGuestMessage({
        sessionId: "12345678-1234-4234-8234-123456789abc",
        accessToken: "guest-token", requestId: "turn-1", question: "When is breakfast?", target,
      }),
      (error) => error instanceof ApiError && error.outcome === "unknown" && error.code === "network_outcome_unknown",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("typed provider failures are known API rejections", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ error: {
    code: "provider_auth", message: "The provider is not configured.", retryable: false,
  } }, { status: 401 });
  try {
    await assert.rejects(
      sendGuestMessage({
        sessionId: "12345678-1234-4234-8234-123456789abc",
        accessToken: "guest-token", requestId: "turn-1", question: "When is breakfast?", target,
      }),
      (error) => error instanceof ApiError && error.outcome === "rejected" && error.code === "provider_auth",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("answer-only resume sends the applied receipt reference without replaying the guest edit", async () => {
  const originalFetch = globalThis.fetch;
  let call;
  globalThis.fetch = async (url, init) => {
    call = { url, init };
    return Response.json({ request_id: "resume-1", status: "completed", answer: "Breakfast is served." });
  };
  try {
    await sendGuestMessage({
      sessionId: "12345678-1234-4234-8234-123456789abc",
      accessToken: "guest-token", requestId: "resume-1", answerOnlyReceiptId: "original-1", target,
    });
    assert.deepEqual(JSON.parse(call.init.body), { request_id: "resume-1", answer_only_receipt_id: "original-1" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("partial-success errors preserve the committed receipt for explicit answer resume", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({
    request_id: "turn-1", status: "partial_success",
    error: { code: "provider_timeout", message: "answer failed" },
    guest_brief: { brief_version: 1, dates: {}, party: {}, pending_fields: [] },
    brief_receipt: { request_id: "turn-1", status: "partial_success", brief_version_before: 0,
      brief_version_after: 1, applied_delta: {}, source_refs: [], answer_status: "failed", brief_version_used: 1 },
    applied_delta: {}, answer_status: "failed",
  }, { status: 502 });
  try {
    await assert.rejects(
      sendGuestMessage({ sessionId: "12345678-1234-4234-8234-123456789abc", accessToken: "guest-token",
        requestId: "turn-1", question: "Add a child and ask about breakfast", target }),
      (error) => error instanceof ApiError && error.partialResult?.status === "partial_success"
        && error.partialResult.brief_receipt.request_id === "turn-1",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
