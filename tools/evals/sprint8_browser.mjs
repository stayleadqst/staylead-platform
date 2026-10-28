#!/usr/bin/env node
/** Four-turn opt-in Sprint 8 browser acceptance. Import/default path is offline. */
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { browserRunDirectory, freshRuntimeHandoffReady, hardNeedsPreserved, latestTurnForQuestion, localGuideAcceptanceCheck, semanticReviewReceiptValid, sha256 } from "./sprint8_browser_helpers.mjs";

const RUN_ID = "s8-local-guide-20261028-acceptance";
const MAX_TURNS = 4;
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const privatePath = async (value, name) => {
  assert(value && path.isAbsolute(value) && value.startsWith("/private/tmp/"), `${name} must point under /private/tmp`);
  const info = await fs.lstat(value);
  assert(info.isFile() && !info.isSymbolicLink() && (info.mode & 0o777) === 0o600 && info.size <= 1_048_576,
    `${name} must be a private regular 0600 file`);
  return value;
};
const hashFile = async (file) => sha256(await fs.readFile(file));
function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stable(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

if (process.argv.includes("--offline-harness-smoke")) {
  const proposed = JSON.parse(await fs.readFile("docs/product/evidence/sprint-8/acceptance-cases-proposed.json", "utf8"));
  assert(proposed.authorized_for_live_calls === false, "The proposed case file must remain unauthorized");
  console.log(JSON.stringify({ status: "offline-harness-smoke-ok", batch_namespace: RUN_ID,
    guest_turn_cap: MAX_TURNS, request_cap: 8, fresh_counters: { guest_turns: 0, requests: 0 },
    no_browser: true, no_api_or_model: true }));
  process.exit(0);
}
assert(process.env.STAYLEAD_S8_LIVE_EVAL === "1", "STAYLEAD_S8_LIVE_EVAL=1 is required; no browser/API/model request was sent");
const configPath = await privatePath(process.env.STAYLEAD_S8_RUNTIME_CONFIG, "runtime config");
const statePath = await privatePath(process.env.STAYLEAD_S8_RUN_STATE, "run state");
const config = JSON.parse(await fs.readFile(configPath, "utf8"));
const state = JSON.parse(await fs.readFile(statePath, "utf8"));
assert(config.run_id === RUN_ID && state.run_id === RUN_ID && config.authorized_for_live_calls === true
  && state.authorized_for_live_calls === true && config.candidate_sha256 === state.candidate_sha256
  && config.case_sha256 === state.case_sha256 && config.oracle_sha256 === state.oracle_sha256
  && state.harness_sha256 === sha256(stable({ files: config.harness_files, browser_executable: config.browser_executable })),
"Private config/state is not an explicitly authorized fresh Sprint 8 namespace");
assert(freshRuntimeHandoffReady(state),
  "Browser controller requires the exact fresh authorized zero-counter state after API startup");
assert(state.max_guest_turns === 4 && state.max_requests === 8 && state.max_calls_per_turn === 2
  && state.provider_timeout_seconds === 25 && state.turn_timeout_seconds === 45 && state.max_output_tokens === 700
  && state.model === "gpt-6.1-sol" && state.effort === "low" && state.automatic_retry === false
  && state.fallback === false && state.stop_at_first_blocking_failure === true,
"Fresh state does not hold the exact approved Sprint 8 profile");
const manifestPath = path.join(process.cwd(), "docs/product/evidence/sprint-8/candidate-manifest.json");
const manifestInfo = await fs.lstat(manifestPath);
assert(manifestInfo.isFile() && !manifestInfo.isSymbolicLink() && manifestInfo.size <= 2 * 1024 * 1024,
  "Public candidate manifest is unsafe or oversized");
const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
assert(manifest.schema_version === 1 && manifest.branch === "sprint-8-guide-shortlist"
  && manifest.baseline === "12122f7d012c0617670438de5419efdc3d7729ab"
  && manifest.scope === "apps, fixtures, product tests; new acceptance harness excluded and separately pinned"
  && manifest.hash_method === "sha256(canonical JSON files map: sort_keys=True,separators=(comma,colon))"
  && sha256(stable(manifest.files)) === config.candidate_sha256
  && manifest.candidate_sha256 === config.candidate_sha256 && manifest.sha256 === config.candidate_sha256
  && manifest.browser_executable === config.browser_executable, "Public candidate manifest fingerprint mismatch");
const casesPath = await privatePath(config.live_cases_path, "approved case matrix");
const oraclePath = await privatePath(config.oracle_path, "independent oracle");
const [caseRaw, oracleRaw] = await Promise.all([fs.readFile(casesPath), fs.readFile(oraclePath)]);
assert(sha256(caseRaw) === config.case_sha256 && sha256(oracleRaw) === config.oracle_sha256,
  "Approved case or independent oracle hash changed");
const cases = JSON.parse(caseRaw.toString("utf8"));
const oracle = JSON.parse(oracleRaw.toString("utf8"));
assert(cases.run_id === RUN_ID && cases.authorized_for_live_calls === true && cases.cases?.length === MAX_TURNS
  && cases.property?.hotel_id === "HTL-S8-DEMO" && cases.property?.slug === "lotus-pilot-demo"
  && cases.limits?.guest_turns === 4 && cases.limits?.requests === 8 && cases.limits?.calls_per_turn === 2
  && cases.limits?.provider_timeout_seconds === 25 && cases.limits?.turn_timeout_seconds === 45
  && cases.limits?.max_output_tokens === 700 && cases.limits?.model === "gpt-6.1-sol" && cases.limits?.effort === "low"
  && cases.limits?.automatic_retry === false && cases.limits?.fallback === false
  && cases.limits?.stop_at_first_blocking_failure === true && Array.isArray(oracle.case_checks),
"Approved matrix/oracle shape or limits are invalid");
assert(state.sessions === undefined || Object.keys(state.sessions).length === 0, "Fresh session bindings are not empty");
const checks = new Map(oracle.case_checks.map((row) => [row.case_id, row]));
assert(["s8-01", "s8-02", "s8-03", "s8-04"].every((id) => checks.has(id)), "Independent oracle does not cover all turns");
const profile = config;
assert(profile.max_guest_turns === 4 && profile.max_requests === 8 && profile.max_calls_per_turn === 2
  && profile.provider_timeout_seconds === 25 && profile.turn_timeout_seconds === 45 && profile.max_output_tokens === 700
  && profile.model === "gpt-6.1-sol" && profile.effort === "low" && profile.automatic_retry === false
  && profile.fallback === false && profile.stop_at_first_blocking_failure === true,
"Pinned S8 runtime limits differ");
const repo = process.cwd();
for (const [file, expected] of Object.entries(manifest.files ?? {})) {
  const full = path.resolve(repo, file);
  const info = await fs.lstat(full);
  assert(full.startsWith(`${repo}${path.sep}`) && !info.isSymbolicLink() && info.isFile()
    && await hashFile(full) === expected, `Pinned candidate source changed: ${file}`);
}
const harnessFiles = new Set([
  "tools/evals/sprint8_runtime.py", "tools/evals/sprint8_browser.mjs",
  "tools/evals/sprint8_browser_helpers.mjs", "tests/contracts/test_sprint8_acceptance_harness.py",
]);
assert(config.harness_files && Object.keys(config.harness_files).length === harnessFiles.size
  && Object.keys(config.harness_files).every((file) => harnessFiles.has(file)), "Private config must pin the four acceptance harness files");
for (const [file, expected] of Object.entries(config.harness_files)) {
  const full = path.resolve(repo, file); const info = await fs.lstat(full);
  assert(full.startsWith(`${repo}${path.sep}`) && !info.isSymbolicLink() && info.isFile()
    && await hashFile(full) === expected, `Acceptance harness changed: ${file}`);
}
const playwrightUrl = process.env.STAYLEAD_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.STAYLEAD_PLAYWRIGHT_MODULE).href : "playwright";
const { chromium } = await import(playwrightUrl);
assert(typeof config.browser_executable === "string" && path.isAbsolute(config.browser_executable),
  "The approved private config must pin the local browser executable");
