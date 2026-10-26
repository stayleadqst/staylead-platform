import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const { chromium } = await import(pathToFileURL(
  "/Users/ccvn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs",
).href);
const BASE_URL = process.env.STAYLEAD_S6_WEB_URL ?? "http://127.0.0.1:13016";
const EVIDENCE = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_PATH = path.join(EVIDENCE, "consumer-final-ac-browser.json");
const EXPECTED_CANDIDATE = "b666454970829c56ae52d3cfe184b7414c4d8cd4";
const LABEL_KEYS = [
  "send", "sending", "copy", "copied", "copy_failed", "retry_answer", "check_status",
  "brief", "stay", "nights", "adults", "children", "age", "unknown", "pending_age",
  "updated", "partial_success", "stale_answer", "ai_notice", "synthetic_notice",
];
const ZH_LABELS = Object.fromEntries(LABEL_KEYS.map((key) => [key, `已翻譯-${key}`]));
const BASE_ORIGIN = new URL(BASE_URL).origin;

const brief = (version) => ({
  brief_version: version,
  dates: { check_in: null, check_out: null, nights: null },
  party: { adults: 2, children: [] },
  pending_fields: [],
});

function response({ requestId, answer, language, direction, revision, labels, labelsFallback = false, briefVersion }) {
  return {
    request_id: requestId,
    status: "completed",
    answer,
    language_preference: { language_tag: language, source: "explicit", revision },
    presentation: {
      language_tag: language,
      direction,
      preference_revision: revision,
      labels,
      labels_fallback: labelsFallback,
      freshness: "current",
      receipt_id: requestId,
    },
    answer_eligibility: "current",
    guest_brief: brief(briefVersion),
    evidence: [],
    unknowns: [],
  };
}

function session(language, revision) {
  return {
    session_id: `session-${language}-${revision}`,
    access_token: "synthetic-browser-fixture",
    token_type: "Bearer",
    expires_at: "2099-01-01T00:00:00Z",
    hotel: { hotel_id: "fixture-hotel", hotel_slug: "harbor-city-demo", name: "Harbor City" },
    config_version: "fixture-v1",
    language_preference: { language_tag: language, source: "explicit", revision },
  };
}

async function installApi(page, { initialLanguage, initialRevision, messageHandler }) {
  const counts = { messages: 0, translationLike: 0, unrecognized: 0 };
  const paths = [];
  const externalOrigins = new Set();
  page.on("request", (request) => {
    try {
      const origin = new URL(request.url()).origin;
      if (origin !== BASE_ORIGIN) externalOrigins.add(origin);
    } catch { /* Ignore non-URL browser request identifiers. */ }
  });
  await page.route("**/api/guest/**", async (route) => {
    const url = new URL(route.request().url());
    paths.push(url.pathname);
    if (url.pathname.endsWith("/health")) {
      await route.fulfill({ json: { status: "ok", domain: "hospitality", guest_contract_version: "1" } });
      return;
    }
    if (/\/hotels\/[a-z0-9-]+$/.test(url.pathname)) {
      await route.fulfill({ json: {
        hotel_id: "fixture-hotel", hotel_slug: "harbor-city-demo", public_config: {},
        config_version: "fixture-v1", guest_contract_version: "1",
      } });
      return;
    }
    if (url.pathname.endsWith("/sessions") && route.request().method() === "POST") {
      await route.fulfill({ json: session(initialLanguage, initialRevision) });
      return;
    }
    if (url.pathname.endsWith("/freshness")) {
      await route.fulfill({ json: { status: "current" } });
      return;
    }
    if (url.pathname.endsWith("/messages") && route.request().method() === "POST") {
      counts.messages += 1;
      await messageHandler({ route, count: counts.messages, counts });
      return;
    }
    if (/translat|label/i.test(url.pathname)) counts.translationLike += 1;
    else counts.unrecognized += 1;
    await route.fulfill({ status: 404, json: { error: { code: "fixture_unexpected_path", message: "Unexpected mocked API path." } } });
  });
  return { counts, paths, externalOrigins };
}

async function openPage(browser, apiOptions) {
  const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  const api = await installApi(page, apiOptions);
  await page.goto(`${BASE_URL}/hotels/harbor-city-demo/chat`, { waitUntil: "networkidle" });
  await page.getByLabel("Your question").waitFor();
  return { context, page, api };
}

async function submit(page, message) {
  await page.getByLabel("Your question").fill(message);
  await page.locator(".chat-composer button[type=submit]").click();
}

