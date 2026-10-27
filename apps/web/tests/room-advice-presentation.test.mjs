import test from "node:test";
import assert from "node:assert/strict";
import { roomAdviceCostView } from "../src/domains/hospitality/registration/room-advice-cost.ts";
import { roomAdviceStatusLabel } from "../src/domains/hospitality/registration/room-advice-status.ts";

test("conflict status gives a useful neutral next step in each reviewed language", () => {
  for (const languageTag of ["en", "vi", "zh-Hans", "ja-JP"]) {
    const message = roomAdviceStatusLabel("conflict", languageTag);
    assert.ok(message.length > 30);
    assert.match(message, /adjust|điều chỉnh|调整|調整|ask|hỏi|联系|ホテル/u);
    assert.doesNotMatch(message, /hotel records conflict|hồ sơ khách sạn.*mâu thuẫn|酒店记录存在冲突|ホテル記録に矛盾/u);
  }
  assert.equal(
    roomAdviceStatusLabel("unknown_status", "fr"),
    roomAdviceStatusLabel("unsupported", "en"),
  );
});

test("incomplete stay cost retains the checked nightly reference but withholds stay total", () => {
  assert.deepEqual(roomAdviceCostView({
    status: "incomplete", total: null, nightly_subtotal: 1_950_000,
  }), {
    confirmedStayTotal: null,
    referenceNightlyBase: 1_950_000,
  });
  assert.deepEqual(roomAdviceCostView({
    status: "complete", total: 5_850_000, nightly_subtotal: 1_950_000,
  }), {
    confirmedStayTotal: 5_850_000,
    referenceNightlyBase: 1_950_000,
  });
});
