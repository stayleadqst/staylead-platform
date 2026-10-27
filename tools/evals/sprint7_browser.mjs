#!/usr/bin/env node
/**
 * Production-browser acceptance driver for the pinned Sprint 7 nine turns.
 * It sends each guest utterance once through the real UI, follows the real
 * API, persists one option selection with zero model calls, then stops on the
 * first blocking failure. It writes only sanitized text and local screenshots
 * beneath /private/tmp. No automatic retry, resume, model fixture, or Grok.
 *
 * Run only after the coordinator creates a fresh authorized private state and
 * starts sprint7_runtime.py. This script never creates or resets that state.
 */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";

const repo = process.cwd();
const top = path.resolve(repo, "../..");
const casesPath = path.join(top, "validation/sprint-7-execution-20261026/live-cases-proposed.json");
const oraclePath = path.join(top, "validation/sprint-7-execution-20261026/independent-expected-facts.json");
const cases = JSON.parse(await fs.readFile(casesPath, "utf8"));
const oracle = JSON.parse(await fs.readFile(oraclePath, "utf8"));
const RUN_ID = "s7-room-advice-20261026-batch1";
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const sha = (value) => createHash("sha256").update(value).digest("hex");
const envPath = (key) => {
  const value = process.env[key];
  assert(value && path.isAbsolute(value) && value.startsWith("/private/tmp/"), `${key} must point under /private/tmp`);
  return value;
};

assert(cases.run_id === RUN_ID && cases.cases?.length === 9, "Pinned Sprint 7 proposal is missing or changed");
assert(cases.proposed_max_guest_turns === 9 && cases.proposed_max_requests === 18
  && cases.max_calls_per_turn === 2 && cases.provider_timeout_seconds === 25
  && cases.turn_timeout_seconds === 45 && cases.output_cap === 700
  && cases.model === "gpt-6-luna" && cases.effort === "low"
  && cases.no_automatic_retry === true && cases.stop_at_first_blocking_failure === true,
"Sprint 7 proposal bounds changed");
assert(oracle.synthetic === true && Array.isArray(oracle.global_invariants), "Independent oracle is not pinned");
const dataRoot = path.join(repo, "fixtures/hospitality/knowledge-v1");
const sourceData = {};
for (const name of ["properties.json", "sources.json", "facts.json", "manifest.json"]) {
  const raw = await fs.readFile(path.join(dataRoot, name));
  assert(sha(raw) === oracle.source_files?.[name], `Independent oracle source hash changed: ${name}`);
  sourceData[name] = JSON.parse(raw.toString("utf8"));
}
const hotelIdBySlug = {
  "harbor-city-demo": "HTL-CITY01", "lagoon-family-demo": "HTL-BEACH02", "pine-ridge-demo": "HTL-RETREAT03",
};
const roomRates = Object.fromEntries(Object.entries(oracle.room_rates ?? {}));
const expectedRoomSubtotals = {
  1: { "CITY-STD": 5_400_000 },
  2: { "CITY-STD": 5_400_000, "CITY-TWN": 5_850_000, "CITY-FAM": 8_700_000 },
  3: { "CITY-TWN": 5_850_000 },
  4: { "BEACH-GDN": 5_200_000, "BEACH-FAM": 7_600_000, "BEACH-POOL": 9_000_000 },
  5: { "BEACH-GDN": 5_200_000, "BEACH-FAM": 7_600_000, "BEACH-POOL": 9_000_000 },
  6: { "BEACH-GDN": 5_200_000, "BEACH-FAM": 7_600_000, "BEACH-POOL": 9_000_000 },
  8: { "PINE-LOFT": 4_400_000, "PINE-GARDEN": 5_000_000, "PINE-CABIN": 8_200_000 },
};
const sources = sourceData["sources.json"];
assert(Array.isArray(sources), "Pinned source catalog is not an array");
const sourceOwner = new Map(sources.map((item) => [item.source_id, item.hotel_id]));
if (process.argv.includes("--oracle-loader-smoke")) {
  console.log(JSON.stringify({ status: "offline-source-loader-ok", source_count: sources.length,
    source_owner_count: sourceOwner.size, no_browser: true, no_api_or_model: true }));
  process.exit(0);
}
assert(process.env.STAYLEAD_LIVE_EVAL === "1", "STAYLEAD_LIVE_EVAL=1 is required; no browser/API/model request was sent");
const expectedBrief = {
  1: { adults: 1, children: [], check_in: "2026-11-10", check_out: "2026-11-13", nights: 3 },
  2: { adults: 2, children: [], check_in: "2026-11-10", check_out: "2026-11-13", nights: 3 },
  3: { adults: 2, children: [], check_in: "2026-11-10", check_out: "2026-11-13", nights: 3 },
  4: { adults: 2, children: [null], check_in: "2026-11-10", check_out: "2026-11-12", nights: 2 },
  5: { adults: 2, children: [7], check_in: "2026-11-10", check_out: "2026-11-12", nights: 2 },
  6: { adults: 2, children: [12], check_in: "2026-11-10", check_out: "2026-11-12", nights: 2 },
  7: { adults: 1, children: [7], check_in: "2026-11-10", check_out: "2026-11-12", nights: 2 },
  8: { adults: 1, children: [8], check_in: "2026-11-10", check_out: "2026-11-12", nights: 2 },
};
const statePath = envPath("STAYLEAD_S7_RUN_STATE");
const stateInfo = await fs.lstat(statePath);
assert(stateInfo.isFile() && !stateInfo.isSymbolicLink() && (stateInfo.mode & 0o777) === 0o600,
  "Private Sprint 7 state must be a regular 0600 file");
