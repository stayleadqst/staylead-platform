#!/usr/bin/env node
/**
 * Fresh one-session driver for the resumed Sprint 6 nine-turn acceptance batch.
 * It never mocks the API or automatically retries/resumes/reloads, and never
 * logs session tokens. C may explicitly command one visible answer-only resume.
 * On failure, it saves evidence and holds the visible session for a C decision.
 *
 *   node docs/product/evidence/sprint-6/remediation/resumed-live-browser.mjs
 */

import fs from "node:fs/promises";
import { readFileSync } from "node:fs";
import { createHash as nodeCreateHash } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { shouldOfferOperatorResume } from "./operator-resume-routing.mjs";
import { safeAnswerTrace } from "./safe-answer-trace.mjs";

const { chromium } = await import(pathToFileURL(
  "/Users/ccvn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs",
).href);

const ROOT = process.cwd();
const MATRIX_PATH = path.join(ROOT, "docs/product/evidence/sprint-6/live-cases.json");
const RUN_NAMESPACE = process.env.STAYLEAD_S6_RUN_NAMESPACE ?? "remediation-1";
requireCheck(["remediation-1", "remediation-2", "remediation-3"].includes(RUN_NAMESPACE), "STAYLEAD_S6_RUN_NAMESPACE must be remediation-1, remediation-2, or remediation-3");
const RUN_ID = `s6-codex-20261026-${RUN_NAMESPACE}`;
const OUTPUT_DIR = RUN_NAMESPACE === "remediation-1" ? "resumed-live-run" : `${RUN_NAMESPACE}-live-run`;
const OUTPUT = path.join(ROOT, "docs/product/evidence/sprint-6/remediation", OUTPUT_DIR);
const BASE_URL = process.env.STAYLEAD_S6_WEB_URL ?? "http://127.0.0.1:13016";
const PRIVATE_PREFIX = RUN_NAMESPACE === "remediation-1" ? "staylead-sprint6-remediation" : `staylead-sprint6-${RUN_NAMESPACE}`;
const RUNTIME_STATE = `/private/tmp/${PRIVATE_PREFIX}-run-state.json`;
const RUNTIME_EVENTS = `/private/tmp/${PRIVATE_PREFIX}-runtime-events.jsonl`;

function requireCheck(condition, message) {
  if (!condition) throw new Error(message);
}

