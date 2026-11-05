import assert from "node:assert/strict";

const { chromium } = await import("/Users/ccvn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs");
const browser = await chromium.launch({ headless: false, channel: "chrome" });
const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"] });
const page = await context.newPage();
let messageCalls = 0;
const brief = { brief_version: 1, dates: { check_in: null, check_out: null, nights: null }, party: { adults: 2, children: [] }, pending_fields: [] };
const receipt = { request_id: "receipt-update-1", status: "partial_success", brief_version_before: 1, brief_version_after: 2,
  applied_delta: { party: { adults: 3 } }, source_refs: [], answer_status: "pending", brief_version_used: null };
const presentation = { language_tag: "en", direction: "ltr", preference_revision: 0, freshness: "current", receipt_id: null,
  labels_fallback: false, labels: { copy: "Copy", copied: "Copied", retry_answer: "Retry answer" } };
await page.route("**/api/guest/**", async (route) => {
  const url = new URL(route.request().url());
  if (url.pathname.endsWith("/health")) return route.fulfill({ json: { status: "ok", domain: "hospitality", guest_contract_version: "1" } });
  if (url.pathname.endsWith("/hotels/harbor-city-demo")) return route.fulfill({ json: { hotel_id: "hotel-1", hotel_slug: "harbor-city-demo", public_config: {}, config_version: "1", guest_contract_version: "1" } });
  if (url.pathname.endsWith("/sessions") && route.request().method() === "POST") return route.fulfill({ json: {
    session_id: "session-12345678", access_token: "synthetic-token", token_type: "Bearer", expires_at: "2099-01-01T00:00:00Z",
    hotel: { hotel_id: "hotel-1", hotel_slug: "harbor-city-demo", public_config: {} }, config_version: "1",
    language_preference: { language_tag: "en", source: "fallback", revision: 0 },
  } });
  if (url.pathname.endsWith("/messages")) {
    messageCalls += 1;
    if (messageCalls === 1) return route.fulfill({ json: { request_id: "old-answer-id", status: "completed", answer: "Original answer stays exactly as shown.",
      guest_brief: brief, evidence: [], unknowns: [], language_preference: { language_tag: "en", source: "fallback", revision: 0 }, presentation,
      answer_eligibility: "current", brief_version_used: 1 }, status: 200 });
    if (messageCalls === 2) return route.fulfill({ status: 502, json: { request_id: "edit-id", status: "partial_success", guest_brief: { ...brief, brief_version: 2, party: { adults: 3, children: [] } },
      brief_receipt: receipt, applied_delta: receipt.applied_delta, answer_status: "failed", error: { code: "answer_generation_failed", message: "Answer did not finish." } } });
    if (messageCalls === 3) return route.abort("failed");
    if (messageCalls === 4) return route.fulfill({ status: 200, json: { request_id: "resume-new-request-id", status: "completed", answer: "Updated answer for the committed trip details.",
      guest_brief: { ...brief, brief_version: 2, party: { adults: 3, children: [] } }, brief_receipt: { ...receipt, answer_status: "completed", brief_version_used: 2 },
      applied_delta: receipt.applied_delta, evidence: [], unknowns: [], language_preference: { language_tag: "en", source: "fallback", revision: 0 }, presentation,
      answer_eligibility: "current", brief_version_used: 2 } });
    return route.fulfill({ status: 500, json: { error: { code: "unexpected_test_call", message: "Unexpected synthetic test request." } } });
  }
  return route.fulfill({ status: 404, json: { error: { code: "not_found", message: "Unexpected route." } } });
});

try {
  await page.goto("http://127.0.0.1:13016/hotels/harbor-city-demo/chat", { waitUntil: "networkidle" });
  const composer = page.locator("#guest-question");
  await composer.waitFor({ state: "visible" });
  await composer.fill("Tell me the current details.");
  await page.locator(".chat-composer button[type=submit]").click();
  await page.getByText("Original answer stays exactly as shown.").waitFor();
  await composer.fill("Change our party to 3 adults.");
  await page.locator(".chat-composer button[type=submit]").click();
  await page.getByRole("button", { name: "Continue the answer using the updated trip details" }).waitFor();
  await page.getByRole("button", { name: "Continue the answer using the updated trip details" }).click();
  await page.getByRole("button", { name: "Retry answer" }).waitFor();
  assert.equal(await composer.isDisabled(), true, "uncertain same-receipt attempt should keep semantic composer locked");
  await page.getByRole("button", { name: "Continue the answer using the updated trip details" }).click();
  await page.getByText("Updated answer for the committed trip details.").waitFor();
  await page.getByText("This saved answer was completed by a later continuation.").first().waitFor();
  assert.equal(await composer.isDisabled(), false, "successful same-receipt completion should release composer");
  assert.equal(await page.getByText("Original answer stays exactly as shown.").count(), 1, "historical answer must remain unchanged");
  assert.equal(await page.getByText("This saved answer was completed by a later continuation.").count(), 2,
    "original partial and unknown continuation bubbles should both resolve");
  assert.equal(await page.getByRole("button", { name: "Retry answer" }).count(), 0, "unknown sibling attempt must no longer offer retry");
  const answer = page.locator(".message-assistant[lang][dir]").last();
  const renderedText = await answer.locator(".answer-copy-source").textContent();
  const beforeCopyCalls = messageCalls;
  await answer.locator(".answer-actions button").last().click();
  await answer.locator(".copy-status[data-copy-result='copied']").waitFor({ state: "attached" });
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), renderedText, "clipboard should match the exact rendered answer text");
  assert.equal(messageCalls, beforeCopyCalls, "copy must not produce another guest API request");
  assert.equal(messageCalls, 4, "only the four explicit synthetic submissions were sent");
  console.log(JSON.stringify({ result: "pass", message_calls: messageCalls, composer_enabled_after_recovery: true,
    historical_answer_preserved: true, mocked_api_only: true }, null, 2));
} finally {
  await context.close();
  await browser.close();
}