const runState = JSON.parse(await fs.readFile(statePath, "utf8"));
assert(runState.run_id === RUN_ID && runState.status === "running"
  && runState.authorized_for_live_calls === true
  && runState.max_guest_turns === 9 && runState.max_codex_requests === 18
  && runState.max_calls_per_turn === 2
  && runState.reserved_guest_turn_budget === 9 && runState.reserved_request_budget === 18,
"No freshly authorized and reserved Sprint 7 state; stopping before browser launch");

const moduleUrl = process.env.STAYLEAD_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.STAYLEAD_PLAYWRIGHT_MODULE).href : "playwright";
const { chromium } = await import(moduleUrl);
const webUrl = (process.env.STAYLEAD_S7_WEB_URL ?? "http://127.0.0.1:13000").replace(/\/$/, "");
const apiUrl = (process.env.STAYLEAD_S7_API_URL ?? "http://127.0.0.1:18087").replace(/\/$/, "");
const runDir = `/private/tmp/staylead-s7-browser-${RUN_ID}`;
await fs.mkdir(runDir, { mode: 0o700 }); // refuses reuse; failed run artifacts stay intact
await fs.chmod(runDir, 0o700);
const reportPath = path.join(runDir, "browser-report.json");
async function writePrivateCapture(name, value) {
  const target = path.join(runDir, name);
  const text = JSON.stringify(value, null, 2) + "\n";
  assert(Buffer.byteLength(text, "utf8") <= 64 * 1024, `${name} exceeds the 64 KiB local capture cap`);
  await fs.writeFile(target, text, { flag: "wx", mode: 0o600 });
  await fs.chmod(target, 0o600);
  return target;
}
const report = {
  run_id: RUN_ID, started_at: new Date().toISOString(), candidate_sha256: runState.candidate_sha256,
  live_cases_sha256: sha(await fs.readFile(casesPath)), oracle_sha256: sha(await fs.readFile(oraclePath)),
  browser: "chromium", live: true, mock_api: false, screenshots_local_only: true,
  turns: [], selections: [], failure: null,
};
let browser;
let context;
let page;
const sessions = new Map();
let activeHotel = "";
const childIdsByHotel = new Map();
try {
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  page = await context.newPage();
  page.on("response", async (response) => {
    const req = response.request();
    if (req.method() !== "POST") return;
    const url = new URL(response.url());
    if (url.pathname.endsWith("/sessions")) {
      try {
        const body = await response.json();
        if (body.session_id && body.access_token) sessions.set(activeHotel, body);
      } catch { /* the owning turn reports the actionable failure */ }
    }
  });

  const groups = [
    { hotel: "harbor-city-demo", turns: [1, 2, 3] },
    { hotel: "lagoon-family-demo", turns: [4, 5, 6] },
    { hotel: "pine-ridge-demo", turns: [7, 8, 9] },
  ];
  let selectedCity = null;
  for (const group of groups) {
    activeHotel = group.hotel;
    await page.goto(`${webUrl}/hotels/${group.hotel}/chat`, { waitUntil: "domcontentloaded" });
    await page.locator("#guest-question").waitFor({ state: "visible", timeout: 30000 });
    for (const turnNo of group.turns) {
      const testCase = cases.cases[turnNo - 1];
      assert(testCase.turn === turnNo && testCase.hotel_slug === group.hotel, `case ${turnNo} changed hotel/order`);
      const messageResponsePromise = page.waitForResponse((response) =>
        response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/messages"), { timeout: 55000 });
      await page.locator("#guest-question").fill(testCase.utterance);
      await page.locator(".chat-composer button[type='submit']").click();
      const apiResponse = await messageResponsePromise;
      const statusCode = apiResponse.status();
      assert(statusCode >= 200 && statusCode < 300, `turn ${turnNo} API status ${statusCode}`);
      const payload = await apiResponse.json();
      const room = payload.room_advice ?? null;
      if (turnNo <= 3) {
        assert(room?.options?.length > 0, `city-${turnNo} did not produce a feasible room option`);
      }
      let visibleRoom = null;
      if (turnNo !== 9) {
        assert(room && room.result_id && Number.isInteger(room.result_version), `turn ${turnNo} missing persisted room result`);
        assert(room.currentness === "current", `turn ${turnNo} result is not current`);
        assert(room.hotel_id === hotelIdBySlug[group.hotel] && room.session_id && room.config_version && room.dependency_fingerprint,
          `turn ${turnNo} missing scoped result identity/version dependencies`);
        assert(room.availability === "unknown", `turn ${turnNo} made an availability claim`);
        assert(Array.isArray(room.source_refs) && room.source_refs.length > 0,
          `turn ${turnNo} has no source references`);
        for (const sourceRef of room.source_refs) {
          const source = sourceRef.source ?? sourceRef;
          const sourceGeneration = source.source_generation ?? source.hotel_generation;
          assert(source.source_id && source.hotel_id === room.hotel_id
            && sourceOwner.get(source.source_id) === room.hotel_id,
            `turn ${turnNo} contains a cross-hotel or unpinned source reference`);
          assert(sourceGeneration === room.source_generation,
            `turn ${turnNo} source generation does not match the current result`);
        }
        const brief = payload.guest_brief;
        const expected = expectedBrief[turnNo];
        assert(brief?.party?.adults === expected.adults && brief?.party?.children?.length === expected.children.length,
          `turn ${turnNo} canonical guest membership mismatch`);
        if (expected.check_in) assert(brief.dates.check_in === expected.check_in && brief.dates.check_out === expected.check_out
          && brief.dates.nights === expected.nights, `turn ${turnNo} canonical dates/nights mismatch`);
        expected.children.forEach((age, index) => {
          assert(brief.party.children[index].age === age, `turn ${turnNo} child age mismatch`);
        });
        if (brief.party.children.length) {
          const ids = brief.party.children.map((child) => child.member_id);
          const previousIds = childIdsByHotel.get(group.hotel);
          if (previousIds) assert(JSON.stringify(ids) === JSON.stringify(previousIds),
            `turn ${turnNo} changed a child's stable member ID`);
          childIdsByHotel.set(group.hotel, ids);
        }
        const canonicalMembers = new Set([
          ...Array.from({ length: expected.adults }, (_, i) => `adult-${i + 1}`),
          ...brief.party.children.map((child) => child.member_id),
        ]);
        for (const option of room.options ?? []) {
          const ids = (option.assignments ?? []).map((item) => item.member_id);
          assert(ids.length === canonicalMembers.size && new Set(ids).size === ids.length
            && ids.every((id) => canonicalMembers.has(id)), `turn ${turnNo} assignment omitted, duplicated, or invented a guest`);
          if (option.cost?.total !== null && option.cost?.total !== undefined) {
            assert(option.cost.status === "complete", `turn ${turnNo} exposed a total marked incomplete`);
          }
          const rates = option.rooms.map((item) => roomRates[item.room_type_id]);
          if (rates.every((rate) => Number.isInteger(rate)) && Number.isInteger(brief.dates.nights)) {
            const expectedKnownBase = rates.reduce((sum, rate) => sum + rate, 0) * brief.dates.nights;
            const referenceSubtotal = (option.cost?.breakdown ?? [])
              .filter((line) => /reference rate/i.test(line.label) && line.status === "known")
              .reduce((sum, line) => sum + line.amount, 0);
            assert(referenceSubtotal === expectedKnownBase, `turn ${turnNo} independent room subtotal mismatch`);
            const expectedByRoom = expectedRoomSubtotals[turnNo] ?? {};
            for (const [roomType, amount] of Object.entries(expectedByRoom)) {
              const matchingRooms = option.rooms.filter((item) => item.room_type_id === roomType).length;
              if (matchingRooms > 0) {
                assert(matchingRooms === option.rooms.length && expectedKnownBase === amount,
                  `turn ${turnNo} ${roomType} room count/subtotal differs from independent expected amount`);
              }
            }
          }
          const hasUnknownCost = (option.cost?.breakdown ?? []).some((line) => line.status === "unknown");
          if (hasUnknownCost) assert(option.cost.status === "incomplete" && option.cost.total === null,
            `turn ${turnNo} converted an unknown mandatory charge into a total`);
          for (const check of option.checks ?? []) {
            assert(check.status !== "conflict" || option.fit !== "fit", `turn ${turnNo} certified a conflicting option`);
          }
        }
        await page.locator('[data-testid="room-advice"]').last().waitFor({ state: "visible", timeout: 30000 });
        visibleRoom = page.locator('[data-testid="room-advice"]').last();
        assert(await visibleRoom.getAttribute("data-room-advice") === "true", `turn ${turnNo} was not rendered by the room-advice consumer`);
      }
      if (turnNo === 2) {
        const lang = (await visibleRoom.getAttribute("lang"))?.toLowerCase() ?? "";
        assert(lang.startsWith("zh") && /[\u3400-\u9fff]/u.test(await visibleRoom.innerText()),
          "city-2 Chinese UI language/content missing");
      }
      if (turnNo >= 4 && turnNo <= 6) {
        assert(!(room.options ?? []).some((option) => option.cost?.status === "complete"),
          `beach-${turnNo} falsely certified complete charges despite unknown child fees`);
      }
      if (turnNo === 7) {
        const claimsAccess = (room.options ?? []).some((option) =>
          (option.checks ?? []).some((check) => /access|wheelchair|bathroom/i.test(check.code) && check.status === "pass"));
        assert(!claimsAccess, "retreat-7 certified unverified accessibility");
      }
      const answer = page.locator(".turn").last();
      await answer.waitFor({ state: "visible" });
      const visibleText = await page.locator(".turn").last().innerText();
      const capture = JSON.stringify({ case_id: testCase.id, utterance: testCase.utterance,
        independent_expected: testCase.independent_expected, api_response: payload, visible_text: visibleText });
      assert(Buffer.byteLength(capture, "utf8") <= 64 * 1024, `turn ${turnNo} private capture exceeds 64 KiB`);
      const capturePath = path.join(runDir, `turn-${String(turnNo).padStart(2, "0")}-synthetic.json`);
      await writePrivateCapture(path.basename(capturePath), JSON.parse(capture));
      report.turns.push({ turn: turnNo, case_id: testCase.id, hotel_slug: group.hotel,
        http_status: statusCode, request_id_sha256: sha(payload.request_id ?? ""),
        answer_sha256: sha(payload.answer ?? ""), private_capture: path.basename(capturePath),
        result_id_sha256: room ? sha(room.result_id) : null,
        result_version: room?.result_version ?? null, brief_version: room?.brief_version ?? payload.guest_brief?.brief_version ?? null,
        source_generation: room?.source_generation ?? null, config_version: room?.config_version ?? null,
        source_ref_count: room?.source_refs?.length ?? 0, option_count: room?.options?.length ?? 0,
        cost_statuses: (room?.options ?? []).map((option) => option.cost?.status ?? "missing"),
        language: visibleRoom ? await visibleRoom.getAttribute("lang") : null, currentness: room?.currentness ?? null });

      if (turnNo === 2) {
        const session = sessions.get(group.hotel);
        assert(session?.access_token && session.session_id === room.session_id,
          "city session receipt unavailable for the selection-only API action");
        const optionId = room.options[0].option_id;
        const beforeState = JSON.parse(await fs.readFile(statePath, "utf8"));
        const selectionResponsePromise = page.waitForResponse((response) =>
          response.request().method() === "POST"
          && new URL(response.url()).pathname.includes(`/room-advice/${room.result_id}/selection`), { timeout: 15000 });
        await visibleRoom.locator(`[data-testid="room-select"][data-room-select="${optionId}"]`).click();
        const selectionResponse = await selectionResponsePromise;
        assert(selectionResponse.ok(), `selection-only API returned ${selectionResponse.status()}`);
        const selection = await selectionResponse.json();
        const latestResponse = await fetch(`${apiUrl}/v1/guest/sessions/${session.session_id}/room-advice`, {
          headers: { authorization: `Bearer ${session.access_token}` },
        });
        assert(latestResponse.ok, `GET latest room advice returned ${latestResponse.status}`);
        const latest = await latestResponse.json();
        assert(selection.option_id === optionId && selection.result_version === room.result_version
          && latest.selection?.option_id === optionId && latest.currentness === "current",
        "selected option/result version did not persist as current");
        report.selections.push({ hotel_slug: group.hotel, result_version: room.result_version,
          option_id_sha256: sha(optionId), persisted: true, model_calls: 0 });
        await writePrivateCapture("city-selection-latest.json", { selection, latest });
        const afterState = JSON.parse(await fs.readFile(statePath, "utf8"));
        assert(afterState.codex_requests === beforeState.codex_requests
          && afterState.guest_turns === beforeState.guest_turns,
        "selection-only request consumed a guest turn or model-request reservation");
        selectedCity = { result_version: room.result_version, option_id: optionId };
      }
      if (turnNo === 3 && selectedCity) {
        const cityTurns = page.locator(".turn");
        const oldCityTurn = cityTurns.nth(1);
        const currentCityTurn = cityTurns.nth(2);
        const oldCityCard = oldCityTurn.locator('[data-testid="room-advice"]');
        const staleBanner = oldCityCard.locator('[data-testid="room-advice-stale"]');
        await staleBanner.waitFor({ state: "visible", timeout: 15000 });
        const oldOptionButton = oldCityCard.locator(
          `[data-testid="room-select"][data-room-select="${selectedCity.option_id}"]`,
        );
        assert(await oldOptionButton.isDisabled(), "previously selected city option remained selectable after the edit");
        const currentCityCard = currentCityTurn.locator('[data-testid="room-advice"]');
        assert(await currentCityCard.count() === 1, "edited city recommendation card is missing");
        const currentOptionButton = currentCityCard.locator(
          `[data-testid="room-select"][data-room-select="${room.options[0].option_id}"]`,
        );
        const currentOptionElement = await currentOptionButton.elementHandle();
        assert(currentOptionElement, "new current city option button is missing");
        await page.waitForFunction((button) => button instanceof HTMLButtonElement && !button.disabled,
          currentOptionElement, { timeout: 15000 });
        assert(!(await currentOptionButton.isDisabled()), "new current city option is not selectable");
        const session = sessions.get(group.hotel);
        const latestResponse = await fetch(`${apiUrl}/v1/guest/sessions/${session.session_id}/room-advice`, {
          headers: { authorization: `Bearer ${session.access_token}` },
        });
        assert(latestResponse.ok, "latest city result could not be read after the edit");
        const latest = await latestResponse.json();
        assert(latest.result_version > selectedCity.result_version && latest.currentness === "current",
          "city edit did not replace the prior selected result with a current version");
        await writePrivateCapture("city-edit-latest.json", latest);
        report.city_edit = { previous_selected_version: selectedCity.result_version,
          latest_version: latest.result_version, previous_selection_not_current: latest.selection?.result_version !== selectedCity.result_version,
          old_card_stale_banner_visible: true, old_option_disabled: true, new_option_enabled: true };
      }
      if (turnNo === 9) {
        const session = sessions.get(group.hotel);
        assert(session?.session_id, "retreat guest session capture failed");
        const latestResponse = await fetch(`${apiUrl}/v1/guest/sessions/${session.session_id}/room-advice`, {
          headers: { authorization: `Bearer ${session.access_token}` },
        });
        assert(latestResponse.ok, "latest room result unavailable after the booking-channel request");
        const latest = await latestResponse.json();
        assert(latest.currentness === "current" && latest.result_version === report.turns.at(-2).result_version,
          "booking-channel question unexpectedly replaced or staled the latest room result");
        await writePrivateCapture("retreat-booking-latest.json", latest);
        const bookingTurn = page.locator(".turn").last();
        const bookingChannel = bookingTurn.locator(".booking-channel");
        const link = bookingChannel.locator("a");
        assert(await link.count() === 1, "trusted booking anchor is missing");
        const href = await link.getAttribute("href");
        assert(href === session.hotel.booking_channel?.destination_url
          && href.startsWith("https://") && !new URL(href).search && !new URL(href).hash
          && href.includes(group.hotel), "booking destination is unsafe or not hotel-scoped");
        assert((await link.getAttribute("rel") ?? "").split(/\s+/).includes("noopener")
          && await link.getAttribute("referrerpolicy") === "no-referrer", "booking link leaks opener/referrer");
        const disclosure = await bookingChannel.innerText();
        const bookingBoundaryPhrases = [
          "does not reserve a room or make a payment",
          "không giữ phòng hoặc thanh toán",
          "不会预留客房或付款",
          "部屋の確保や支払いは行われません",
        ];
        assert(bookingBoundaryPhrases.some((phrase) => disclosure.includes(phrase)),
          "booking boundary disclosure missing");
      }
    }
    const screenshot = path.join(runDir, `${group.hotel}-desktop.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    await fs.chmod(screenshot, 0o600);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('[data-testid="room-advice"]').last().waitFor({ state: "visible", timeout: 10000 });
  const mobileSize = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth, body: document.body.scrollWidth,
  }));
  assert(mobileSize.body <= mobileSize.viewport + 1, "mobile layout overflows horizontally");
  const mobileShot = path.join(runDir, "retreat-mobile.png");
  await page.screenshot({ path: mobileShot, fullPage: true });
  await fs.chmod(mobileShot, 0o600);

  report.mobile_layout = { ...mobileSize, no_horizontal_overflow: true };
  const finalState = JSON.parse(await fs.readFile(statePath, "utf8"));
  assert(finalState.guest_turns === 9 && finalState.codex_requests >= 9
    && finalState.codex_requests <= 18, "persistent live counters do not match the nine-turn bounded batch");
  report.counters = { guest_turns: finalState.guest_turns, codex_requests: finalState.codex_requests,
    max_guest_turns: finalState.max_guest_turns, max_codex_requests: finalState.max_codex_requests };
  report.completed_at = new Date().toISOString();
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  console.log(JSON.stringify({ run_id: RUN_ID, turns: report.turns.length, report: reportPath, status: "completed" }));
} catch (error) {
  const failureMessage = String(error?.message ?? "blocking failure")
    .replace(/Bearer\s+[^\s,;]+/gi, "Bearer <redacted>")
    .replace(/https?:\/\/[^\s"']+/gi, "<url-redacted>")
    .replace(/(token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,;]+/gi, "$1=<redacted>");
  report.failure = { name: error?.name ?? "Error", message: failureMessage.slice(0, 240) };
  try {
    const failedState = JSON.parse(await fs.readFile(statePath, "utf8"));
    report.counters = { guest_turns: failedState.guest_turns, codex_requests: failedState.codex_requests,
      max_guest_turns: failedState.max_guest_turns, max_codex_requests: failedState.max_codex_requests,
      status: failedState.status };
  } catch { report.counters = { unavailable: true }; }
  report.completed_at = new Date().toISOString();
  try { await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx", mode: 0o600 }); } catch { /* preserve an earlier failed report */ }
  console.error(JSON.stringify({ run_id: RUN_ID, turns_completed: report.turns.length,
    failure: report.failure, report: reportPath }));
  process.exitCode = 1;
} finally {
  await context?.close();
  await browser?.close();
}
