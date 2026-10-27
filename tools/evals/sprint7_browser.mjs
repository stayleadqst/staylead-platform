#!/usr/bin/env node
/**
 * Bounded continuation for unchanged approved Pine cases 6-7 after the sealed 3/5 parent run.
 * Starts one fresh Pine session; submits each remaining approved utterance once.
 * Selection/replay/GET checks use zero provider requests; stop at first blocker.
 * Screenshots and turn payloads remain private beneath /private/tmp.
 */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { browserRunDirectory, retainsTwoHardAccessibilityNeeds,
  roomAdviceHardChecksConsistent, hasExactBedSharingConsent,
  selectionOptionForAcceptanceTurn } from "./sprint7_browser_helpers.mjs";
import { validateSourceRefs } from "./sprint7_source_refs.mjs";

const repo = process.cwd();
const RUN_ID = "s7-room-advice-20261026-reacceptance1-cont2";
const CASE_RUN_ID = "s7-room-advice-20261026-reacceptance1";
const PARENT_RUN_ID = "s7-room-advice-20261026-reacceptance1-cont1";
const APPROVED_CASE_TURNS = [6, 7];
const BUDGET_TURNS = [4, 5];
const HOTEL_ID = { "harbor-city-demo": "HTL-CITY01", "lagoon-family-demo": "HTL-BEACH02", "pine-ridge-demo": "HTL-RETREAT03" };
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const sha = (value) => createHash("sha256").update(value).digest("hex");
const envPath = (key) => {
  const value = process.env[key];
  assert(value && path.isAbsolute(value) && value.startsWith("/private/tmp/"), `${key} must point under /private/tmp`);
  return value;
};

if (process.argv.includes("--offline-harness-smoke")) {
  console.log(JSON.stringify({ status: "offline-harness-smoke-ok", batch_namespace: RUN_ID,
    case_namespace: CASE_RUN_ID, parent_namespace: PARENT_RUN_ID, approved_case_turns: APPROVED_CASE_TURNS,
    guest_turn_cap: 7, request_cap: 14,
    seed_counters: { guest_turns: 3, codex_requests: 5 }, no_browser: true, no_api_or_model: true }));
  process.exit(0);
}
assert(process.env.STAYLEAD_LIVE_EVAL === "1", "STAYLEAD_LIVE_EVAL=1 is required; no browser/API/model request was sent");
const statePath = envPath("STAYLEAD_S7_RUN_STATE");
const configPath = envPath("STAYLEAD_S7_RUNTIME_CONFIG");
for (const file of [statePath, configPath]) {
  const info = await fs.lstat(file);
  assert(info.isFile() && !info.isSymbolicLink() && (info.mode & 0o777) === 0o600,
    "Private reacceptance state/config must be regular 0600 files");
}
const state = JSON.parse(await fs.readFile(statePath, "utf8"));
const config = JSON.parse(await fs.readFile(configPath, "utf8"));
assert(state.run_id === RUN_ID && config.run_id === RUN_ID
  && state.candidate_sha256 === config.candidate_sha256 && state.matrix_sha256 === config.matrix_sha256,
"Private config/state is not the authorized reacceptance1-cont2 namespace");
const casesPath = process.env.STAYLEAD_S7_LIVE_CASES ?? config.live_cases_path;
const oraclePath = config.oracle_path;
assert(path.resolve(casesPath) === path.resolve(config.live_cases_path), "Case file differs from the candidate pin");
const casesRaw = await fs.readFile(casesPath);
const oracleRaw = await fs.readFile(oraclePath);
const cases = JSON.parse(casesRaw.toString("utf8"));
const oracle = JSON.parse(oracleRaw.toString("utf8"));
assert(sha(casesRaw) === state.matrix_sha256 && sha(oracleRaw) === config.oracle_sha256,
  "Approved case matrix or independent oracle changed");
assert(cases.run_id === CASE_RUN_ID && cases.authorized_for_live_calls === true && cases.cases?.length === 7,
  "Approved reacceptance1 case matrix is invalid");
