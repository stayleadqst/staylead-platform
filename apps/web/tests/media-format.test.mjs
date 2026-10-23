import assert from "node:assert/strict";
import test from "node:test";

import { formatMediaTime } from "../src/shared/chat/media-format.ts";

test("clip references retain fractional seconds and exact minute boundaries", () => {
  assert.equal(formatMediaTime(0.5), "0:00.5");
  assert.equal(formatMediaTime(2.5), "0:02.5");
  assert.equal(formatMediaTime(65.25), "1:05.25");
  assert.equal(formatMediaTime(60), "1:00");
});
