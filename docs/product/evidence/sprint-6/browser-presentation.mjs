import assert from "node:assert/strict";

const { chromium } = await import("/Users/ccvn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs");
const baseUrl = process.env.STAYLEAD_WEB_URL ?? "http://127.0.0.1:13016";
const CASES = [
  { tag: "en", direction: "ltr", answer: "Welcome, Linh Nguyễn! Room 123; breakfast at 08:30. https://example.test/stay", copy: "Copy" },
  { tag: "zh-Hant", direction: "ltr", answer: "欢迎，李明！房间 １２３；早餐 08:30。https://example.test/stay", copy: "复制" },
  { tag: "ja-JP", direction: "ltr", answer: "李 明さん、ようこそ。部屋は １２３、朝食は 08:30 です。https://example.test/stay", copy: "コピー" },
  { tag: "ar-EG", direction: "rtl", answer: "مرحباً، ليلى! الغرفة ١٢٣؛ الإفطار 08:30. https://example.test/stay", copy: "نسخ" },
  { tag: "hi-IN", direction: "ltr", answer: "स्वागत है, आरव! कमरा १२३; नाश्ता 08:30 बजे। https://example.test/stay", copy: "कॉपी" },
  { tag: "fr-FR", direction: "ltr", answer: "Bonjour 李明 — room 123, petit-déjeuner à 08:30. https://example.test/stay", copy: "Copier" },
];
const EXPLICIT_SCRIPT_CASE = {
  tag: "az-Arab", direction: "rtl",
  answer: "خوش آمدید، نرگس! اتاق ۱۲۳؛ صبحانه ساعت 08:30. https://example.test/stay",
  copy: "نسخ",
};

function session(tag = "zh-Hant", sessionId = "123e4567-e89b-42d3-a456-426614174000") {
  return {
    session_id: sessionId,
    access_token: "offline-browser-fixture",
    token_type: "Bearer",
    expires_at: "2099-01-01T00:00:00Z",
    hotel: { name: "海湾旅馆" },
    config_version: "fixture-v1",
    language_preference: { language_tag: tag, source: "explicit", revision: 1 },
  };
}

async function routeApi(page, { eligibility = "current", languageCase = CASES[1], delaySecondMessage = false, includeBrief = false } = {}) {
  let messages = 0;
  let releaseDelayed;
  const messageWaiters = [];
  const waitForMessageCount = (count) => messages >= count
    ? Promise.resolve()
    : new Promise((resolve) => messageWaiters.push({ count, resolve }));
  await page.route("**/api/guest/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/health")) {
      await route.fulfill({ json: { status: "ok", domain: "hospitality", guest_contract_version: "1" } });
    } else if (/\/hotels\/[a-z0-9-]+$/.test(path)) {
      await route.fulfill({ json: {
        hotel_id: "hotel-fixture", hotel_slug: path.split("/").at(-1), public_config: {},
        config_version: "fixture-v1", guest_contract_version: "1",
      } });
    } else if (path.endsWith("/sessions") && route.request().method() === "POST") {
      const slug = JSON.parse(route.request().postData() ?? "{}").hotel_slug;
      await route.fulfill({ json: session(languageCase.tag,
        slug === "lagoon-family-demo" ? "223e4567-e89b-42d3-a456-426614174000" : "123e4567-e89b-42d3-a456-426614174000") });
    } else if (path.endsWith("/messages") && route.request().method() === "POST") {
      messages += 1;
      const pendingWaiters = [];
      for (const waiter of messageWaiters.splice(0)) {
        if (messages >= waiter.count) waiter.resolve();
        else pendingWaiters.push(waiter);
      }
      messageWaiters.push(...pendingWaiters);
      const fulfill = () => route.fulfill({ json: {
        request_id: JSON.parse(route.request().postData() ?? "{}").request_id,
        status: "completed",
        answer: languageCase.answer,
        language_preference: { language_tag: languageCase.tag, source: "explicit", revision: 1 },
        presentation: {
          language_tag: languageCase.tag, direction: languageCase.direction, preference_revision: 1,
          labels: { send: "Send", copy: languageCase.copy, copied: "Copied", check_status: "Check status" },
          labels_fallback: true,
          freshness: eligibility === "stale" ? "stale" : "current", receipt_id: "fixture-receipt",
        },
        answer_eligibility: eligibility,
        evidence: [], unknowns: [], media: [],
        ...(includeBrief ? { guest_brief: { brief_version: 1,
          dates: { check_in: null, check_out: null, nights: null },
          party: { adults: 2, children: [] }, pending_fields: [] } } : {}),
      } });
      if (delaySecondMessage && messages === 2) {
        await new Promise((resolve) => { releaseDelayed = async () => { try { await fulfill(); } catch {} resolve(); }; });
      } else await fulfill();
    } else if (path.endsWith("/freshness")) {
      await route.fulfill({ json: { status: "current" } });
    } else {
      await route.fulfill({ status: 404, json: { error: { code: "offline_fixture_miss", message: "Unmocked API path" } } });
    }
  });
  return {
    messageCount: () => messages,
    waitForMessageCount,
    releaseDelayed: () => releaseDelayed?.(),
  };
}