async function waitForAssistantCount(page, count) {
  await page.waitForFunction((expected) => document.querySelectorAll(".message-assistant[lang][dir]").length >= expected, count);
}

async function waitForMessageCount(api, count) {
  const deadline = Date.now() + 5000;
  while (api.counts.messages < count && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(api.counts.messages, count, `expected ${count} explicit message request(s)`);
}

const browser = await chromium.launch({ headless: true, channel: "chrome" });
const checks = [];
try {
  // The UI serializes semantic requests. A later response carrying an older
  // preference revision must not roll back the current language; old answers
  // retain the language and direction from their own response metadata.
  let releaseArabic;
  let releaseOldLocale;
  const localePage = await openPage(browser, {
    initialLanguage: "en",
    initialRevision: 0,
    messageHandler: async ({ route, count }) => {
      if (count === 1) {
        await route.fulfill({ json: response({ requestId: "locale-1", answer: "Linh Nguyễn; room 123; 08:30 https://example.test/stay",
          language: "en", direction: "ltr", revision: 1,
          labels: { send: "Send", copy: "Copy", copied: "Copied", check_status: "Check status" }, briefVersion: 1 }) });
        return;
      }
      if (count === 2) {
        await new Promise((resolve) => { releaseArabic = async () => { await route.fulfill({ json: response({ requestId: "locale-2",
          answer: "مرحباً ليلى؛ الغرفة ١٢٣؛ 08:30", language: "ar-EG", direction: "rtl", revision: 2,
          labels: { send: "إرسال", copy: "نسخ", copied: "تم النسخ", check_status: "تحقق من الحالة" }, briefVersion: 2 }) }); resolve(); }; });
        return;
      }
      if (count === 3) {
        await new Promise((resolve) => { releaseOldLocale = async () => { await route.fulfill({ json: response({ requestId: "locale-3",
          answer: "Older English preference response; 08:30", language: "en", direction: "ltr", revision: 1,
          labels: { send: "Send", copy: "Copy", copied: "Copied", check_status: "Check status" }, briefVersion: 3 }) }); resolve(); }; });
        return;
      }
      await route.fulfill({ status: 500, json: { error: { code: "unexpected_test_request", message: "Unexpected request." } } });
    },
  });
  const { page, context, api } = localePage;
  await submit(page, "Answer in English for Linh Nguyễn, room 123, time 08:30 and URL https://example.test/stay");
  await waitForAssistantCount(page, 1);
  await submit(page, "Please switch to Arabic for my next answer.");
  await waitForMessageCount(api, 2);
  assert.equal(await page.getByLabel("Your question").isDisabled(), true, "composer must serialize in-flight locale turns");
  assert.equal(releaseArabic instanceof Function, true);
  await releaseArabic();
  await waitForAssistantCount(page, 2);
  assert.equal(await page.locator("main.chat-shell").getAttribute("lang"), "ar-EG");
  assert.equal(await page.locator("main.chat-shell").getAttribute("dir"), "rtl");

  await submit(page, "Please answer in English.");
  await waitForMessageCount(api, 3);
  assert.equal(await page.getByLabel("Your question").isDisabled(), true, "composer must remain locked while older preference response is pending");
  assert.equal(await page.locator("main.chat-shell").getAttribute("lang"), "ar-EG");
  await releaseOldLocale();
  await waitForAssistantCount(page, 3);
  const cards = page.locator(".message-assistant[lang][dir]");
  assert.equal(await cards.nth(0).getAttribute("lang"), "en");
  assert.equal(await cards.nth(0).getAttribute("dir"), "ltr");
  assert.equal(await cards.nth(1).getAttribute("lang"), "ar-EG");
  assert.equal(await cards.nth(1).getAttribute("dir"), "rtl");
  assert.equal(await cards.nth(2).getAttribute("lang"), "en", "each answer keeps its response language");
  assert.equal(await cards.nth(2).getAttribute("data-answer-eligibility"), "stale", "old preference revision cannot remain copy-eligible");
  assert.equal(await cards.nth(2).locator(".answer-actions button").last().isDisabled(), true);
  assert.equal(await page.locator("main.chat-shell").getAttribute("lang"), "ar-EG", "older response revision must not replace newer preference");
  assert.equal(await page.locator(".chat-header > div[lang]").getAttribute("lang"), "ar-EG");
  assert.equal(await page.locator(".chat-header > div[lang]").getAttribute("dir"), "rtl");
  assert.equal(api.counts.messages, 3);
  assert.equal(api.counts.translationLike, 0);
  assert.equal(api.counts.unrecognized, 0);
  checks.push({
    id: "L3-AC2",
    status: "pass",
    assertions: ["composer serializes delayed turns", "older preference revision did not replace current RTL preference", "historical answer lang/dir retained", "older-revision current answer not copy eligible", "brief direction follows current preference"],
    message_requests: api.counts.messages,
    translation_like_requests: api.counts.translationLike,
  });
  await context.close();

  const cachedOutage = await openPage(browser, {
    initialLanguage: "zh-Hant",
    initialRevision: 5,
    messageHandler: async ({ route, count }) => {
      if (count === 1) {
        await route.fulfill({ json: response({ requestId: "cached-labels-1", answer: "繁體中文回答。",
          language: "zh-Hant", direction: "ltr", revision: 5, labels: ZH_LABELS, briefVersion: 1 }) });
      } else {
        await route.fulfill({ status: 502, json: { error: { code: "provider_failure", message: "The answer was not completed." } } });
      }
    },
  });
  await submit(cachedOutage.page, "Give an answer before the provider outage.");
  await waitForAssistantCount(cachedOutage.page, 1);
  assert.equal(await cachedOutage.page.locator(".chat-composer button[type=submit]").textContent(), ZH_LABELS.send);
  assert.equal(await cachedOutage.page.locator(".chat-header .synthetic-label").textContent(), ZH_LABELS.synthetic_notice);
  await submit(cachedOutage.page, "Trigger a synthetic provider outage.");
  await waitForMessageCount(cachedOutage.api, 2);
  await cachedOutage.page.getByRole("status").filter({ hasText: /We could not answer this request/i }).waitFor();
  assert.equal(await cachedOutage.page.locator(".message-assistant[lang][dir]").count(), 1, "outage must not create a false success answer");
  assert.equal(await cachedOutage.page.locator(".chat-composer button[type=submit]").textContent(), ZH_LABELS.send, "last validated labels remain available during outage");
  assert.equal(cachedOutage.api.counts.messages, 2);
  assert.equal(cachedOutage.api.counts.translationLike, 0);
  assert.equal(cachedOutage.api.counts.unrecognized, 0);
  checks.push({ id: "L3-AC4-cached-labels", status: "pass", assertions: ["last validated locale labels survive HTTP 502", "visible provider failure", "no false success", "no translation or extra API request"], message_requests: 2 });
  await cachedOutage.context.close();

  const englishOutage = await openPage(browser, {
    initialLanguage: "ja-JP",
    initialRevision: 7,
    messageHandler: async ({ route, count }) => {
      assert.equal(count, 1);
      await route.fulfill({ status: 502, json: { error: { code: "provider_failure", message: "The answer was not completed." } } });
    },
  });
  await submit(englishOutage.page, "Trigger outage before any translated bundle is cached.");
  await waitForMessageCount(englishOutage.api, 1);
  await englishOutage.page.getByText("Some interface labels are shown in English because translations are unavailable.").waitFor();
  await englishOutage.page.getByRole("status").filter({ hasText: /We could not answer this request/i }).waitFor();
  assert.equal(await englishOutage.page.locator("main.chat-shell").getAttribute("lang"), "ja-JP");
  assert.equal(await englishOutage.page.locator(".chat-composer button[type=submit]").textContent(), "Send");
  assert.equal(await englishOutage.page.locator(".message-assistant[lang][dir]").count(), 0, "outage must not appear as a successful answer");
  assert.equal(englishOutage.api.counts.messages, 1);
  assert.equal(englishOutage.api.counts.translationLike, 0);
  assert.equal(englishOutage.api.counts.unrecognized, 0);
  checks.push({ id: "L3-AC4-disclosed-English-fallback", status: "pass", assertions: ["English fallback explicitly disclosed", "provider failure visible", "no false success", "no translation or extra API request"], message_requests: 1 });
  await englishOutage.context.close();

  const result = {
    candidate_commit: EXPECTED_CANDIDATE,
    mode: "mocked-production-browser-focused-ac",
    status: "pass",
    checks,
    browser_external_origins: [...new Set([
      ...localePage.api.externalOrigins,
      ...cachedOutage.api.externalOrigins,
      ...englishOutage.api.externalOrigins,
    ])],
    screenshot_files_created: false,
    model_or_backend_calls: 0,
    limitations: ["Provider failure and delayed/stale preference responses were intercepted fixtures; no backend/provider was contacted."],
  };
  assert.deepEqual(result.browser_external_origins, [], "browser must stay on the local production web origin");
  await fs.writeFile(OUTPUT_PATH, `${JSON.stringify(result, null, 2)}\n`, { mode: 0o600 });
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