const browserInfo = await fs.lstat(config.browser_executable);
assert(browserInfo.isFile() && !browserInfo.isSymbolicLink(), "Pinned browser executable must be a local regular file");
await fs.access(config.browser_executable, 1);
const browser = await chromium.launch({ headless: false, executablePath: config.browser_executable });
const runDir = browserRunDirectory(RUN_ID, process.env.STAYLEAD_S8_BROWSER_ATTEMPT ?? "r1");
await fs.mkdir(runDir, { mode: 0o700 }); await fs.chmod(runDir, 0o700);
const report = { run_id: RUN_ID, candidate_sha256: config.candidate_sha256,
  case_sha256: config.case_sha256, oracle_sha256: config.oracle_sha256, live: true, turns: [], failure: null };
const replacePrivateReport = async (value) => {
  const target = path.join(runDir, "browser-report.json");
  const content = JSON.stringify(value, null, 2) + "\n";
  assert(Buffer.byteLength(content) <= 128 * 1024, "Private browser report exceeds size cap");
  try {
    const info = await fs.lstat(target);
    assert(info.isFile() && !info.isSymbolicLink() && (info.mode & 0o777) === 0o600, "Existing private report is unsafe");
  } catch (error) { if (error.code !== "ENOENT") throw error; }
  await fs.writeFile(target, content, { mode: 0o600 });
  await fs.chmod(target, 0o600);
  return target;
};
const receiptPath = (turn) => path.join(runDir, `semantic-review-turn-${String(turn).padStart(2, "0")}.json`);
async function waitForReceipt(turn, responseHash) {
  const deadline = Date.now() + 600_000;
  while (Date.now() < deadline) {
    try {
      const file = receiptPath(turn); const info = await fs.lstat(file);
      assert(info.isFile() && !info.isSymbolicLink() && (info.mode & 0o777) === 0o600, "Semantic review receipt is not private");
      const receipt = JSON.parse(await fs.readFile(file, "utf8"));
      assert(semanticReviewReceiptValid(receipt, { run_id: RUN_ID, candidate_sha256: config.candidate_sha256,
        approved_case_turn: turn, response_sha256: responseHash }), "Semantic review receipt does not match exact candidate/turn/response");
      return;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
  throw new Error(`No root/Q semantic receipt for turn ${turn}; later turns were not attempted`);
}

let page;
let previousRequests = 0;
try {
  const context = await browser.newContext({ viewport: { width: 1365, height: 900 } });
  page = await context.newPage();
  const base = (process.env.STAYLEAD_S8_WEB_URL ?? "http://127.0.0.1:13000").replace(/\/$/u, "");
  for (let index = 0; index < cases.cases.length; index += 1) {
    const item = cases.cases[index];
    if (index < 3) {
      if (index > 0) await page.goto(`${base}/hotels/${cases.property.slug}/chat`, { waitUntil: "domcontentloaded" });
      else await page.goto(`${base}/hotels/${cases.property.slug}/chat`, { waitUntil: "domcontentloaded" });
    }
    if (item.mobile_rtl || (index === 3 && cases.cases[2].mobile_rtl)) await page.setViewportSize({ width: 390, height: 844 });
    const editor = page.locator("#guest-question");
    await editor.waitFor({ state: "visible", timeout: 15_000 });
    await editor.fill(item.input);
    const responseWait = page.waitForResponse((response) => response.request().method() === "POST" && /\/sessions\/[^/]+\/messages$/u.test(new URL(response.url()).pathname), { timeout: 50_000 });
    await page.locator("form.chat-composer button[type=submit]").click();
    const networkResponse = await responseWait;
    const payload = await networkResponse.json();
    assert(networkResponse.ok(), `Turn ${index + 1} API response failed: ${networkResponse.status()}`);
    const afterState = JSON.parse(await fs.readFile(statePath, "utf8"));
    const requestDelta = afterState.requests - previousRequests;
    assert(afterState.guest_turns === index + 1 && afterState.approved_case_turn === index + 1
      && requestDelta >= 1 && requestDelta <= 2 && afterState.requests <= 8,
    `Turn ${index + 1} counters diverged or exceeded the request allowance`);
    previousRequests = afterState.requests;
    const currentTurn = page.locator(".turn").filter({
      has: page.locator(".message-guest p").getByText(item.input, { exact: true }),
    }).last();
    await currentTurn.getByTestId("local-guide-result").waitFor({ state: "visible", timeout: 10_000 });
    const turnSnapshots = await page.locator(".turn").evaluateAll((turns) => turns.map((turn) => {
      const question = turn.querySelector(".message-guest p")?.textContent ?? "";
      const guide = turn.querySelector('[data-testid="local-guide-result"]');
      return { question, guide: guide ? {
        lang: guide.getAttribute("lang"), dir: guide.getAttribute("dir"), text: guide.innerText,
      } : null };
    }));
    const currentSnapshot = latestTurnForQuestion(turnSnapshots, item.input);
    assert(currentSnapshot?.guide, `Turn ${index + 1} did not render a card for its exact question`);
    const rendered = currentSnapshot.guide;
    const oracleCase = checks.get(item.id);
    const verdict = localGuideAcceptanceCheck({ response: payload, rendered, expected: oracleCase, language: item.language });
    assert(verdict.ok, `Turn ${index + 1} failed independent oracle: ${verdict.reason}`);
    if (index === 3) {
      const original = report.turns[2]?.response?.guest_brief;
      if (oracleCase.preserved_hard_needs) assert(hardNeedsPreserved(original, payload.guest_brief), "Turn 4 did not preserve exact M2 hard needs");
    }
    const screenshot = path.join(runDir, `turn-${String(index + 1).padStart(2, "0")}.png`);
    await page.screenshot({ path: screenshot, fullPage: true }); await fs.chmod(screenshot, 0o600);
    const responseHash = sha256(JSON.stringify(payload));
    report.turns.push({ turn: index + 1, case_id: item.id, locale: item.language, response_sha256: responseHash,
      provider_requests_after: afterState.requests, verdict, screenshot, response: payload, rendered });
    await replacePrivateReport(report);
    if (index < cases.cases.length - 1) await waitForReceipt(index + 1, responseHash);
  }
} catch (error) {
  report.failure = { name: error?.name ?? "Error", message: error?.message ?? String(error) };
  await replacePrivateReport(report).catch(() => {});
  console.error(`Sprint 8 browser acceptance halted: ${report.failure.name}: ${report.failure.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
