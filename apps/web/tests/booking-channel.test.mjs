import assert from "node:assert/strict";
import test from "node:test";

import { safeBookingDestination } from "../src/domains/hospitality/registration/booking-channel.ts";
import { assistantOutageCopy, isAssistantOutage } from "../src/shared/chat/assistant-outage.ts";

test("accepts a clean HTTPS booking destination, including synthetic demo URLs", () => {
  assert.equal(
    safeBookingDestination("https://booking.example/hotels/harbor-city-demo"),
    "https://booking.example/hotels/harbor-city-demo",
  );
});

test("rejects unsafe protocols, credentials, query parameters, fragments, and malformed URLs", () => {
  for (const value of [
    "http://booking.example/hotel",
    "javascript:alert(1)",
    "https://user:pass@booking.example/hotel",
    "https://booking.example/hotel?guest=person@example.test",
    "https://booking.example/hotel#transcript",
    "//booking.example/hotel",
    "not a URL",
  ]) assert.equal(safeBookingDestination(value), undefined, value);
});

test("assistant outage notice uses reviewed locale copy and discloses English fallback", () => {
  assert.match(assistantOutageCopy("ar-EG").message, /إجابة كاملة/u);
  assert.equal(assistantOutageCopy("ar-EG").fallbackVisible, false);
  assert.match(assistantOutageCopy("fr-CA").message, /réponse complète/u);
  assert.equal(assistantOutageCopy("ko").language, "en");
  assert.equal(assistantOutageCopy("ko").fallbackVisible, true);
});

test("only transport and provider outage failures receive the supplemental notice", () => {
  for (const code of ["provider_timeout", "provider_failure", "api_proxy_timeout", "network_outcome_unknown"]) {
    assert.equal(isAssistantOutage({ code, status: 504 }), true);
  }
  assert.equal(isAssistantOutage({ code: "invalid_session", status: 401 }), false);
  assert.equal(isAssistantOutage(new Error("offline")), false);
});