assert(cases.proposed_max_guest_turns === 7 && cases.proposed_max_requests === 14
  && cases.max_calls_per_turn === 2 && cases.provider_timeout_seconds === 25
  && cases.turn_timeout_seconds === 45 && cases.output_cap === 700
  && cases.model === "gpt-6-luna" && cases.effort === "low"
  && cases.no_automatic_retry === true && cases.stop_at_first_blocking_failure === true,
"Approved global caps or stop rules changed");
assert(state.status === "running" && state.authorized_for_live_calls === true
  && state.max_guest_turns === 7 && state.max_codex_requests === 14 && state.max_calls_per_turn === 2
  && state.reserved_guest_turn_budget === 7 && state.reserved_request_budget === 14
  && state.guest_turns === 3 && state.codex_requests === 5,
"Continuation must seed only the sealed parent 3/5 counters and preserve global bounds");
const prior = config.prior_allocation;
assert(prior?.run_id === "s7-room-advice-20261026-batch2-cont6"
  && prior.state_sha256 === "7067736dec93d298942e5ca52a87df36e3f4b1d3ec5b7f4e9ad8a007c1ee92bd"
  && prior.guest_turns === 9 && prior.codex_requests === 16 && prior.lifetime_prior_requests === 17
  && prior.status === "closedimmutable", "Prior allocation receipt does not match the sealed completed run");
const continuation = config.continuation;
assert(continuation?.parent_run_id === PARENT_RUN_ID
  && continuation.parent_state_path === "/private/tmp/staylead-s7-reacceptance1-cont1-state.json"
  && continuation.parent_state_sha256 === "91368ee5d096c544bdfa1c8b2dda8b004f85b1d46f745abfd0d3042e50338e75"
  && continuation.parent_guest_turns === 3 && continuation.parent_codex_requests === 5
  && JSON.stringify(continuation.approved_case_turns) === JSON.stringify(APPROVED_CASE_TURNS)
  && JSON.stringify(continuation.budget_turns) === JSON.stringify(BUDGET_TURNS)
  && continuation.max_new_guest_turns === 2 && continuation.max_new_requests === 4,
"Continuation mapping or remaining allowance differs from the exact approved receipt");
assert(oracle.synthetic === true && Array.isArray(oracle.global_invariants), "Independent oracle is not pinned");
const dataRoot = path.join(repo, "fixtures/hospitality/knowledge-v1");
const sourceData = {};
for (const name of ["properties.json", "sources.json", "facts.json", "manifest.json"]) {
  const raw = await fs.readFile(path.join(dataRoot, name));
  assert(sha(raw) === oracle.source_files?.[name], `Oracle source hash changed: ${name}`);
  sourceData[name] = JSON.parse(raw.toString("utf8"));
}
const publicHotelConfig = new Map(sourceData["properties.json"].properties.map((item) => [item.hotel_id, item]));
const sourceOwner = new Map(Object.entries(oracle.source_bindings ?? {}));
const factOwner = new Map(Object.entries(oracle.projected_fact_owners ?? {}));
const fixtureSourceOwner = new Map(sourceData["sources.json"].map((item) => [item.source_id, item]));
assert(sourceOwner.size > 0 && factOwner.size > 0, "Oracle lacks source/fact ownership mappings");
for (const [sourceId, binding] of sourceOwner) {
  const fixture = fixtureSourceOwner.get(sourceId);
  assert(fixture && fixture.hotel_id === binding.hotel_id && fixture.version === binding.version
    && /^[a-f0-9]{64}$/u.test(binding.expected_hash ?? "") && Number.isInteger(binding.source_generation),
  `Oracle source binding invalid for ${sourceId}`);
}
for (const [factId, binding] of factOwner) {
  assert(factId && sourceOwner.get(binding.source_id)?.hotel_id === binding.hotel_id,
    "Oracle projected fact owner is not source-bound");
}
const rates = oracle.room_rates ?? {};
const expectedBase = {
  "CITY-STD": 5_400_000, "CITY-TWN": 5_850_000, "CITY-FAM": 8_700_000,
  "BEACH-GDN": 5_200_000, "BEACH-FAM": 7_600_000, "BEACH-POOL": 9_000_000,
  "PINE-LOFT": 4_400_000, "PINE-GARDEN": 5_000_000, "PINE-CABIN": 8_200_000,
};
for (const [room, subtotal] of Object.entries(expectedBase)) {
  const nightly = rates[room];
  assert(Number.isInteger(nightly) && nightly > 0 && (room.startsWith("CITY") ? 3 : 2) * nightly === subtotal,
    `Pinned oracle does not support expected stay subtotal for ${room}`);
}

