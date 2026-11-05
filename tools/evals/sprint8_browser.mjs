#!/usr/bin/env node
/** Four-turn opt-in Sprint 8 browser acceptance. Import/default path is offline. */
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { browserRunDirectory, freshRuntimeHandoffReady, hardNeedsPreserved, latestTurnForQuestion, localGuideAcceptanceCheck, persistBeforeEvaluation, semanticReviewReceiptValid, sha256 } from "./sprint8_browser_helpers.mjs";

const RUN_ID = "s8-local-guide-20261028-reacceptance1";
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
async function writePrivateJson(target, value, maxBytes) {
  const content = `${JSON.stringify(value, null, 2)}\n`;
  assert(Buffer.byteLength(content) <= maxBytes, "Private evidence file exceeds its size cap");
  const temporary = `${target}.tmp-${process.pid}`;
  try {
    const existing = await fs.lstat(target);
    assert(existing.isFile() && !existing.isSymbolicLink() && (existing.mode & 0o777) === 0o600,
      "Existing private evidence file is unsafe");
  } catch (error) { if (error.code !== "ENOENT") throw error; }
  await fs.writeFile(temporary, content, { flag: "wx", mode: 0o600 });
  await fs.chmod(temporary, 0o600);
  await fs.rename(temporary, target);
  await fs.chmod(target, 0o600);
  return { content, sha256: sha256(content) };
}
async function persistTurnEvidence({ report, record, evidencePath, persistIndex }) {
  const evidence = { ...record };
  delete evidence.evidence_path;
  delete evidence.evidence_sha256;
  const saved = await writePrivateJson(evidencePath, evidence, 1_048_576);
  record.evidence_path = evidencePath;
  record.evidence_sha256 = saved.sha256;
  const index = Number.isInteger(record.turn) && record.turn > 0 ? record.turn - 1 : report.turns.length;
  report.turns[index] = {
    turn: record.turn, case_id: record.case_id, locale: record.locale,
    input_sha256: record.input_sha256, attempt_status: record.attempt_status,
    network_response: record.network_response ?? null,
    response_sha256: record.response_sha256 ?? null,
    counter_snapshot: record.counter_snapshot ?? null,
    request_delta: record.request_delta ?? null,
    provider_requests_after: record.provider_requests_after ?? null,
    screenshot: record.screenshot ?? null,
    verdict: record.verdict ?? null,
    failure: record.failure ?? null,
    evidence_path: evidencePath, evidence_sha256: saved.sha256,
  };
  await persistIndex(report);
}

