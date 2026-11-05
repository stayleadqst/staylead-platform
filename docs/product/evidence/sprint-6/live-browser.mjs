#!/usr/bin/env node
/**
 * One-session, real-API browser driver for the pinned Sprint 6 nine-turn matrix.
 * It never mocks the API, retries, resumes, reloads, or logs session tokens.
 * C executes this only after live-run approval and after API/UI are already up.
 *
 *   node docs/product/evidence/sprint-6/live-browser.mjs
 */

import fs from "node:fs/promises";
import { readFileSync } from "node:fs";
import { createHash as nodeCreateHash } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const { chromium } = await import(pathToFileURL(
  "/Users/ccvn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs",
).href);

const ROOT = process.cwd();
const MATRIX_PATH = path.join(ROOT, "docs/product/evidence/sprint-6/live-cases.json");
const OUTPUT = path.join(ROOT, "docs/product/evidence/sprint-6/live-run");
const BASE_URL = process.env.STAYLEAD_S6_WEB_URL ?? "http://127.0.0.1:13016";
const RUNTIME_STATE = "/private/tmp/staylead-sprint6-run-state.json";
const RUNTIME_EVENTS = "/private/tmp/staylead-sprint6-runtime-events.jsonl";

function requireCheck(condition, message) {
  if (!condition) throw new Error(message);
}

function redactText(value) {
  return String(value ?? "")
    .replace(/\bBearer\s+[^\s,"}]+/gi, "Bearer <redacted>")
    .replace(/\b(sk-[A-Za-z0-9_-]{12,})\b/g, "<redacted>")
    .replace(/\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, "<redacted>");
}

function safePresentation(value) {
  if (!value || typeof value !== "object") return null;
  return {
    language_tag: value.language_tag ?? null,
    direction: value.direction ?? null,
    preference_revision: value.preference_revision ?? null,
    freshness: value.freshness ?? null,
    receipt_id: value.receipt_id ?? null,
    labels_fallback: value.labels_fallback ?? null,
  };
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
    request_id: value.brief_receipt.request_id ?? null,
    status: value.brief_receipt.status ?? null,
    brief_version_before: value.brief_receipt.brief_version_before ?? null,
    brief_version_after: value.brief_receipt.brief_version_after ?? null,
    answer_status: value.brief_receipt.answer_status ?? null,
    brief_version_used: value.brief_receipt.brief_version_used ?? null,
  } : null;
  return {
    request_id: value.request_id ?? null,
    status: value.status ?? null,
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
  matrix_id: matrix.matrix_id,
  started_at_utc: new Date().toISOString(),
  base_url: BASE_URL,
  mock_api: false,
  browser_submissions_per_turn: 1,
  note: "The browser submits each pinned turn once; the configured application/provider performs approved calls under the persistent runtime caps.",
}, null, 2) + "\n", { mode: 0o600 });

const browser = await chromium.launch({ headless: true, channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });
const page = await context.newPage();
const observationsPath = path.join(OUTPUT, "observations.jsonl");
const screenshotsDir = path.join(OUTPUT, "turn-screenshots");
await fs.mkdir(screenshotsDir);
let stopReason = null;
let introducedChildHash = null;

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
    { timeout: 60000 });
    let response = null;
    let requestIssue = null;
    try {
      await submit.click();
      response = await responsePromise;
    } catch (error) {
      requestIssue = error.message;
    }
    let rawResponse = null;
    try { rawResponse = response ? await response.json() : { request_error: requestIssue }; } catch { rawResponse = { parse_error: true }; }
    const api = safeApiResponse(rawResponse);
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
        } else {
          clipboard = { result: "answer_not_copy_eligible", equals_rendered_text: false };
          outputIssue = `turn ${turnCase.turn}: rendered answer was not copy-eligible`;
        }
      } catch (error) {
        outputIssue = error.message;
      }
      screenshotPath = path.join(screenshotsDir, `turn-${String(turnCase.turn).padStart(2, "0")}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: true }).catch((error) => {
        outputIssue ??= `screenshot failed: ${error.message}`;
        screenshotPath = null;
      });
    }

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
    if (httpStatus >= 400) {
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
    result: stopReason ? "stopped_with_preserved_partial_evidence" : "completed_matrix_pending_semantic_review",
    turns_observed: (await fs.readFile(observationsPath, "utf8")).trim().split("\n").filter(Boolean).length,
    stop_reason: stopReason,
    automatic_retry_or_resume_used: false,
    non_provider_external_network_calls: 0,
    provider_network_activity: "handled by the approved Codex CLI runtime; not measured by the browser script",
    semantic_verdict: "not_assigned_by_browser_script",
    reviewer_decision_required: true,
    completed_at_utc: new Date().toISOString(),
  }, null, 2) + "\n", { mode: 0o600 });
} finally {
  await context.close();
  await browser.close();
}

if (stopReason) process.exitCode = 2;