const moduleUrl = process.env.STAYLEAD_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.STAYLEAD_PLAYWRIGHT_MODULE).href : "playwright";
const { chromium } = await import(moduleUrl);
const webUrl = (process.env.STAYLEAD_S7_WEB_URL ?? "http://127.0.0.1:13000").replace(/\/$/u, "");
const apiUrl = (process.env.STAYLEAD_S7_API_URL ?? "http://127.0.0.1:18087").replace(/\/$/u, "");
const runDir = browserRunDirectory(RUN_ID, process.env.STAYLEAD_S7_BROWSER_ATTEMPT ?? "r1");
await fs.mkdir(runDir, { mode: 0o700 });
await fs.chmod(runDir, 0o700);
const reportPath = path.join(runDir, "browser-report.json");
async function writePrivateCapture(name, value) {
  const target = path.join(runDir, name);
  const text = JSON.stringify(value, null, 2) + "\n";
  assert(Buffer.byteLength(text, "utf8") <= 64 * 1024, `${name} exceeds the private capture cap`);
  await fs.writeFile(target, text, { flag: "wx", mode: 0o600 });
  await fs.chmod(target, 0o600);
  return target;
}
const report = { run_id: RUN_ID, case_run_id: CASE_RUN_ID, started_at: new Date().toISOString(), candidate_sha256: state.candidate_sha256,
  live_cases_sha256: sha(casesRaw), oracle_sha256: sha(oracleRaw), browser: "chromium", live: true,
  mock_api: false, prior_allocation_closed: true, parent_run_id: PARENT_RUN_ID,
  parent_counters: { guest_turns: 3, codex_requests: 5 },
  turns: [], selections: [], failure: null };
