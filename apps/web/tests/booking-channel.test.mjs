import assert from "node:assert/strict";
import test from "node:test";

import { safeBookingDestination } from "../src/domains/hospitality/registration/booking-channel.ts";

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
