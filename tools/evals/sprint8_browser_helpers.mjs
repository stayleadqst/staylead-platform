/** Pure checks shared by the Sprint 8 local-guide browser controller and offline tests. */
import { createHash } from "node:crypto";

export const sha256 = (value) => createHash("sha256").update(value).digest("hex");

/** API startup hands its freshly validated authorized namespace to the browser as running. */
export function freshRuntimeHandoffReady(state) {
  return state?.authorized_for_live_calls === true
    && (state.status === "authorized" || state.status === "running")
    && state.guest_turns === 0 && state.approved_case_turn === 0 && state.requests === 0;
}

/** Choose the latest exact-question turn so a same-session prior card cannot satisfy this turn. */
export function latestTurnForQuestion(turns, question) {
  if (!Array.isArray(turns) || typeof question !== "string") return null;
  return [...turns].reverse().find((turn) => turn?.question === question) ?? null;
}

/** Save exact turn evidence before applying any semantic oracle to it. */
export async function persistBeforeEvaluation({ report, record, persist, counterSnapshot, captureScreenshot, evaluate }) {
  try {
    record.counter_snapshot = await counterSnapshot();
  } catch (error) {
    record.counter_snapshot_error = { name: error?.name ?? "Error", message: error?.message ?? String(error) };
  }
  try {
    record.screenshot = await captureScreenshot();
  } catch (error) {
    record.screenshot_error = { name: error?.name ?? "Error", message: error?.message ?? String(error) };
  }
  const index = Number.isInteger(record.turn) && record.turn > 0 ? record.turn - 1 : report.turns.length;
  report.turns[index] = record;
  await persist(report);
  record.evidence_persisted = true;
  return evaluate();
}

export function browserRunDirectory(runId, attempt) {
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/u.test(runId) || !/^[a-z0-9][a-z0-9-]{0,15}$/u.test(attempt)) {
    throw new Error("Invalid Sprint 8 private run identity");
  }
  return `/private/tmp/staylead-s8-browser-${runId}-${attempt}`;
}

export function semanticReviewReceiptValid(receipt, expected) {
  return receipt !== null && typeof receipt === "object"
    && receipt.run_id === expected.run_id
    && receipt.candidate_sha256 === expected.candidate_sha256
    && receipt.approved_case_turn === expected.approved_case_turn
    && receipt.verdict === "pass"
    && receipt.response_sha256 === expected.response_sha256;
}

const localizedLanguage = (tag) => typeof tag === "string" ? tag.toLowerCase().split("-")[0] : "";
const rtl = new Set(["ar", "fa", "he", "ur"]);