let browser;
let context;
let page;
let activeSession;
const sessions = new Map();
const expectedBrief = {
  6: { adults: 1, children: [7], dates: ["2026-11-10", "2026-11-12", 2] },
  7: { adults: 1, children: [8], dates: ["2026-11-10", "2026-11-12", 2] },
};
const childIdsBySession = new Map();
function checkBrief(turnNo, brief) {
  const expected = expectedBrief[turnNo];
  assert(brief?.party?.adults === expected.adults && brief.party.children?.length === expected.children.length,
    `turn ${turnNo} M2 party count differs from pinned case`);
  assert(brief.dates?.check_in === expected.dates[0] && brief.dates?.check_out === expected.dates[1]
    && brief.dates?.nights === expected.dates[2], `turn ${turnNo} M2 date/nights differs from pinned case`);
  for (let index = 0; index < expected.children.length; index += 1) {
    assert(brief.party.children[index].age === expected.children[index], `turn ${turnNo} child age differs`);
  }
  if (turnNo === 6) {
    assert(retainsTwoHardAccessibilityNeeds(brief),
      "pine-6 did not preserve both hard accessibility needs");
    assert(brief.room_requirements?.budget_amount == null, "pine-6 invented a budget");
  }
  if (turnNo === 6 || turnNo === 7) {
    const child = brief.party.children?.[0];
    assert(child?.member_id && brief.party.guardians?.[child.member_id] === "adult-1"
      && hasExactBedSharingConsent(brief, ["adult-1", child.member_id], true),
    `turn ${turnNo} lost the guardian or explicit adult-child bed-sharing consent`);
  }
  if (turnNo === 7) {
    assert(!(brief.room_requirements?.hard_accessibility_needs ?? []).length,
      "pine-7 did not clear the two explicitly relaxed hard access requirements");
  }
  return brief.party.children?.[0]?.member_id ?? null;
}
function checkRoom(turnNo, room, hotelId, brief) {
  assert(room && room.result_id && Number.isInteger(room.result_version) && room.currentness === "current",
    `turn ${turnNo} missing current persisted result`);
  assert(room.hotel_id === hotelId && room.session_id && room.config_version && room.dependency_fingerprint,
    `turn ${turnNo} missing hotel/session/config/dependency identity`);
  assert(room.brief_version === brief.brief_version && room.availability === "unknown",
    `turn ${turnNo} result has stale brief binding or claims availability`);
  assert(roomAdviceHardChecksConsistent(room),
    `turn ${turnNo} exposed options despite a checked hard conflict`);
  assert(validateSourceRefs(room, sourceOwner, factOwner), `turn ${turnNo} source refs failed hotel/version/hash/fact/generation guards`);
  const members = new Set([`adult-1`, ...(brief.party.adults > 1 ? [`adult-2`] : []),
    ...(brief.party.children ?? []).map((child) => child.member_id)]);
  for (const option of room.options ?? []) {
    const assigned = option.assignments ?? [];
    const ids = assigned.map((assignment) => assignment.member_id);
    assert(ids.length === members.size && new Set(ids).size === ids.length
      && ids.every((id) => members.has(id)), `turn ${turnNo} has missing, duplicate, or invented guest assignments`);
    if (option.cost?.total != null) assert(option.cost.status === "complete", `turn ${turnNo} has a total marked incomplete`);
    const roomRates = option.rooms.map((item) => rates[item.room_type_id]);
    if (roomRates.every(Number.isInteger) && Number.isInteger(brief.dates.nights)) {
      const expected = roomRates.reduce((sum, rate) => sum + rate, 0) * brief.dates.nights;
      const nightlySubtotal = roomRates.reduce((sum, rate) => sum + rate, 0);
      assert(option.cost?.nightly_subtotal === nightlySubtotal,
        `turn ${turnNo} nightly reference amount differs from independent source rates`);
      const references = (option.cost?.breakdown ?? []).filter((line) => /reference rate/i.test(line.label) && line.status === "known");
      assert(references.reduce((sum, line) => sum + line.amount, 0) === expected,
        `turn ${turnNo} known room subtotal differs from independent source rates`);
      if (brief.room_requirements?.budget_strength === "hard") {
        assert(expected <= brief.room_requirements.budget_amount,
          `turn ${turnNo} offered a known room subtotal above the explicit hard stay budget`);
      }
      for (const item of option.rooms) {
        const expectedSubtotal = expectedBase[item.room_type_id];
        assert(expectedSubtotal && rates[item.room_type_id] * brief.dates.nights === expectedSubtotal,
          `turn ${turnNo} room base differs from independent rate oracle`);
      }
    }
    if ((option.cost?.breakdown ?? []).some((line) => line.status === "unknown")) {
      assert(option.cost.status === "incomplete" && option.cost.total == null,
        `turn ${turnNo} converted an unknown mandatory fee into a confirmed total`);
    }
  }
  return room;
}
async function selectCurrentOption(turnNo, room, card, session, stateAtSelection) {
  const option = selectionOptionForAcceptanceTurn(turnNo, room);
  if (!option) return null;
  const button = card.locator(`[data-testid="room-select"][data-room-select="${option.option_id}"]`);
  await button.waitFor({ state: "visible", timeout: 15000 });
  assert(!(await button.isDisabled()), `turn ${turnNo} current option is disabled`);
  const selectionResponsePromise = page.waitForResponse((response) => response.request().method() === "POST"
    && new URL(response.url()).pathname.includes(`/room-advice/${room.result_id}/selection`), { timeout: 15000 });
  await button.click();
  const response = await selectionResponsePromise;
  assert(response.ok(), `turn ${turnNo} selection API returned ${response.status()}`);
  const selection = await response.json();
  const latestResponse = await fetch(`${apiUrl}/v1/guest/sessions/${session.session_id}/room-advice`, {
    headers: { authorization: `Bearer ${session.access_token}` },
  });
  assert(latestResponse.ok, `turn ${turnNo} GET latest returned ${latestResponse.status}`);
  const latest = await latestResponse.json();
  assert(selection.result_id === room.result_id && selection.result_version === room.result_version
    && selection.option_id === option.option_id && latest.result_id === room.result_id
    && latest.result_version === room.result_version && latest.currentness === "current"
    && latest.selection?.result_id === room.result_id && latest.selection?.option_id === option.option_id,
  `turn ${turnNo} selection did not persist against the exact current result`);
  const afterState = JSON.parse(await fs.readFile(statePath, "utf8"));
  assert(afterState.codex_requests === stateAtSelection.codex_requests
    && afterState.guest_turns === stateAtSelection.guest_turns,
    "Selection-only API action consumed a turn or model request");
  report.selections.push({ turn: turnNo, result_version: room.result_version, option_id_sha256: sha(option.option_id), model_calls: 0 });
  await writePrivateCapture(`selection-${turnNo}-latest.json`, latest);
  return { option, latest };
}

