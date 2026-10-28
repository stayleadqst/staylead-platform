import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const moduleRoot = process.env.B08_PLAYWRIGHT_MODULE_ROOT;
let playwright;
try {
  playwright = createRequire(resolve(moduleRoot ?? process.cwd(), "package.json"))("playwright");
} catch (error) {
  throw new Error(
    "Could not load Playwright; set B08_PLAYWRIGHT_MODULE_ROOT to a node_modules directory containing playwright.",
    { cause: error },
  );
}

const { chromium } = playwright;
const webOrigin = process.env.B08_WEB_ORIGIN ?? "http://127.0.0.1:13540";
const scenario = process.env.B08_BROWSER_SCENARIO ?? "default";
const artifactDir = process.env.B08_BROWSER_ARTIFACT_DIR;
if (artifactDir) mkdirSync(artifactDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.addInitScript(() => { window.__b08Injected = false; });
  const outageScenario = scenario.startsWith("outage");
  const missingContact = scenario === "outage-missing-ar";
  const hotelSlug = missingContact ? "lagoon-family-demo" : "harbor-city-demo";
  await page.goto(`${webOrigin}/hotels/${hotelSlug}/chat`, { waitUntil: "domcontentloaded" });
  const composer = page.getByLabel("Your question");
  await composer.waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);

  const configuredChannel = page.locator(".booking-channel").first();
  if (missingContact) {
    assert.match(await configuredChannel.innerText(), /Open the configured booking channel/u);
  } else {
    assert.match(await configuredChannel.innerText(), /Open the configured booking channel/u);
    assert.equal(await configuredChannel.getByText("+1 555 0100").count(), 0,
      "contact details stay collapsed until the guest asks or chooses the contact control");
  }
  await configuredChannel.getByRole("button", { name: "Contact hotel" }).click();
  const initialContact = await configuredChannel.innerText();
  if (missingContact) {
    assert.match(initialContact, /No hotel contact is configured/u);
    assert.match(initialContact, /Contact hours are not configured/u);
    assert.doesNotMatch(initialContact, /\+1 555 0100|Daily, 09:00–17:00/u,
      "contact values from another property must not cross hotel scope");
  } else {
    assert.match(initialContact, /\+1 555 0100/u);
    assert.match(initialContact, /Daily, 09:00–17:00/u);
    assert.ok(initialContact.includes('+1 555 0100 <img src=x onerror="window.__b08Injected=true">'),
      "untrusted contact text remains visible literally");
    assert.equal(await configuredChannel.locator("img,script").count(), 0,
      "configured contact text must not create markup");
    assert.equal(await page.evaluate(() => window.__b08Injected), false);
    assert.equal(await configuredChannel.locator('a[href="https://booking.example/hotels/harbor-city-demo"]').count(), 1,
      "the configured booking link remains visible alongside contact details");
  }
  assert.match(initialContact, /Showing these details does not contact the hotel or send a message/u);

  if (outageScenario) {
    const messageRequests = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/api\/guest\/sessions\/[^/]+\/messages$/u.test(new URL(request.url()).pathname)) {
        messageRequests.push(request.postDataJSON());
      }
    });
    const localeSeed = scenario.endsWith("-ar") ? "أين الإفطار؟"
      : scenario.endsWith("-ko") ? "조식은 어디에 있나요?" : undefined;
    if (localeSeed) {
      await composer.fill(localeSeed);
      await page.getByRole("button", { name: "Send" }).click();
      await page.locator(".message-assistant").last().waitFor({ state: "visible", timeout: 30_000 });
      await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    }
    const failureRequestsBefore = messageRequests.length;
    await composer.fill("Trigger timeout in the test provider.");
    await page.getByRole("button", { name: "Send" }).click();
    const error = page.locator(".message-error").last();
    const outageNotice = error.locator(".status-note").last();
    await outageNotice.waitFor({ state: "visible", timeout: 15_000 });
    await page.waitForTimeout(250);
    assert.equal(messageRequests.length, failureRequestsBefore + 1,
      "the website must not automatically retry a timed-out request");
    const expectedLocale = scenario.endsWith("-ar") || missingContact ? "ar"
      : scenario.endsWith("-ko") ? "en" : "en";
    if (localeSeed) assert.equal(await page.locator("main").getAttribute("dir"), expectedLocale === "ar" ? "rtl" : "ltr");
    assert.equal(await outageNotice.getAttribute("lang"), expectedLocale);
    assert.equal(await outageNotice.getAttribute("dir"), expectedLocale === "ar" ? "rtl" : "ltr");
    if (scenario.endsWith("-ko")) assert.match(await outageNotice.innerText(), /shown in English/u);
    if (!localeSeed) assert.match(await outageNotice.innerText(), /No external action was taken/u);
    if (artifactDir) await page.screenshot({ path: resolve(artifactDir, `${scenario}-failure.png`), fullPage: true });

    const retry = page.getByRole("button", { name: "Retry answer" }).last();
    await retry.click();
    await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled, undefined, { timeout: 15_000 });
    assert.equal(messageRequests.length, failureRequestsBefore + 2,
      "one explicit same-ID status retry resolves the terminal failure without a provider call");
    assert.equal(messageRequests.at(-1)?.request_id, messageRequests.at(-2)?.request_id,
      "the first explicit recovery check preserves the failed request ID");
    if (await page.locator(".message-assistant").count() <= (localeSeed ? 1 : 0)) {
      const answersBeforeNewRequest = await page.locator(".message-assistant").count();
      await page.getByRole("button", { name: "Retry answer" }).last().click();
      await page.waitForFunction((previous) => document.querySelectorAll(".message-assistant").length > previous,
        answersBeforeNewRequest, { timeout: 30_000 });
    }
    await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    const answersBeforeContinuation = await page.locator(".message-assistant").count();
    await composer.fill("Where is breakfast?");
    await page.getByRole("button", { name: "Send" }).click();
    await page.waitForFunction((previous) => document.querySelectorAll(".message-assistant").length > previous,
      answersBeforeContinuation, { timeout: 30_000 });
    process.stdout.write(JSON.stringify({
      result: "b08-timeout-recovery-ui-passed",
      providerFailure: "controlled offline provider timeout after 1-second configured limit",
      locale: expectedLocale,
      automaticRetries: 0,
      explicitRecoveryRequestIds: messageRequests.slice(failureRequestsBefore).map((item) => item.request_id),
      recovery: "guest explicitly retried/resolved prior request, then continued with a new information question",
      evidence: "Next.js proxy → local B08 test API → isolated PostgreSQL; no live inference",
    }) + "\n");
    if (artifactDir) await page.screenshot({ path: resolve(artifactDir, `${scenario}-continued.png`), fullPage: true });
    await page.close();
  } else {
    await composer.fill("Where is breakfast, and is there a helipad?");
    await page.getByRole("button", { name: "Send" }).click();
    const answer = page.locator(".message-assistant").last();
    await answer.waitFor({ state: "visible", timeout: 30_000 });
    const answerText = await answer.innerText();
    assert.match(answerText, /Breakfast is at Ben Gio on floor 1 from 06:30 to 09:30/u);
    assert.match(answerText, /Please confirm helipad availability with the hotel/u);

    await page.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    await composer.fill("How can I contact the hotel?");
    await page.getByRole("button", { name: "Send" }).click();
    const requestedChannel = page.locator(".booking-channel").last();
    await requestedChannel.getByText("+1 555 0100").waitFor({ state: "visible", timeout: 30_000 });
    const requestedText = await requestedChannel.innerText();
    assert.match(requestedText, /Daily, 09:00–17:00/u);
    assert.doesNotMatch(requestedText, /we contacted|staff will reply|within \d+/iu,
      "the configured contact display makes no acknowledgement or deadline claim");
    assert.match(requestedText, /Showing these details does not contact the hotel or send a message/u);
    assert.equal(await requestedChannel.locator("img,script").count(), 0);
    assert.equal(await page.evaluate(() => window.__b08Injected), false);
    const approvedBookingHref = "https://booking.example/hotels/harbor-city-demo";
    assert.equal(await page.locator(".booking-channel").first().locator(`a[href="${approvedBookingHref}"]`).count(), 1,
      "the initial panel shows the configured property booking link");
    assert.equal(await requestedChannel.locator(`a[href="${approvedBookingHref}"]`).count(), 1,
      "the requested turn shows the same configured property booking link");

    const missingPage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await missingPage.goto(`${webOrigin}/hotels/lagoon-family-demo/chat`, { waitUntil: "domcontentloaded" });
    const missingComposer = missingPage.getByLabel("Your question");
    await missingComposer.waitFor({ state: "visible", timeout: 20_000 });
    await missingPage.waitForFunction(() => !document.querySelector("#guest-question")?.disabled);
    const missingChannel = missingPage.locator(".booking-channel").first();
    const missingBookingLink = missingChannel.locator('a[href="https://booking.example/hotels/lagoon-family-demo"]');
    await missingBookingLink.waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await missingBookingLink.count(), 1);
    await missingChannel.getByRole("button", { name: "Contact hotel" }).click();
    const missingText = await missingChannel.innerText();
    assert.match(missingText, /No hotel contact is configured/u);
    assert.match(missingText, /Contact hours are not configured/u);
    assert.match(missingText, /Showing these details does not contact the hotel or send a message/u);
    assert.doesNotMatch(missingText, /\+1 555 0100|Daily, 09:00–17:00/u,
      "contact details from another property must not cross hotel scope");
    await missingPage.close();

    process.stdout.write(JSON.stringify({
      result: "b08-contact-and-partial-answer-ui-passed",
      viewport: "390x844",
      contact: "property-configured value and hours shown on explicit control/request",
      partialAnswer: "supported breakfast and exact helipad unknown both visible",
      bookingAction: "configured URL and contact coexist; no reservation, message, acknowledgement, or deadline",
      evidence: "Next.js proxy → local B08 test API → isolated PostgreSQL; controlled offline provider",
    }) + "\n");
    if (artifactDir) await page.screenshot({ path: resolve(artifactDir, "default-contact-partial.png"), fullPage: true });
    await page.close();
  }
} finally {
  await browser.close();
}