/** Validate the response/body against an independently pinned per-case oracle. */
export function localGuideAcceptanceCheck({ response, rendered, expected, language }) {
  const guide = response?.local_guide;
  if (!guide || !Array.isArray(guide.supported_claims) || !Array.isArray(guide.source_refs)) return { ok: false, reason: "missing_local_guide_or_sources" };
  const ids = guide.supported_claims.map((claim) => claim.venue_id);
  if (expected.preferred_venue_ids && expected.preferred_venue_ids.some((id) => !ids.includes(id))) return { ok: false, reason: "expected_venue_missing" };
  if (expected.excluded && expected.excluded.some((id) => ids.includes(id))) return { ok: false, reason: "closed_or_expired_venue_exposed" };
  const claims = new Map(guide.supported_claims.map((claim) => [claim.venue_id, claim]));
  for (const [venueId, facts] of Object.entries(expected.claims ?? {})) {
    const claim = claims.get(venueId);
    if (!claim) return { ok: false, reason: `claim_missing:${venueId}` };
    if (facts.price_amount !== undefined && claim.price?.amount !== facts.price_amount) return { ok: false, reason: `price_mismatch:${venueId}` };
    if (facts.price_currency !== undefined && claim.price?.currency !== facts.price_currency) return { ok: false, reason: `currency_mismatch:${venueId}` };
    if (facts.price_basis !== undefined && claim.price?.basis !== facts.price_basis) return { ok: false, reason: `price_basis_mismatch:${venueId}` };
    if (facts.duration_minutes !== undefined && claim.duration_minutes !== facts.duration_minutes) return { ok: false, reason: `duration_mismatch:${venueId}` };
    if (facts.sponsored !== undefined && claim.sponsored !== facts.sponsored) return { ok: false, reason: `sponsorship_mismatch:${venueId}` };
    if (facts.hours_status !== undefined && claim.hours_status !== facts.hours_status) return { ok: false, reason: `hours_status_mismatch:${venueId}` };
    if (facts.fit_status !== undefined && claim.fit_status !== facts.fit_status) return { ok: false, reason: `fit_status_mismatch:${venueId}` };
    if (facts.conflict_fields && facts.conflict_fields.some((field) => !claim.conflict_fields.includes(field))) return { ok: false, reason: `conflict_missing:${venueId}` };
    if (facts.unknown_codes && facts.unknown_codes.some((code) => !(claim.unknown_codes ?? []).includes(code))) return { ok: false, reason: `unknown_code_missing:${venueId}` };
  }
  if (expected.required_localized_unknowns_rendered) {
    const claimsWithUnknowns = guide.supported_claims.filter((claim) =>
      Array.isArray(claim.unknown_codes) && claim.unknown_codes.length > 0,
    );
    if (!claimsWithUnknowns.length) return { ok: false, reason: "localized_unknown_codes_missing" };
    for (const claim of claimsWithUnknowns) {
      const labels = claim.localized_unknowns;
      if (!Array.isArray(labels) || labels.length < claim.unknown_codes.length
          || labels.some((label) => typeof label !== "string" || !label.trim() || !rendered?.text?.includes(label))) {
        return { ok: false, reason: `localized_unknown_not_rendered:${claim.venue_id}` };
      }
    }
  }
  if (expected.no_certified_dining_fit_without_positive_evidence
      && guide.supported_claims.some((claim) => claim.kind === "dining" && claim.fit_status === "fit")) return { ok: false, reason: "hard_need_certified_without_proof" };
  if (expected.no_booking && response.booking_request?.requested === true) return { ok: false, reason: "unexpected_booking_request" };
  const responseLanguage = localizedLanguage(response.presentation?.language_tag);
  const actualLanguage = localizedLanguage(language);
  if (responseLanguage !== actualLanguage || rendered?.lang?.toLowerCase() !== language.toLowerCase()) return { ok: false, reason: "locale_mismatch" };
  if (rtl.has(actualLanguage) && rendered?.dir !== "rtl") return { ok: false, reason: "rtl_direction_missing" };
  for (const [field, wanted] of Object.entries(expected.m2 ?? {})) {
    const actual = response.guest_brief?.local_guide_preferences?.[field];
    if (JSON.stringify(actual) !== JSON.stringify(wanted)) return { ok: false, reason: `m2_field_mismatch:${field}` };
  }
  const sourceIds = new Set(guide.source_refs.flatMap((row) => {
    const id = row?.source?.source_id ?? row?.source_id;
    return typeof id === "string" && Array.isArray(row?.fact_ids) && row.fact_ids.length ? [id] : [];
  }));
  if (!sourceIds.size || [...sourceIds].some((id) => typeof id !== "string" || !id)) return { ok: false, reason: "source_provenance_missing" };
  if (expected.required_source_ids && expected.required_source_ids.some((id) => !sourceIds.has(id))) return { ok: false, reason: "required_source_missing" };
  for (const source of expected.sources ?? []) {
    const bound = guide.source_refs.find((row) => (row?.source?.source_id ?? row?.source_id) === source.source_id);
    const data = bound?.source ?? bound;
    if (!data || (source.status && data.status !== source.status)
        || (source.version && data.source_version !== source.version)
        || (source.generation !== undefined && data.source_generation !== source.generation)
        || !Array.isArray(bound.fact_ids) || !bound.fact_ids.length) return { ok: false, reason: `source_binding_mismatch:${source.source_id}` };
  }
  const answer = response.answer ?? "";
  for (const number of expected.required_answer_numbers ?? []) if (!answer.includes(String(number))) return { ok: false, reason: `answer_number_missing:${number}` };
  for (const number of expected.forbidden_answer_numbers ?? []) if (answer.includes(String(number))) return { ok: false, reason: `answer_number_unverified:${number}` };
  for (const phrase of expected.forbidden_answer_phrases ?? []) if (answer.toLowerCase().includes(String(phrase).toLowerCase())) return { ok: false, reason: "forbidden_answer_phrase" };
  for (const phrase of expected.required_rendered_phrases ?? []) if (!rendered?.text?.includes(phrase)) return { ok: false, reason: "required_localized_phrase_missing" };
  return { ok: true, venue_ids: ids, source_ids: [...sourceIds] };
}

export function hardNeedsPreserved(before, after) {
  const oldNeeds = before?.local_guide_preferences?.hard_needs ?? [];
  const newNeeds = after?.local_guide_preferences?.hard_needs ?? [];
  const sameValues = (left, right) => {
    if (Array.isArray(left) && Array.isArray(right)) {
      const sortedLeft = left.map((value) => JSON.stringify(value)).sort();
      const sortedRight = right.map((value) => JSON.stringify(value)).sort();
      return JSON.stringify(sortedLeft) === JSON.stringify(sortedRight);
    }
    return JSON.stringify(left) === JSON.stringify(right);
  };
  if (oldNeeds.length || newNeeds.length) return oldNeeds.length > 0 && sameValues(oldNeeds, newNeeds);
  const oldPrefs = before?.local_guide_preferences ?? {};
  const newPrefs = after?.local_guide_preferences ?? {};
  return ["hard_accessibility_needs", "allergy_requirements", "child_safety_required"]
    .some((field) => oldPrefs[field] !== undefined)
    && ["hard_accessibility_needs", "allergy_requirements", "child_safety_required"]
      .every((field) => sameValues(oldPrefs[field], newPrefs[field]));
}