try {
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  page = await context.newPage();
const groups = [
    { session: "fresh-pine", hotel: "pine-ridge-demo", turns: [6, 7] },
  ];
  for (const group of groups) {
    const hotelId = HOTEL_ID[group.hotel];
    assert(group.turns.every((turnNo) => cases.cases[turnNo - 1].session === group.session
      && cases.cases[turnNo - 1].hotel_slug === group.hotel), `case grouping changed for ${group.session}`);
    const sessionResponsePromise = page.waitForResponse((response) => response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/sessions"), { timeout: 30000 });
    await page.goto(`${webUrl}/hotels/${group.hotel}/chat`, { waitUntil: "domcontentloaded" });
    await page.locator("#guest-question").waitFor({ state: "visible", timeout: 30000 });
    const sessionResponse = await sessionResponsePromise;
    assert(sessionResponse.ok(), `${group.session} API failed to open`);
    const session = await sessionResponse.json();
    activeSession = session;
    const trustedProperty = publicHotelConfig.get(hotelId);
    assert(session.session_id && session.access_token && trustedProperty
      && session.hotel?.hotel_id === hotelId && session.hotel?.name === trustedProperty.name
      && session.hotel?.address === trustedProperty.address && session.hotel?.timezone === trustedProperty.timezone
      && session.hotel?.currency === trustedProperty.currency && session.hotel?.booking_channel,
      `${group.session} has an invalid public session hotel config`);
    sessions.set(group.session, session);
    for (const turnNo of group.turns) {
      const testCase = cases.cases[turnNo - 1];
      assert(testCase.turn === turnNo && APPROVED_CASE_TURNS.includes(turnNo)
        && testCase.session === group.session && testCase.hotel_slug === group.hotel,
        `case ${turnNo} changed identity/order`);
      const beforeState = JSON.parse(await fs.readFile(statePath, "utf8"));
      const budgetTurn = beforeState.guest_turns + 1;
      assert(BUDGET_TURNS[APPROVED_CASE_TURNS.indexOf(turnNo)] === budgetTurn,
        `case ${turnNo} does not map to the next global budget turn`);
      const messageResponsePromise = page.waitForResponse((response) => response.request().method() === "POST"
        && new URL(response.url()).pathname.endsWith("/messages"), { timeout: 55000 });
      await page.locator("#guest-question").fill(testCase.utterance);
      await page.locator(".chat-composer button[type='submit']").click();
      const apiResponse = await messageResponsePromise;
      const responseText = await apiResponse.text();
      const capturePath = await writePrivateCapture(`turn-${String(turnNo).padStart(2, "0")}-api.json`, {
        case_turn: turnNo, budget_turn: budgetTurn,
        status: apiResponse.status(), body_sha256: sha(responseText), body_text: responseText,
      });
      assert(apiResponse.status() >= 200 && apiResponse.status() < 300,
        `turn ${turnNo} API status ${apiResponse.status()}`);
      const payload = JSON.parse(responseText);
      const brief = payload.guest_brief;
      const childId = checkBrief(turnNo, brief);
      if (turnNo === 6) childIdsBySession.set(group.session, childId);
      if (turnNo === 7) assert(childId === childIdsBySession.get(group.session),
        "pine-7 changed the child's stable member ID after the explicit relaxation");
      const room = checkRoom(turnNo, payload.room_advice, hotelId, brief);
      if (turnNo === 7) assert(room.options.length > 0,
        `turn ${turnNo} did not produce a useful positive candidate set`);
      if (turnNo === 6) {
        assert((room.options ?? []).every((option) => !(option.checks ?? []).some((check) =>
          /access|wheelchair|bathroom|step_free/iu.test(check.code) && check.status === "pass")),
        "pine-6 certified unverified hard accessibility fit");
        assert(room.questions.some((question) => /access|room_requirements/iu.test(question.field))
          || room.options.some((option) => option.checks.some((check) =>
            /access|wheelchair|bathroom|step_free/iu.test(check.code) && check.status === "unknown")),
        "pine-6 did not explain the unresolved hard accessibility requirements");
      }
      if (turnNo === 7) {
        assert(payload.presentation?.language_tag?.toLowerCase().startsWith("fr"), "pine-7 did not render French");
        const rationale = (room.options ?? []).flatMap((option) => option.rationale ?? []);
        assert(rationale.length > 0 && rationale.every((item) => item.locale?.toLowerCase().startsWith("fr")
          && item.locale_fallback === false && item.text), "pine-7 rationale has missing French text or fallback");
        assert((room.questions ?? []).every((item) => item.locale?.toLowerCase().startsWith("fr")
          && item.locale_fallback === false && item.reason), "pine-7 questions have missing French text or fallback");
      }
      assert(Array.isArray(room.options) && Array.isArray(room.questions), `turn ${turnNo} result structure missing`);
      const currentCard = page.locator('[data-testid="room-advice"]').last();
      await currentCard.waitFor({ state: "visible", timeout: 30000 });
      if (turnNo === 7) {
        assert((await currentCard.getAttribute("lang"))?.toLowerCase().startsWith("fr"), "French Pine card is not lang=fr");
        const visible = await currentCard.innerText();
        for (const item of room.options.flatMap((option) => option.rationale ?? [])) {
          assert(visible.includes(item.text), "visible French room card omitted a checked rationale label");
        }
      }
      const answerTurn = page.locator(".turn").last();
      const visibleText = await answerTurn.innerText();
      await writePrivateCapture(`turn-${String(turnNo).padStart(2, "0")}-evidence.json`, {
        case_turn: turnNo, budget_turn: budgetTurn,
        case_id: testCase.id ?? `source-case-${testCase.source_case}`, expected: testCase.expected,
        api_response: payload, visible_text: visibleText,
      });
      const afterState = JSON.parse(await fs.readFile(statePath, "utf8"));
      const calls = payload.trace?.calls;
      assert(Number.isInteger(calls) && calls >= 1 && calls <= 2
        && afterState.guest_turns === beforeState.guest_turns + 1
        && afterState.approved_case_turn === turnNo
        && afterState.codex_requests === beforeState.codex_requests + calls,
      `turn ${turnNo} counters/trace differ or exceed two calls`);
      report.turns.push({ case_turn: turnNo, budget_turn: budgetTurn, session: group.session,
        hotel_id: hotelId, http_status: apiResponse.status(),
        request_id_sha256: sha(payload.request_id ?? ""), result_id_sha256: sha(room.result_id),
        result_version: room.result_version, brief_version: brief.brief_version,
        source_generation: room.source_generation, source_ref_count: room.source_refs.length,
        option_count: room.options.length, status: room.status, provider_calls: calls,
        answer_language: payload.presentation?.language_tag ?? null,
        capture: path.basename(capturePath),
      });
      if (turnNo === 7) {
        const selected = await selectCurrentOption(turnNo, room, currentCard, session, afterState);
        assert(selected, `turn ${turnNo} did not expose a current option for the required UI selection`);
      }
    }
    await page.screenshot({ path: path.join(runDir, `${group.hotel}-desktop.png`), fullPage: true });
    await fs.chmod(path.join(runDir, `${group.hotel}-desktop.png`), 0o600);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, body: document.body.scrollWidth }));
  assert(mobile.body <= mobile.viewport + 1, "mobile layout overflows horizontally");
  await page.screenshot({ path: path.join(runDir, "pine-mobile.png"), fullPage: true });
  await fs.chmod(path.join(runDir, "pine-mobile.png"), 0o600);
  report.mobile_layout = { ...mobile, no_horizontal_overflow: true };
  const finalState = JSON.parse(await fs.readFile(statePath, "utf8"));
  assert(finalState.guest_turns === 5 && finalState.approved_case_turn === 7
    && finalState.codex_requests >= 7 && finalState.codex_requests <= 9,
  "continuation counters differ from two approved cases, seeded 3/5, and remaining 2/4 bounds");
  report.counters = { guest_turns: finalState.guest_turns, codex_requests: finalState.codex_requests,
    max_guest_turns: finalState.max_guest_turns, max_codex_requests: finalState.max_codex_requests,
    parent_seed: { guest_turns: 3, codex_requests: 5 }, new_guest_turns: 2,
    new_requests: finalState.codex_requests - 5, unused_guest_turns: 2,
    unused_requests: 14 - finalState.codex_requests };
  report.completed_at = new Date().toISOString();
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  console.log(JSON.stringify({ run_id: RUN_ID, turns: report.turns.length, report: reportPath, status: "completed" }));
} catch (error) {
  const failureMessage = String(error?.message ?? "blocking failure")
    .replace(/Bearer\s+[^\s,;]+/giu, "Bearer <redacted>")
    .replace(/https?:\/\/[^\s"']+/giu, "<url-redacted>")
    .replace(/(token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,;]+/giu, "$1=<redacted>");
  report.failure = { name: error?.name ?? "Error", message: failureMessage.slice(0, 240) };
  try {
    const failed = JSON.parse(await fs.readFile(statePath, "utf8"));
    report.counters = { guest_turns: failed.guest_turns, codex_requests: failed.codex_requests,
      max_guest_turns: failed.max_guest_turns, max_codex_requests: failed.max_codex_requests, status: failed.status };
  } catch { report.counters = { unavailable: true }; }
  report.completed_at = new Date().toISOString();
  try { await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx", mode: 0o600 }); } catch { /* preserve first failed report */ }
  console.error(JSON.stringify({ run_id: RUN_ID, turns_completed: report.turns.length,
    failure: report.failure, report: reportPath }));
  process.exitCode = 1;
} finally {
  await context?.close();
  await browser?.close();
}