async function openChat(browser, { mobile = false, eligibility = "current", clipboard = "normal",
  languageCase = CASES[1], delaySecondMessage = false, includeBrief = false } = {}) {
  const context = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true } : {});
  if (clipboard === "normal") await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: baseUrl });
  const page = await context.newPage();
  if (clipboard === "denied") {
    await page.addInitScript(() => {
      Object.defineProperty(Navigator.prototype, "clipboard", {
        configurable: true,
        value: { writeText: async () => { throw new DOMException("denied", "NotAllowedError"); } },
      });
    });
  } else if (clipboard === "unsupported") {
    await page.addInitScript(() => {
      Object.defineProperty(Navigator.prototype, "clipboard", { configurable: true, value: undefined });
      Object.defineProperty(window, "getSelection", { configurable: true, value: undefined });
    });
  }
  const api = await routeApi(page, { eligibility, languageCase, delaySecondMessage, includeBrief });
  await page.goto(`${baseUrl}/hotels/harbor-city-demo/chat`);
  await page.getByLabel("Your question").waitFor();
  return { context, page, api };
}

const browser = await chromium.launch({ headless: true, channel: "chrome" });
try {
  const raceOnly = process.env.STAYLEAD_BROWSER_FROM === "races";
  const scriptOnly = process.env.STAYLEAD_BROWSER_FROM === "rtl-script";
  if (!raceOnly && !scriptOnly) {
  for (const languageCase of CASES) {
    for (const mobile of [false, true]) {
      const { context, page } = await openChat(browser, { mobile, languageCase });
      await page.getByLabel("Your question").fill("请告诉我早餐时间 / 08:30");
      await page.getByRole("button", { name: /Send|发送/ }).click();
      const answerCard = page.locator(".message-assistant").last();
      const answerNode = answerCard.locator(".answer-copy-source");
      await answerNode.getByText(languageCase.answer, { exact: true }).waitFor();
      assert.equal(await answerNode.evaluate((node) => node.textContent), languageCase.answer);
      assert.equal(await answerCard.getAttribute("lang"), languageCase.tag);
      assert.equal(await answerCard.getAttribute("dir"), languageCase.direction);
      assert.equal(await answerCard.getAttribute("data-answer-eligibility"), "current");
      assert.equal(await answerCard.getAttribute("data-copy-eligible"), "true");
      assert.equal(await page.locator("html").evaluate((node) => node.scrollWidth <= node.clientWidth), true);
      assert.equal(await answerCard.evaluate((node) => node.scrollWidth <= node.clientWidth), true);
      const fallbackNoticeCount = await answerCard.getByText("Some interface labels are shown in English because translations are unavailable.").count();
      assert.equal(fallbackNoticeCount, languageCase.tag.split("-")[0] === "en" ? 0 : 1);
      const copyButton = answerCard.getByRole("button", { name: languageCase.copy });
      await copyButton.focus();
      await page.keyboard.press("Enter");
      await answerCard.locator(".copy-status[data-copy-result='copied']").waitFor();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), languageCase.answer);
      await context.close();
    }
  }

  const { context: deniedContext, page: deniedPage } = await openChat(browser, { clipboard: "denied", languageCase: CASES[1] });
  await deniedPage.getByLabel("Your question").fill("请复制答案");
  await deniedPage.getByRole("button", { name: /Send|发送/ }).click();
  const deniedCard = deniedPage.locator(".message-assistant").last();
  await deniedCard.getByRole("button", { name: CASES[1].copy }).click();
  await deniedCard.locator(".copy-status[data-copy-result='selection_fallback']").waitFor();
  assert.equal(await deniedPage.evaluate(() => window.getSelection()?.toString()), CASES[1].answer);
  await deniedContext.close();

  const { context: unsupportedContext, page: unsupportedPage } = await openChat(browser, { clipboard: "unsupported", languageCase: CASES[1] });
  await unsupportedPage.getByLabel("Your question").fill("请复制答案");
  await unsupportedPage.getByRole("button", { name: /Send|发送/ }).click();
  const unsupportedCard = unsupportedPage.locator(".message-assistant").last();
  await unsupportedCard.getByRole("button", { name: CASES[1].copy }).click();
  await unsupportedCard.locator(".copy-status[data-copy-result='unsupported']").waitFor();
  await unsupportedContext.close();

  const { context: pendingContext, page: pendingPage } = await openChat(browser, { eligibility: "pending" });
  await pendingPage.getByLabel("Your question").fill("请查看待处理答案");
  await pendingPage.getByRole("button", { name: /Send|发送/ }).click();
  const pendingCard = pendingPage.locator(".message-assistant").last();
  assert.equal(await pendingCard.getAttribute("data-answer-eligibility"), "pending");
  assert.equal(await pendingCard.getByRole("button", { name: CASES[1].copy }).isDisabled(), true);
  await pendingContext.close();

  const { context: staleContext, page: stalePage, api: staleApi } = await openChat(browser, { eligibility: "stale", languageCase: CASES[1] });
  await stalePage.getByLabel("Your question").fill("请查看旧答案");
  await stalePage.getByRole("button", { name: /Send|发送/ }).click();
  const staleCard = stalePage.locator(".message-assistant").last();
  const staleCopy = staleCard.getByRole("button", { name: CASES[1].copy });
  assert.equal(await staleCopy.isDisabled(), true);
  assert.equal(staleApi.messageCount(), 1);
  await staleContext.close();

  }

  if (!scriptOnly) {
  const { context: pendingOldContext, page: pendingOldPage, api: pendingApi } = await openChat(browser, {
    languageCase: CASES[1], delaySecondMessage: true,
  });
  await pendingOldPage.getByLabel("Your question").fill("第一条问题");
  await pendingOldPage.getByRole("button", { name: /Send|发送/ }).click();
  const oldCard = pendingOldPage.locator(".message-assistant").first();
  await oldCard.getByRole("button", { name: CASES[1].copy }).waitFor();
  await pendingOldPage.getByLabel("Your question").fill("第二条问题");
  await pendingOldPage.getByRole("button", { name: /Send|发送/ }).click();
  assert.equal(await oldCard.getByRole("button", { name: CASES[1].copy }).isDisabled(), true);
  await pendingApi.waitForMessageCount(2);
  assert.equal(pendingApi.messageCount(), 2);
  await pendingApi.releaseDelayed();
  const newCard = pendingOldPage.locator(".message-assistant").last();
  await pendingOldPage.waitForFunction(() => {
    const cards = document.querySelectorAll(".message-assistant");
    return cards.item(cards.length - 1)?.getAttribute("data-copy-eligible") === "true";
  });
  assert.equal(await newCard.getAttribute("data-copy-eligible"), "true");
  assert.equal(await oldCard.getByRole("button", { name: CASES[1].copy }).isDisabled(), true);
  await pendingOldContext.close();

  const { context: scopeContext, page: scopePage, api: scopeApi } = await openChat(browser, {
    languageCase: CASES[1], delaySecondMessage: true,
  });
  await scopePage.getByLabel("Your question").fill("当前会话答案");
  await scopePage.getByRole("button", { name: /Send|发送/ }).click();
  await scopePage.locator(".message-assistant").waitFor();
  await scopePage.getByLabel("Your question").fill("等待中的旧会话请求");
  await scopePage.getByRole("button", { name: /Send|发送/ }).click();
  await scopeApi.waitForMessageCount(2);
  await scopePage.goto(`${baseUrl}/hotels/lagoon-family-demo/chat`);
  await scopePage.getByLabel("Your question").waitFor();
  assert.equal(await scopePage.locator(".message-assistant").count(), 0);
  assert.equal(scopeApi.messageCount(), 2);
  await scopeApi.releaseDelayed();
  await scopePage.waitForLoadState("networkidle");
  assert.equal(await scopePage.locator(".message-assistant").count(), 0);
  await scopeContext.close();
  }

  if (scriptOnly) {
    const requestedTag = process.env.STAYLEAD_BROWSER_LANGUAGE ?? "az-Arab";
    const selectedLanguageCase = requestedTag === EXPLICIT_SCRIPT_CASE.tag
      ? EXPLICIT_SCRIPT_CASE
      : CASES.find((candidate) => candidate.tag === requestedTag);
    assert.ok(selectedLanguageCase, `No browser language fixture for ${requestedTag}`);
    for (const languageCase of [selectedLanguageCase]) {
      const { context, page } = await openChat(browser, { languageCase, includeBrief: true });
      await page.getByLabel("Your question").fill("مرحباً 08:30");
      await page.getByRole("button", { name: /Send|发送/ }).click();
      const answerCard = page.locator(".message-assistant").last();
      await answerCard.locator(".answer-copy-source").waitFor();
      assert.equal(await page.locator("main.chat-shell").getAttribute("lang"), languageCase.tag);
      assert.equal(await page.locator("main.chat-shell").getAttribute("dir"), "rtl");
      const brief = page.locator(`.chat-header > div[lang="${languageCase.tag}"]`);
      assert.equal(await brief.getAttribute("dir"), "rtl");
      assert.equal(await answerCard.getAttribute("lang"), languageCase.tag);
      assert.equal(await answerCard.getAttribute("dir"), "rtl");
      await context.close();
    }
  }

  const result = raceOnly
    ? { status: "PASS", mode: "races", checks_run: ["newer-pending-turn-disables-older-answer", "session-scope-navigation-clears-answer", "late-old-scope-response-ignored"] }
    : scriptOnly ? { status: "PASS", mode: "rtl-script", language: process.env.STAYLEAD_BROWSER_LANGUAGE ?? "az-Arab",
      checks_run: ["main-brief-answer-direction-consistency"] }
      : { status: "PASS", mode: "full", checks_run: ["six-language-tags", "desktop-and-mobile", "exact-rendered-clipboard-text", "keyboard-activation", "clipboard-selection-fallback", "unsupported-clipboard", "pending-and-stale-answer-blocked", "newer-pending-turn-disables-older-answer", "session-scope-navigation-clears-answer", "late-old-scope-response-ignored", "overflow"] };
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
