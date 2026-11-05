import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const moduleRoot = process.env.B09_PLAYWRIGHT_MODULE_ROOT;
let playwright;
try {
  playwright = createRequire(resolve(moduleRoot ?? process.cwd(), "package.json"))("playwright");
} catch (error) {
  throw new Error(
    "Could not load Playwright; set B09_PLAYWRIGHT_MODULE_ROOT to a node_modules directory containing playwright.",
    { cause: error },
  );
}
const { chromium } = playwright;
const webOrigin = process.env.B09_WEB_ORIGIN ?? "http://127.0.0.1:13530";
const artifactDir = process.env.B09_BROWSER_ARTIFACT_DIR;
const scenario = process.env.B09_BROWSER_SCENARIO ?? "default";
if (artifactDir) mkdirSync(artifactDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
try {
  if (scenario === "confirmation-only") {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.addInitScript(() => { window.__b09Injected = false; });
    const confirmationResponses = [];
    page.on("response", async (response) => {
      if (response.url().includes("/api/guest/sessions/") && response.url().endsWith("/brief-confirmations")) {
        const observation = { status: response.status() };
        try {
          const payload = await response.json();
          const errorCode = payload?.error?.code;
          if (typeof errorCode === "string") observation.errorCode = errorCode;
        } catch {
          // Keep diagnostic output limited to status and a safe API error code.
        }
        confirmationResponses.push(observation);
      }
    });
    await page.goto(`${webOrigin}/hotels/harbor-city-demo/chat`, { waitUntil: "domcontentloaded" });
    const composer = page.getByLabel("Your question");
    await composer.waitFor({ state: "visible", timeout: 20_000 });
    await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    await composer.fill("For this test, set two adults.");
    await page.getByRole("button", { name: "Send" }).click();
    const review = page.locator(".brief-confirmation");
    await review.waitFor({ state: "visible", timeout: 30_000 });
    const reviewText = await review.innerText();
    assert.match(reviewText, /Adults/);
    assert.match(reviewText, /Not set/);
    assert.match(reviewText, /2/);
    assert.equal(await review.locator("img,script,a").count(), 0, "review content must be rendered as text");
    await review.getByRole("button", { name: "Confirm changes" }).click();
    try {
      await page.locator(".brief-receipt").waitFor({ state: "visible", timeout: 30_000 });
    } catch (error) {
      await page.waitForTimeout(250);
      let failureScreenshot = null;
      if (artifactDir) {
        failureScreenshot = resolve(artifactDir, "b09-browser-confirmation-failure.png");
        await page.screenshot({ path: failureScreenshot, fullPage: true });
      }
      process.stderr.write(JSON.stringify({
        scenario: "confirmation-only", confirmationResponses, failureScreenshot,
      }) + "\n");
      throw error;
    }
    await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    assert.match(await page.locator(".brief-summary").innerText(), /2\s+adults/i);
    assert.deepEqual(confirmationResponses, [{ status: 200 }]);
    let screenshots = null;
    if (artifactDir) {
      const confirmed = resolve(artifactDir, "b09-browser-confirmed-brief.png");
      await page.screenshot({ path: confirmed, fullPage: true });
      screenshots = { confirmed };
    }

    const hostileNeed = '<img src=x onerror="window.__b09Injected=true"> https://attacker.invalid/probe';
    await composer.fill(`Now change it to three adults and require room accessibility exactly: ${hostileNeed}`);
    await page.getByRole("button", { name: "Send" }).click();
    const secondReview = page.locator(".brief-confirmation");
    await secondReview.waitFor({ state: "visible", timeout: 30_000 });
    const secondReviewText = await secondReview.innerText();
    assert.match(secondReviewText, /3/);
    assert.match(secondReviewText, /Required room accessibility/i);
    assert.ok(secondReviewText.includes(hostileNeed), "untrusted accessibility text must remain visible as literal text");
    assert.equal(await secondReview.locator("img,script,a").count(), 0, "proposal text must not create markup or active links");
    assert.equal(await page.locator('a[href*="attacker.invalid"]').count(), 0, "unsafe URL must remain inactive text");
    assert.equal(await page.locator("img[onerror]").count(), 0);
    assert.equal(await page.evaluate(() => window.__b09Injected === true), false);
    await secondReview.getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("status").filter({ hasText: "Changes were not saved." }).waitFor({ state: "visible" });
    assert.equal(await page.locator(".brief-confirmation").count(), 0);
    assert.match(await page.locator(".brief-summary").innerText(), /2\s+adults/i);
    assert.deepEqual(confirmationResponses, [{ status: 200 }], "cancel must not submit a confirmation action");
    if (artifactDir) {
      const canceled = resolve(artifactDir, "b09-browser-canceled-brief.png");
      await page.screenshot({ path: canceled, fullPage: true });
      screenshots.canceled = canceled;
    }
    process.stdout.write(JSON.stringify({
      result: "offline-brief-confirmation-ui-passed",
      confirmationResponses,
      confirmedChangeRendered: true,
      canceledProposalLeftBriefUnchanged: true,
      screenshots,
      evidence: "actual Next proxy → local test-only API → isolated PostgreSQL; no live inference",
    }) + "\n");
    await page.close();
  } else if (scenario === "confirmation-no-effect-recovery-only") {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const confirmationResponses = [];
    const confirmationRequestIds = [];
    let interceptFirstConfirmation = true;
    page.on("response", async (response) => {
      if (response.url().includes("/api/guest/sessions/") && response.url().endsWith("/brief-confirmations")) {
        const observation = { status: response.status() };
        try {
          const payload = await response.json();
          const errorCode = payload?.error?.code;
          if (typeof errorCode === "string") observation.errorCode = errorCode;
        } catch {
          // Keep output to status and sanitized API error codes.
        }
        confirmationResponses.push(observation);
      }
    });
    await page.route("**/api/guest/sessions/*/brief-confirmations", async (route) => {
      const body = route.request().postDataJSON();
      if (typeof body?.request_id === "string") confirmationRequestIds.push(body.request_id);
      if (interceptFirstConfirmation) {
        interceptFirstConfirmation = false;
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: {
            code: "brief_apply_no_effect",
            message: "The trip update was not applied. Confirm it again as a new request.",
            retryable: true,
          } }),
        });
      } else {
        await route.continue();
      }
    });
    await page.goto(`${webOrigin}/hotels/harbor-city-demo/chat`, { waitUntil: "domcontentloaded" });
    const composer = page.getByLabel("Your question");
    await composer.waitFor({ state: "visible", timeout: 20_000 });
    await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    await composer.fill("For this test, set two adults.");
    await page.getByRole("button", { name: "Send" }).click();
    const review = page.locator(".brief-confirmation");
    await review.waitFor({ state: "visible", timeout: 30_000 });
    await review.getByRole("button", { name: "Confirm changes" }).click();
    const firstFailure = page.locator(".message-error");
    await firstFailure.waitFor({ state: "visible", timeout: 15_000 });
    await page.waitForTimeout(250);
    assert.deepEqual(confirmationResponses, [{ status: 503, errorCode: "brief_apply_no_effect" }]);
    assert.equal(confirmationRequestIds.length, 1, "a known no-effect response must not auto-submit again");
    assert.equal(await review.count(), 1, "the guest may explicitly retry the still-visible proposal");

    await firstFailure.getByRole("button", { name: "Retry answer" }).click();
    await page.locator(".brief-receipt").waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(confirmationRequestIds.length, 2, "only the explicit retry should make a second confirmation request");
    assert.notEqual(confirmationRequestIds[1], confirmationRequestIds[0],
      "a confirmed no-effect retry must use a new request ID");
    assert.deepEqual(confirmationResponses, [
      { status: 503, errorCode: "brief_apply_no_effect" }, { status: 200 },
    ]);
    assert.match(await page.locator(".brief-summary").innerText(), /2\s+adults/i,
      "the second explicit confirmation must reach the real API and commit the change");
    process.stdout.write(JSON.stringify({
      result: "offline-confirmation-no-effect-recovery-passed",
      confirmationResponses,
      distinctRequestIdsUsed: true,
      firstFailure: "synthetic local browser interception; no API request was forwarded",
      secondConfirmation: "actual Next proxy → local test-only API → isolated PostgreSQL",
      evidence: "one prepared challenge; no automatic retry; user initiated a new-ID retry; no live inference",
    }) + "\n");
    await page.close();
  } else if (scenario === "html-refusal-only") {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    let refusalStatus;
    page.on("response", (response) => {
      if (response.url().includes("/api/guest/sessions/") && response.url().endsWith("/messages")) {
        refusalStatus = response.status();
      }
    });
    await page.goto(`${webOrigin}/hotels/harbor-city-demo/chat`, { waitUntil: "domcontentloaded" });
    const probe = page.getByLabel("Your question");
    await probe.waitFor({ state: "visible", timeout: 20_000 });
    await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    const marker = `B09-HTML-REFUSAL-${Date.now()}`;
    const hostileText = `B09 security injection probe ${marker}: <img src=x onerror="window.__b09Injected=true"> https://attacker.invalid/probe`;
    await probe.fill(hostileText);
    await page.getByRole("button", { name: "Send" }).click();
    const refusal = page.locator(".message-error");
    await refusal.waitFor({ state: "visible", timeout: 30_000 });
    const guestMessage = page.locator(".message.message-guest").filter({ hasText: marker }).last();
    await guestMessage.waitFor({ state: "visible" });
    assert.equal(await guestMessage.evaluate((node) => node.textContent), hostileText);
    assert.equal(await page.locator("img[onerror]").count(), 0, "guest text must never create executable markup");
    assert.equal(await page.locator('a[href*="attacker.invalid"]').count(), 0, "unsafe URL must remain inactive text");
    assert.equal(await page.evaluate(() => window.__b09Injected === true), false);
    assert.equal(await page.locator(".message-assistant .answer-copy-source").count(), 0);
    assert.equal(await page.locator(".brief-summary").count(), 0);
    assert.equal(refusalStatus, 502, "the local API must refuse the controlled malicious proposal");
    let screenshot = null;
    if (artifactDir) {
      screenshot = resolve(artifactDir, "b09-browser-html-refusal.png");
      await page.screenshot({ path: screenshot, fullPage: true });
    }
    process.stdout.write(JSON.stringify({
      result: "offline-html-refusal-check-passed",
      apiResponseStatus: refusalStatus,
      guestTextRenderedLiterally: true,
      noInjectedMarkupOrActiveUnsafeUrl: true,
      noAnswerOrBriefAfterRefusal: true,
      screenshot,
      evidence: "single local production-web refusal case + test-only API stub; no live inference",
    }) + "\n");
    await page.close();
  } else {
    assert.equal(scenario, "default", `unknown B09 browser scenario: ${scenario}`);
  const successPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let successStatus;
  successPage.on("response", (response) => {
    if (response.url().includes("/api/guest/sessions/") && response.url().endsWith("/messages")) {
      successStatus = response.status();
    }
  });
  await successPage.goto(`${webOrigin}/hotels/harbor-city-demo/chat`, { waitUntil: "domcontentloaded" });
  const question = successPage.getByLabel("Your question");
  await question.waitFor({ state: "visible", timeout: 20_000 });
  await successPage.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
  await question.fill("What are the breakfast hours?");
  await successPage.getByRole("button", { name: "Send" }).click();
  const answer = successPage.locator(".message-assistant .answer-copy-source");
  await answer.waitFor({ state: "visible", timeout: 30_000 });
  assert.match(await answer.innerText(), /hotel record includes the requested information/i);
  assert.equal(await successPage.locator(".message-error").count(), 0);
  assert.equal(successStatus, 200, "browser request must reach the local API and complete successfully");

  const probePage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let refusalStatus;
  probePage.on("response", (response) => {
    if (response.url().includes("/api/guest/sessions/") && response.url().endsWith("/messages")) {
      refusalStatus = response.status();
    }
  });
  await probePage.goto(`${webOrigin}/hotels/harbor-city-demo/chat`, { waitUntil: "domcontentloaded" });
  const probe = probePage.getByLabel("Your question");
  await probe.waitFor({ state: "visible", timeout: 20_000 });
  await probePage.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
  await probe.fill("B09 security injection probe");
  await probePage.getByRole("button", { name: "Send" }).click();
  const refused = probePage.locator(".message-error");
  await refused.waitFor({ state: "visible", timeout: 30_000 });
  assert.equal(await probePage.locator(".message-assistant .answer-copy-source").count(), 0);
  assert.equal(await probePage.locator(".brief-summary").count(), 0);
  assert.equal(refusalStatus, 502, "malicious stub proposal must be rejected by the actual API");
  const refusedText = await refused.innerText();
  assert.doesNotMatch(refusedText, /nine|9 adults|guest party/i);

  let screenshots = null;
  if (artifactDir) {
    const positive = resolve(artifactDir, "b09-browser-positive.png");
    const refusal = resolve(artifactDir, "b09-browser-refusal.png");
    await successPage.screenshot({ path: positive, fullPage: true });
    await probePage.screenshot({ path: refusal, fullPage: true });
    screenshots = { positive, refusal };
  }
  process.stdout.write(JSON.stringify({
    result: "offline-browser-checks-passed",
    origin: webOrigin,
    successfulFaqRendered: true,
    maliciousStubProposalRefusedInUi: true,
    noBriefOrAnswerAfterRefusal: true,
    apiResponseStatuses: [successStatus, refusalStatus],
    screenshots,
    evidence: "local production-web build + test-only API stub; no live inference",
  }) + "\n");
  await probePage.close();
  await successPage.close();
  }
} finally {
  await browser.close();
}