if (process.argv.includes("--offline-harness-smoke")) {
  const proposed = JSON.parse(await fs.readFile("docs/product/evidence/sprint-8/acceptance-cases-proposed.json", "utf8"));
  assert(proposed.authorized_for_live_calls === false, "The proposed case file must remain unauthorized");
  console.log(JSON.stringify({ status: "offline-harness-smoke-ok", batch_namespace: RUN_ID,
    guest_turn_cap: MAX_TURNS, request_cap: 8, fresh_counters: { guest_turns: 0, requests: 0 },
    no_browser: true, no_api_or_model: true }));
  process.exit(0);
}
if (process.argv[2] === "--offline-oracle-failure-smoke") {
  const reportPath = process.argv[3];
  assert(typeof reportPath === "string" && path.isAbsolute(reportPath) && reportPath.startsWith("/private/tmp/"),
    "Offline failure smoke report must be under /private/tmp");
  const report = { turns: [] };
  const screenshotPath = `${reportPath}.png`;
  const evidencePath = `${reportPath}.turn-01.json`;
  const response = { presentation: { language_tag: "zh" }, local_guide: {
    supported_claims: [{ venue_id: "ATT-01", unknown_codes: ["hours_unconfirmed"],
      localized_unknowns: ["请向场所确认当前营业时间。"] }],
    source_refs: [{ source_id: "S8-GUIDE-PRIMARY", fact_ids: ["F-HTL-S8-DEMO-001"] }],
  } };
  const record = { turn: 1, case_id: "s8-offline-regression", locale: "zh", response,
    rendered: { lang: "zh", dir: "ltr", text: "待核实事项\n请向场所确认当前营业时间。" } };
  const verdict = await persistBeforeEvaluation({
    report, record,
    counterSnapshot: async () => ({ guest_turns: 1, approved_case_turn: 1, requests: 2 }),
    captureScreenshot: async () => {
      await fs.writeFile(screenshotPath, "synthetic offline screenshot evidence", { mode: 0o600 });
      await fs.chmod(screenshotPath, 0o600);
      return screenshotPath;
    },
    persist: async () => persistTurnEvidence({ report, record, evidencePath,
      persistIndex: (value) => writePrivateJson(reportPath, value, 128 * 1024) }),
    evaluate: async () => {
      const saved = JSON.parse(await fs.readFile(reportPath, "utf8"));
      const evidence = JSON.parse(await fs.readFile(saved.turns[0].evidence_path, "utf8"));
      assert(evidence.response?.local_guide, "Attempt response was not persisted before oracle evaluation");
      assert(evidence.rendered?.text && evidence.counter_snapshot?.requests === 2
        && evidence.screenshot === screenshotPath && saved.turns[0].evidence_sha256,
      "Rendered text, counters, screenshot, or evidence hash were not persisted before oracle evaluation");
      const accepted = localGuideAcceptanceCheck({
        response, rendered: record.rendered, language: "zh",
        expected: { required_localized_unknowns_rendered: true },
      });
      assert(accepted.ok, `Localized unknown evidence should pass its semantic check: ${accepted.reason}`);
      const missingRenderedUnknown = localGuideAcceptanceCheck({
        response, rendered: { ...record.rendered, text: "待核实事项" }, language: "zh",
        expected: { required_localized_unknowns_rendered: true },
      });
      assert(!missingRenderedUnknown.ok && missingRenderedUnknown.reason === "localized_unknown_not_rendered:ATT-01",
        "A known unknown missing from the rendered card must fail");
      return localGuideAcceptanceCheck({
        response, rendered: record.rendered, language: "zh",
        expected: { required_rendered_phrases: ["需要确认"] },
      });
    },
  });
  record.verdict = verdict;
  await persistTurnEvidence({ report, record, evidencePath,
    persistIndex: (value) => writePrivateJson(reportPath, value, 128 * 1024) });
  assert(verdict.ok === false && verdict.reason === "required_localized_phrase_missing",
    "Regression must retain a realistic strict-phrase oracle failure");
  console.log(JSON.stringify({ status: "offline-oracle-failure-evidence-ok", report_path: reportPath,
    verdict, requests: record.counter_snapshot.requests,
    localized_unknown_rendered: true, missing_localized_unknown_rejected: true }));
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
async function persistAttemptBeforeOracle(record, evaluate) {
  return persistBeforeEvaluation({
    report, record, persist: () => persistTurnEvidence({
      report, record,
      evidencePath: path.join(runDir, `turn-${String(record.turn).padStart(2, "0")}-evidence.json`),
      persistIndex: replacePrivateReport,
    }),
    counterSnapshot: async () => {
      const current = JSON.parse(await fs.readFile(statePath, "utf8"));
      return {
        guest_turns: current.guest_turns,
        approved_case_turn: current.approved_case_turn,
        requests: current.requests,
      };
    },
    captureScreenshot: async () => {
      const file = path.join(runDir, `turn-${String(record.turn).padStart(2, "0")}.png`);
      await page.screenshot({ path: file, fullPage: true });
      await fs.chmod(file, 0o600);
      return file;
    },
    evaluate,
  });
}
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
let activeItem = null;
let activeRecord = null;
const completedResponses = [];
try {
  const context = await browser.newContext({ viewport: { width: 1365, height: 900 } });
  page = await context.newPage();
  const base = (process.env.STAYLEAD_S8_WEB_URL ?? "http://127.0.0.1:13000").replace(/\/$/u, "");
  for (let index = 0; index < cases.cases.length; index += 1) {
    const item = cases.cases[index];
    activeItem = item;
    const record = {
      turn: index + 1, case_id: item.id, locale: item.language,
      input_sha256: sha256(item.input), attempt_status: "prepared",
      network_response: null, response: null, rendered: null, rendered_text: null,
    };
    activeRecord = record;
    report.turns.push(record);
    await replacePrivateReport(report);
    if (index < 3) {
      if (index > 0) await page.goto(`${base}/hotels/${cases.property.slug}/chat`, { waitUntil: "domcontentloaded" });
      else await page.goto(`${base}/hotels/${cases.property.slug}/chat`, { waitUntil: "domcontentloaded" });
    }
    if (item.mobile_rtl || (index === 3 && cases.cases[2].mobile_rtl)) await page.setViewportSize({ width: 390, height: 844 });
    const editor = page.locator("#guest-question");
    await editor.waitFor({ state: "visible", timeout: 15_000 });
    await editor.fill(item.input);
    const isMessagePost = (request) => request.method() === "POST"
      && /\/sessions\/[^/]+\/messages$/u.test(new URL(request.url()).pathname);
    const requestFailures = [];
    const onRequestFailed = (request) => {
      if (isMessagePost(request)) requestFailures.push({ method: request.method(), failure: request.failure()?.errorText ?? null });
    };
    page.on("requestfailed", onRequestFailed);
    const responseWait = page.waitForResponse((response) => isMessagePost(response.request()), { timeout: 50_000 });
    record.attempt_status = "submitting";
    await replacePrivateReport(report);
    await page.locator("form.chat-composer button[type=submit]").click();
    record.attempt_status = "submitted";
    await replacePrivateReport(report);
    let networkResponse;
    try {
      networkResponse = await responseWait;
    } catch (error) {
      page.off("requestfailed", onRequestFailed);
      record.request_failures = requestFailures;
      record.failure = { name: error?.name ?? "Error", message: error?.message ?? String(error) };
      try {
        record.rendered_text = await page.locator(".turn").filter({
          has: page.locator(".message-guest p").getByText(item.input, { exact: true }),
        }).last().innerText();
      } catch (renderError) {
        record.render_capture_failure = { name: renderError?.name ?? "Error", message: renderError?.message ?? String(renderError) };
      }
      await persistAttemptBeforeOracle(record, () => { throw error; });
    }
    page.off("requestfailed", onRequestFailed);
    record.network_response = { status: networkResponse.status(), ok: networkResponse.ok() };
    const bodyText = await networkResponse.text();
    try {
      record.response = JSON.parse(bodyText);
      record.response_sha256 = sha256(JSON.stringify(record.response));
    } catch (error) {
      record.response_body_text = bodyText.slice(0, 16_000);
      record.response_body_truncated = bodyText.length > 16_000;
      record.response_parse_failure = { name: error?.name ?? "Error", message: error?.message ?? String(error) };
    }
    record.request_failures = requestFailures;
    const currentTurn = page.locator(".turn").filter({
      has: page.locator(".message-guest p").getByText(item.input, { exact: true }),
    }).last();
    if (networkResponse.ok()) {
      try {
        await currentTurn.getByTestId("local-guide-result").waitFor({ state: "visible", timeout: 10_000 });
      } catch (error) {
        record.render_wait_failure = { name: error?.name ?? "Error", message: error?.message ?? String(error) };
      }
    }
    const turnSnapshots = await page.locator(".turn").evaluateAll((turns) => turns.map((turn) => {
      const question = turn.querySelector(".message-guest p")?.textContent ?? "";
      const guide = turn.querySelector('[data-testid="local-guide-result"]');
      return { question, guide: guide ? {
        lang: guide.getAttribute("lang"), dir: guide.getAttribute("dir"), text: guide.innerText,
      } : null, turn_text: turn.innerText };
    }));
    const currentSnapshot = latestTurnForQuestion(turnSnapshots, item.input);
    record.rendered = currentSnapshot?.guide ?? null;
    record.rendered_text = currentSnapshot?.turn_text ?? null;
    const oracleCase = checks.get(item.id);
    const verdict = await persistAttemptBeforeOracle(record, () => {
      if (!networkResponse.ok()) return { ok: false, reason: `api_http_failure:${networkResponse.status()}` };
      if (!record.response || typeof record.response !== "object") return { ok: false, reason: "api_response_json_missing" };
      if (record.screenshot_error) return { ok: false, reason: "screenshot_capture_failed" };
      const counters = record.counter_snapshot;
      if (!counters) return { ok: false, reason: "counter_snapshot_missing" };
      const requestDelta = counters.requests - previousRequests;
      record.request_delta = requestDelta;
      if (counters.guest_turns !== index + 1 || counters.approved_case_turn !== index + 1
          || requestDelta < 1 || requestDelta > 2 || counters.requests > 8) {
        return { ok: false, reason: "acceptance_counters_diverged" };
      }
      if (!record.rendered) return { ok: false, reason: "current_turn_card_missing" };
      const result = localGuideAcceptanceCheck({
        response: record.response, rendered: record.rendered, expected: oracleCase, language: item.language,
      });
      if (!result.ok) return result;
      if (index === 3 && oracleCase.preserved_hard_needs
          && !hardNeedsPreserved(completedResponses[2]?.guest_brief, record.response.guest_brief)) {
        return { ok: false, reason: "hard_needs_not_preserved" };
      }
      return result;
    });
    record.verdict = verdict;
    record.provider_requests_after = record.counter_snapshot?.requests ?? null;
    completedResponses[index] = record.response;
    await persistTurnEvidence({ report, record,
      evidencePath: path.join(runDir, `turn-${String(record.turn).padStart(2, "0")}-evidence.json`),
      persistIndex: replacePrivateReport,
    });
    assert(verdict.ok, `Turn ${index + 1} failed independent oracle: ${verdict.reason}`);
    previousRequests = record.counter_snapshot.requests;
    const responseHash = record.response_sha256;
    if (index < cases.cases.length - 1) await waitForReceipt(index + 1, responseHash);
  }
} catch (error) {
  if (["submitting", "submitted"].includes(activeRecord?.attempt_status) && !activeRecord.evidence_persisted) {
    activeRecord.failure ??= { name: error?.name ?? "Error", message: error?.message ?? String(error) };
    try {
      activeRecord.rendered_text = await page.locator(".turn").filter({
        has: page.locator(".message-guest p").getByText(activeItem.input, { exact: true }),
      }).last().innerText();
    } catch (renderError) {
      activeRecord.render_capture_failure = { name: renderError?.name ?? "Error", message: renderError?.message ?? String(renderError) };
    }
    await persistAttemptBeforeOracle(activeRecord, () => null).catch(() => {});
  }
  report.failure = { name: error?.name ?? "Error", message: error?.message ?? String(error) };
  await replacePrivateReport(report).catch(() => {});
  console.error(`Sprint 8 browser acceptance halted: ${report.failure.name}: ${report.failure.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