function redactText(value) {
  return String(value ?? "")
    .replace(/\bBearer\s+[^\s,"}]+/gi, "Bearer <redacted>")
    .replace(/\b(sk-[A-Za-z0-9_-]{12,})\b/g, "<redacted>")
    .replace(/\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, "<redacted>")
    .replace(/\b(?:postgres(?:ql)?|mysql|redis):\/\/[^\s,"}]+/gi, "<redacted-dsn>")
    .replace(/\b(api[_-]?key|access[_-]?token|session[_-]?token|password|secret)\s*[:=]\s*[^\s,"}]+/gi, "$1=<redacted>");
}

function safePresentation(value) {
  if (!value || typeof value !== "object") return null;
  return {
    language_tag: value.language_tag ?? null,
    direction: value.direction ?? null,
    preference_revision: value.preference_revision ?? null,
    freshness: value.freshness ?? null,
    receipt_id_sha256: value.receipt_id ? hashIdentifier(value.receipt_id) : null,
    labels_fallback: value.labels_fallback ?? null,
  };
}

function safeValidationDiagnostics(value) {
  if (!value || value.code !== "model_validation" || !Array.isArray(value.errors) ||
      !Number.isInteger(value.error_count) || value.error_count < value.errors.length ||
      value.error_count > 10000 || value.errors.length > 64) return null;
  const errors = [];
  for (const item of value.errors) {
    if (!Array.isArray(item?.loc) || typeof item.type !== "string" || !/^[A-Za-z0-9_.-]{1,80}$/.test(item.type)) return null;
    const loc = [];
    for (const segment of item.loc.slice(0, 12)) {
      if (Number.isInteger(segment) && segment >= 0 && segment <= 10000) loc.push(segment);
      else if (typeof segment === "string" && /^(?:[A-Za-z_][A-Za-z0-9_]{0,63}|<key>)$/.test(segment)) loc.push(segment);
      else return null;
    }
    errors.push({ loc, type: item.type });
  }
  return { code: "model_validation", error_count: value.error_count, errors };
}

function safeBrief(value) {
  if (!value || typeof value !== "object") return null;
  return {
    brief_version: value.brief_version ?? null,
    dates: value.dates ?? null,
    party: {
      adults: value.party?.adults ?? null,
      children: Array.isArray(value.party?.children) ? value.party.children.map((child) => ({
        member_id_sha256: child?.member_id ? hashIdentifier(child.member_id) : null,
        age: Number.isInteger(child?.age) ? child.age : null,
      })) : [],
    },
    pending_fields: Array.isArray(value.pending_fields) ? value.pending_fields : [],
  };
}

function hashIdentifier(value) {
  // Stable, non-reversible reference so turn 2 / turn 3 can be compared without
  // storing the backend's raw member identifier in the evidence file.
  return nodeCreateHash("sha256").update(String(value)).digest("hex").slice(0, 16);
}

function safeApiResponse(value) {
  if (!value || typeof value !== "object") return { parse_error: true };
  const evidence = Array.isArray(value.evidence) ? value.evidence.map((item) => ({
    fact_id: item.fact_id ?? null,
    hotel_id: item.hotel_id ?? null,
    source_id: item.source_id ?? null,
    source_version: item.source_version ?? null,
    section: redactText(item.section ?? ""),
  })) : [];
  const receipt = value.brief_receipt && typeof value.brief_receipt === "object" ? {
    request_id_sha256: value.brief_receipt.request_id ? hashIdentifier(value.brief_receipt.request_id) : null,
    status: value.brief_receipt.status ?? null,
    brief_version_before: value.brief_receipt.brief_version_before ?? null,
    brief_version_after: value.brief_receipt.brief_version_after ?? null,
    answer_status: value.brief_receipt.answer_status ?? null,
    brief_version_used: value.brief_receipt.brief_version_used ?? null,
  } : null;
  return {
    request_id_sha256: value.request_id ? hashIdentifier(value.request_id) : null,
    status: value.status ?? null,
    error_code: typeof value.error?.code === "string" && /^[A-Za-z0-9._:-]{1,100}$/.test(value.error.code)
      ? value.error.code : null,
    answer: redactText(value.answer ?? ""),
    evidence,
    unknowns: Array.isArray(value.unknowns) ? value.unknowns.map(redactText) : [],
    language_preference: value.language_preference ? {
      language_tag: value.language_preference.language_tag ?? null,
      source: value.language_preference.source ?? null,
      revision: value.language_preference.revision ?? null,
    } : null,
    presentation: safePresentation(value.presentation),
    answer_eligibility: value.answer_eligibility ?? null,
    trace: safeAnswerTrace(value.trace),
    validation_diagnostics: safeValidationDiagnostics(value.error?.validation_diagnostics),
    guest_brief: safeBrief(value.guest_brief),
    brief_receipt: receipt,
    replayed: value.replayed ?? null,
    access_token_included: false,
    utterance_included: false,
  };
}

function runtimeSnapshot(turn) {
  let state = null;
  try {
    const parsed = JSON.parse(readFileSync(RUNTIME_STATE, "utf8"));
    state = {
      run_id: parsed.run_id,
      codex_requests: parsed.codex_requests,
      guest_turns: parsed.guest_turns,
      answer_only_resumes: parsed.answer_only_resumes,
      max_codex_requests: parsed.max_codex_requests,
      max_guest_turns: parsed.max_guest_turns,
    };
  } catch {
    state = { unavailable: true };
  }
  let events = [];
  try {
    events = readFileSync(RUNTIME_EVENTS, "utf8").trim().split("\n")
      .filter(Boolean).map((line) => JSON.parse(line))
      .filter((item) => item.guest_turn === turn)
      .map((item) => ({
        stage: item.stage,
        guest_turn: item.guest_turn,
        resume_reservation: item.resume_reservation,
        answer_only_resume: item.answer_only_resume,
        receipt_sha256: item.receipt_sha256,
        attempt: item.attempt,
        turn_call: item.turn_call,
        status: item.status,
        latency_ms: item.latency_ms,
        success: item.success,
        usage: item.usage,
        exception_class: item.exception_class,
      }));
  } catch {
    events = [];
  }
  return { state, events };
}

function expectedChecks(turnCase, api, rendered) {
  const expected = turnCase.expected_presentation;
  requireCheck(api.status === "completed" || api.status === "partial_success", `turn ${turnCase.turn}: response status ${api.status}`);
  requireCheck(api.presentation?.language_tag === expected.language_tag, `turn ${turnCase.turn}: API language mismatch`);
  requireCheck(api.presentation?.direction === expected.direction, `turn ${turnCase.turn}: API direction mismatch`);
  requireCheck(api.presentation?.preference_revision === expected.preference_revision, `turn ${turnCase.turn}: presentation revision mismatch`);
  requireCheck(api.language_preference?.language_tag === turnCase.expected_preference_state.language_tag, `turn ${turnCase.turn}: preference language mismatch`);
  requireCheck(api.language_preference?.source === turnCase.expected_preference_state.source, `turn ${turnCase.turn}: preference source mismatch`);
  requireCheck(api.language_preference?.revision === turnCase.expected_preference_state.revision, `turn ${turnCase.turn}: preference revision mismatch`);
  requireCheck(rendered.lang === expected.language_tag && rendered.dir === expected.direction, `turn ${turnCase.turn}: rendered lang/dir mismatch`);
  requireCheck(api.answer_eligibility === "current" && api.presentation?.freshness === "current",
    `turn ${turnCase.turn}: answer or presentation is not current`);
  if (turnCase.expected_brief_version !== undefined) {
    requireCheck(api.guest_brief?.brief_version === turnCase.expected_brief_version, `turn ${turnCase.turn}: brief version mismatch`);
  }
  const state = turnCase.expected_state;
  if (state?.check_in) requireCheck(api.guest_brief?.dates?.check_in === state.check_in, `turn ${turnCase.turn}: check-in mismatch`);
  if (state?.check_out) requireCheck(api.guest_brief?.dates?.check_out === state.check_out, `turn ${turnCase.turn}: checkout mismatch`);
  if (state?.nights !== undefined) requireCheck(api.guest_brief?.dates?.nights === state.nights, `turn ${turnCase.turn}: night count mismatch`);
  if (state?.adults !== undefined) requireCheck(api.guest_brief?.party?.adults === state.adults, `turn ${turnCase.turn}: adult count mismatch`);
  if (state?.children) {
    requireCheck(api.guest_brief?.party?.children?.length === state.children.length, `turn ${turnCase.turn}: child count mismatch`);
    state.children.forEach((child, index) => {
      if (child.age === undefined) return;
      requireCheck(api.guest_brief.party.children[index]?.age === child.age, `turn ${turnCase.turn}: child age mismatch`);
    });
  }
  if (state?.pending_fields) {
    const actualPending = [...(api.guest_brief?.pending_fields ?? [])].sort();
    requireCheck(JSON.stringify(actualPending) === JSON.stringify([...state.pending_fields].sort()),
      `turn ${turnCase.turn}: pending fields mismatch`);
  }
  if (state?.pending_field === "child age") {
    requireCheck(api.guest_brief?.pending_fields?.some((field) => String(field).toLowerCase().includes("age")),
      `turn ${turnCase.turn}: pending child age was not preserved`);
  }
  if (turnCase.expected_facts) {
    const observed = new Set(api.evidence.map((item) => item.fact_id));
    for (const factId of turnCase.expected_facts) requireCheck(observed.has(factId), `turn ${turnCase.turn}: missing evidence ${factId}`);
  }
  if (turnCase.turn === 6) {
    requireCheck(api.answer.includes(turnCase.expected_exact_values.url), "turn 6: exact synthetic URL missing from API answer");
    const normalized = api.answer.replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));
    const numericText = normalized.replace(/(?<=\d)[,٬.\s](?=\d)/g, "");
    requireCheck(numericText.includes("40") && numericText.includes("100000"), "turn 6: parking values changed in API answer");
  }
  if (turnCase.turn === 7) {
    requireCheck(api.guest_brief?.dates?.check_out === "2026-12-14", "turn 7: ambiguous date changed the committed checkout");
  }
  if (turnCase.turn === 8) {
    requireCheck(api.guest_brief?.dates?.check_out === "2026-12-15", "turn 8: explicit checkout date was not committed");
  }
  if (turnCase.turn === 9) {
    requireCheck(api.language_preference?.revision === 8, "turn 9: short/mixed text changed the language revision");
  }
}

const matrix = JSON.parse(await fs.readFile(MATRIX_PATH, "utf8"));
requireCheck(matrix.turns.length === 9 && matrix.limits.max_codex_requests === 18, "Pinned matrix bounds are invalid");
await fs.mkdir(OUTPUT, { recursive: false });
await fs.writeFile(path.join(OUTPUT, "run-meta.json"), JSON.stringify({
  run_id: RUN_ID,
  run_namespace: RUN_NAMESPACE,
  matrix_id: matrix.matrix_id,
  started_at_utc: new Date().toISOString(),
  base_url: BASE_URL,
  mock_api: false,
  browser_submissions_per_turn: 1,
  note: "The browser submits each pinned turn once; the configured application/provider performs approved calls under the persistent runtime caps.",
}, null, 2) + "\n", { mode: 0o600 });

const browser = await chromium.launch({ headless: process.env.STAYLEAD_S6_HEADLESS !== "0", channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });
const baseOrigin = new URL(BASE_URL).origin;
const externalBrowserRequests = [];
context.on("request", (request) => {
  try {
    const requestUrl = new URL(request.url());
    if (requestUrl.origin === baseOrigin) return;
    externalBrowserRequests.push({
      origin: requestUrl.origin,
      url_sha256: nodeCreateHash("sha256").update(request.url()).digest("hex"),
    });
  } catch {
    externalBrowserRequests.push({ origin: "invalid-url", url_sha256: null });
  }
});
const page = await context.newPage();
const observationsPath = path.join(OUTPUT, "observations.jsonl");
const screenshotsDir = path.join(OUTPUT, "turn-screenshots");
await fs.mkdir(screenshotsDir);
let stopReason = null;
let introducedChildHash = null;
let keepBrowserOpen = false;
let resumeObservationIndex = 0;

async function pauseForExplicitAnswerResume(turnCase, partialApi, rawReceiptId) {
  keepBrowserOpen = true;
  let activePartialApi = partialApi;
  let activeReceiptId = rawReceiptId;
  const terminal = createInterface({ input: stdin, output: stdout });
  try {
    while (true) {
      const command = await terminal.question(
        `Turn ${turnCase.turn} is partial. Type continue to click the existing answer-only button, snapshot, or close: `,
      );
      const normalized = command.trim().toLowerCase();
      if (normalized === "snapshot") {
        await page.screenshot({ path: path.join(OUTPUT, "paused-current.png"), fullPage: true });
        console.log("Paused browser screenshot saved; no HTTP request was made.");
        continue;
      }
      if (normalized === "close") {
        keepBrowserOpen = false;
        return { ok: false, reason: "operator closed paused browser" };
      }
      if (normalized !== "continue") {
        console.log("No command submitted. Only continue, snapshot, or close is accepted.");
        continue;
      }
      if (activePartialApi.status !== "partial_success" || typeof activeReceiptId !== "string" || !activeReceiptId) {
        console.log("This response has no resumable partial receipt; no request was sent.");
        continue;
      }
      const receiptHash = hashIdentifier(activeReceiptId);
      const button = page.locator(".message-error button.text-button")
        .filter({ hasText: "Continue the answer using the updated trip details" }).last();
      const buttonCount = await page.locator(".message-error button.text-button")
        .filter({ hasText: "Continue the answer using the updated trip details" }).count();
      if (buttonCount === 0) {
        console.log("The existing Continue answer control is not rendered; no request was sent.");
        continue;
      }
      const beforeState = runtimeSnapshot(turnCase.turn).state;
      const beforeAssistantCount = await page.locator(".message-assistant[lang][dir]").count();
      const responsePromise = page.waitForResponse((candidate) =>
        candidate.request().method() === "POST" && /\/api\/guest\/sessions\/[^/]+\/messages$/.test(candidate.url()),
      { timeout: 60000 }).then((value) => ({ value }), (error) => ({ error }));
      let response = null;
      let requestIssue = null;
      try {
        await button.click();
        const result = await responsePromise;
        if (result.error) throw result.error;
        response = result.value;
      } catch (error) {
        requestIssue = redactText(error.message);
      }
      let rawResponse = null;
      try { rawResponse = response ? await response.json() : { request_error: requestIssue }; }
      catch { rawResponse = { parse_error: true }; }
      const resumedApi = safeApiResponse(rawResponse);
      if (resumedApi.status === "partial_success") {
        activePartialApi = resumedApi;
        if (typeof rawResponse?.brief_receipt?.request_id === "string") {
          activeReceiptId = rawResponse.brief_receipt.request_id;
        }
      }
      const status = response?.status() ?? 0;
      let resumedRendered = null;
      let resumedClipboard = { result: "not_checked", equals_rendered_text: false };
      let semanticIssue = null;
      if (response && status < 400 && resumedApi.status === "completed") {
        try {
          await page.waitForFunction((count) => document.querySelectorAll(".message-assistant[lang][dir]").length > count,
            beforeAssistantCount, { timeout: 60000 });
          const last = page.locator(".message-assistant[lang][dir]").last();
          resumedRendered = await last.evaluate((node) => ({
            lang: node.getAttribute("lang"), dir: node.getAttribute("dir"),
            eligibility: node.getAttribute("data-answer-eligibility"),
            copyEligible: node.getAttribute("data-copy-eligible"),
            answerText: node.querySelector(".answer-copy-source")?.textContent ?? "",
          }));
          requireCheck(resumedRendered.copyEligible === "true", `turn ${turnCase.turn}: resumed answer is not copy eligible`);
          const beforeCopy = runtimeSnapshot(turnCase.turn).state;
          await last.locator(".answer-actions button").last().click();
          await last.locator(".copy-status[data-copy-result='copied']").waitFor({ state: "attached", timeout: 5000 });
          const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
          resumedClipboard = { result: "copied", equals_rendered_text: clipboardText === resumedRendered.answerText };
          const afterCopy = runtimeSnapshot(turnCase.turn).state;
          requireCheck(beforeCopy?.codex_requests === afterCopy?.codex_requests &&
            beforeCopy?.guest_turns === afterCopy?.guest_turns &&
            beforeCopy?.answer_only_resumes === afterCopy?.answer_only_resumes,
          `turn ${turnCase.turn}: resumed copy action changed counters`);
          requireCheck(resumedClipboard.equals_rendered_text, `turn ${turnCase.turn}: resumed clipboard differs from rendered text`);
          expectedChecks(turnCase, resumedApi, resumedRendered);
        } catch (error) {
          semanticIssue = redactText(error.message);
        }
      } else {
        semanticIssue = `answer-only resume returned HTTP ${status} or status ${resumedApi.status}`;
      }
      const screenshot = path.join(OUTPUT, `resume-${String(++resumeObservationIndex).padStart(2, "0")}.png`);
      await page.screenshot({ path: screenshot, fullPage: true }).catch((error) => {
        semanticIssue ??= `resume screenshot failed: ${redactText(error.message)}`;
      });
      const afterState = runtimeSnapshot(turnCase.turn).state;
      const resumeEvidence = {
        parent_turn: turnCase.turn,
        action: "operator_clicked_existing_continue_answer_control",
        receipt_id_sha256: receiptHash,
        http_status: status,
        request_issue: requestIssue,
        api_response: resumedApi,
        rendered: resumedRendered ? {
          lang: resumedRendered.lang, dir: resumedRendered.dir,
          eligibility: resumedRendered.eligibility,
          answer_text: redactText(resumedRendered.answerText),
        } : null,
        clipboard: resumedClipboard,
        counters_before: beforeState,
        counters_after: afterState,
        semantic_result: semanticIssue ? "failed" : "passed",
        semantic_issue: semanticIssue,
        screenshot: path.relative(ROOT, screenshot),
        observed_at_utc: new Date().toISOString(),
      };
      await fs.appendFile(path.join(OUTPUT, "operator-resumes.jsonl"), JSON.stringify(resumeEvidence) + "\n", { mode: 0o600 });
      if (!semanticIssue) {
        keepBrowserOpen = false;
        return { ok: true, api: resumedApi, rendered: resumedRendered, clipboard: resumedClipboard };
      }
      console.error(`Explicit answer-only attempt was recorded and did not pass: ${semanticIssue}. No retry was sent.`);
      if (!response || status >= 400 || resumedApi.status === "partial_success") {
        console.log("The original partial receipt remains available when the UI permits; another attempt requires a new explicit continue command.");
        continue;
      }
      return { ok: false, reason: semanticIssue };
    }
  } finally {
    terminal.close();
  }
}

try {
  await page.goto(`${BASE_URL}/hotels/harbor-city-demo/chat`, { waitUntil: "domcontentloaded", timeout: 30000 });
  const textarea = page.locator("#guest-question");
  await textarea.waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() => {
    const input = document.querySelector("#guest-question");
    return input instanceof HTMLTextAreaElement && !input.disabled;
  }, null, { timeout: 30000 });

  for (const turnCase of matrix.turns) {
    const beforeCount = await page.locator(".message-assistant[lang][dir]").count();
    const submit = page.locator(".chat-composer button[type=submit]");
    await textarea.fill(turnCase.utterance);
    const responsePromise = page.waitForResponse((response) =>
      response.request().method() === "POST" && /\/api\/guest\/sessions\/[^/]+\/messages$/.test(response.url()),
    { timeout: 60000 }).then((value) => ({ value }), (error) => ({ error }));
    let response = null;
    let requestIssue = null;
    try {
      await submit.click();
      const result = await responsePromise;
      if (result.error) throw result.error;
      response = result.value;
    } catch (error) {
      requestIssue = error.message;
    }
    let rawResponse = null;
    try { rawResponse = response ? await response.json() : { request_error: requestIssue }; } catch { rawResponse = { parse_error: true }; }
    let api = safeApiResponse(rawResponse);
    const operatorResumeReceiptId = typeof rawResponse?.brief_receipt?.request_id === "string"
      ? rawResponse.brief_receipt.request_id : null;
    const httpStatus = response?.status() ?? 0;

    let rendered = null;
    let screenshotPath = null;
    let outputIssue = null;
    let clipboard = { result: "not_checked", equals_rendered_text: false };
    if (response && httpStatus < 400) {
      try {
        await page.waitForFunction((count) => document.querySelectorAll(".message-assistant[lang][dir]").length > count,
          beforeCount, { timeout: 60000 });
        const last = page.locator(".message-assistant[lang][dir]").last();
        rendered = await last.evaluate((node) => ({
          lang: node.getAttribute("lang"),
          dir: node.getAttribute("dir"),
          eligibility: node.getAttribute("data-answer-eligibility"),
          copyEligible: node.getAttribute("data-copy-eligible"),
          answerText: node.querySelector(".answer-copy-source")?.textContent ?? "",
          copyButtonCount: node.querySelectorAll(".answer-actions button").length,
        }));
        requireCheck(rendered.answerText.length > 0, `turn ${turnCase.turn}: empty rendered answer`);
        if (rendered.copyEligible === "true") {
          const beforeCopy = runtimeSnapshot(turnCase.turn).state;
          // The final answer action is copy; other labels are localized and vary.
          await last.locator(".answer-actions button").last().click();
          try {
            await last.locator(".copy-status[data-copy-result='copied']").waitFor({ state: "attached", timeout: 5000 });
            const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
            clipboard = { result: "copied", equals_rendered_text: clipboardText === rendered.answerText };
          } catch {
            const copyStatus = await last.locator(".copy-status").getAttribute("data-copy-result").catch(() => null);
            clipboard = { result: copyStatus ?? "unavailable", equals_rendered_text: false };
          }
          const afterCopy = runtimeSnapshot(turnCase.turn).state;
          requireCheck(beforeCopy?.codex_requests === afterCopy?.codex_requests &&
            beforeCopy?.guest_turns === afterCopy?.guest_turns,
          `turn ${turnCase.turn}: copy action changed provider/turn counters`);
        } else {
          clipboard = { result: "answer_not_copy_eligible", equals_rendered_text: false };
          outputIssue = `turn ${turnCase.turn}: rendered answer was not copy-eligible`;
        }
      } catch (error) {
        outputIssue = error.message;
      }
    }
    screenshotPath = path.join(screenshotsDir, `turn-${String(turnCase.turn).padStart(2, "0")}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch((error) => {
      outputIssue ??= `screenshot failed: ${error.message}`;
      screenshotPath = null;
    });

    const observation = {
      turn: turnCase.turn,
      request_id: api.request_id,
      http_status: httpStatus,
      request_issue: requestIssue ? redactText(requestIssue) : null,
      api_response: api,
      rendered: rendered ? {
        lang: rendered.lang,
        dir: rendered.dir,
        eligibility: rendered.eligibility,
        copy_eligible: rendered.copyEligible === "true",
        answer_text: redactText(rendered.answerText),
      } : null,
      clipboard,
      output_issue: outputIssue,
      screenshot: screenshotPath ? path.relative(ROOT, screenshotPath) : null,
      runtime: runtimeSnapshot(turnCase.turn),
      guest_utterance_included: false,
      access_token_included: false,
      observed_at_utc: new Date().toISOString(),
    };
    await fs.appendFile(observationsPath, JSON.stringify(observation) + "\n", { mode: 0o600 });

    // Stop immediately on transport/budget failure after preserving evidence.
    if (!response) {
      stopReason = `turn ${turnCase.turn} did not receive an API response`;
      break;
    }
    const resumablePartial = shouldOfferOperatorResume({
      responseReceived: Boolean(response), httpStatus, apiStatus: api.status, receiptId: operatorResumeReceiptId,
    });
    if (resumablePartial) {
      const resumed = await pauseForExplicitAnswerResume(turnCase, api, operatorResumeReceiptId);
      if (!resumed.ok) {
        stopReason = resumed.reason;
        break;
      }
      api = resumed.api;
      rendered = resumed.rendered;
      clipboard = resumed.clipboard;
      outputIssue = null;
    }
    if (httpStatus >= 400 && !resumablePartial) {
      stopReason = `turn ${turnCase.turn} returned HTTP ${httpStatus}`;
      break;
    }
    if (outputIssue) {
      stopReason = outputIssue;
      break;
    }
    try {
      requireCheck(rendered, `turn ${turnCase.turn}: assistant UI response was not rendered`);
      requireCheck(clipboard.result === "copied" && clipboard.equals_rendered_text,
        `turn ${turnCase.turn}: clipboard did not exactly match rendered answer text`);
      if (turnCase.turn === 2) {
        introducedChildHash = api.guest_brief?.party?.children?.[0]?.member_id_sha256;
        requireCheck(!!introducedChildHash, "turn 2: new child identity was unavailable for continuity check");
      }
      if (turnCase.turn === 3) {
        const continuedChildHash = api.guest_brief?.party?.children?.[0]?.member_id_sha256;
        requireCheck(!!introducedChildHash && continuedChildHash === introducedChildHash,
          "turn 3: child identity changed instead of updating the same child");
      }
      expectedChecks(turnCase, api, rendered);
    } catch (error) {
      stopReason = error.message;
      break;
    }
  }

  if (!stopReason) {
    for (const size of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await delay(100);
      await page.screenshot({ path: path.join(OUTPUT, `final-${size.name}.png`), fullPage: true });
    }
  }
  await fs.writeFile(path.join(OUTPUT, "run-result.json"), JSON.stringify({
    run_id: RUN_ID,
    result: stopReason ? "stopped_with_preserved_partial_evidence_browser_held_open" : "completed_matrix_pending_semantic_review",
    turns_observed: (await fs.readFile(observationsPath, "utf8")).trim().split("\n").filter(Boolean).length,
    stop_reason: stopReason,
    automatic_retry_or_resume_used: false,
    non_provider_external_network_calls: "unmeasured_by_browser_driver",
    external_browser_requests: { scope: "browser-context-only", count: externalBrowserRequests.length, origin_and_url_hashes: externalBrowserRequests },
    provider_network_activity: "handled by the approved Codex CLI runtime; not measured by the browser script",
    semantic_verdict: "not_assigned_by_browser_script",
    reviewer_decision_required: true,
    completed_at_utc: new Date().toISOString(),
  }, null, 2) + "\n", { mode: 0o600 });
  if (stopReason) {
    keepBrowserOpen = true;
    console.error(`Acceptance halted: ${stopReason}. Evidence saved. Browser/session remains open for C-directed recovery; this driver will not submit another turn.`);
    const terminal = createInterface({ input: stdin, output: stdout });
    try {
      while (true) {
        const command = await terminal.question("Paused. Type snapshot to save current state, or close to close browser: ");
        if (command.trim().toLowerCase() === "snapshot") {
          await page.screenshot({ path: path.join(OUTPUT, "paused-current.png"), fullPage: true });
          console.log("Paused browser screenshot saved; no HTTP request was made.");
        } else if (command.trim().toLowerCase() === "close") {
          keepBrowserOpen = false;
          break;
        } else {
          console.log("No command submitted. Only snapshot or close is accepted; this driver will not send another turn.");
        }
      }
    } finally {
      terminal.close();
    }
  }
} catch (error) {
  stopReason = stopReason ?? `browser driver exception: ${redactText(error?.message ?? error).slice(0, 500)}`;
  let screenshot = null;
  try {
    screenshot = path.join(OUTPUT, "driver-exception.png");
    await page.screenshot({ path: screenshot, fullPage: true });
  } catch {
    screenshot = null;
  }
  const observedTurns = await fs.readFile(observationsPath, "utf8").catch(() => "");
  const crashEvidence = {
    run_id: RUN_ID,
    exception_class: error?.constructor?.name ?? "Error",
    message: stopReason,
    screenshot: screenshot ? path.relative(ROOT, screenshot) : null,
    runtime: runtimeSnapshot(0),
    automatic_retry_or_resume_used: false,
    non_provider_external_network_calls: "unmeasured_by_browser_driver",
    external_browser_requests: { scope: "browser-context-only", count: externalBrowserRequests.length, origin_and_url_hashes: externalBrowserRequests },
    observed_at_utc: new Date().toISOString(),
  };
  await fs.appendFile(path.join(OUTPUT, "driver-errors.jsonl"), JSON.stringify(crashEvidence) + "\n", { mode: 0o600 }).catch(() => {});
  await fs.writeFile(path.join(OUTPUT, "run-result.json"), JSON.stringify({
    run_id: RUN_ID,
    result: "driver_exception_preserved_partial_evidence_browser_held_open",
    turns_observed: observedTurns.trim() ? observedTurns.trim().split("\n").filter(Boolean).length : 0,
    stop_reason: stopReason,
    exception_class: crashEvidence.exception_class,
    screenshot: crashEvidence.screenshot,
    automatic_retry_or_resume_used: false,
    semantic_verdict: "not_assigned_by_browser_script",
    reviewer_decision_required: true,
    completed_at_utc: new Date().toISOString(),
  }, null, 2) + "\n", { mode: 0o600 }).catch(() => {});
  keepBrowserOpen = true;
  console.error(`Acceptance driver stopped unexpectedly: ${stopReason}. Error log/run result were saved where possible; browser/session will remain open. No request was retried.`);
  const terminal = createInterface({ input: stdin, output: stdout });
  try {
    while (true) {
      const command = await terminal.question("Paused after driver error. Type snapshot to save current state, or close to close browser: ");
      if (command.trim().toLowerCase() === "snapshot") {
        await page.screenshot({ path: path.join(OUTPUT, "driver-exception-current.png"), fullPage: true }).catch(() => {});
        console.log("Paused browser screenshot saved if the page is still available; no HTTP request was made.");
      } else if (command.trim().toLowerCase() === "close") {
        keepBrowserOpen = false;
        break;
      } else {
        console.log("No command submitted. Only snapshot or close is accepted after a driver error.");
      }
    }
  } finally {
    terminal.close();
  }
} finally {
  if (!keepBrowserOpen) {
    await context.close();
    await browser.close();
  }
}

if (stopReason) process.exitCode = 2;
