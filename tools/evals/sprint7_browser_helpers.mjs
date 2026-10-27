/** Small pure helpers shared with offline tests for bounded browser branches. */
export function selectionOptionForAcceptanceTurn(turnNumber, roomAdvice) {
  if (![1, 2, 4].includes(turnNumber)) return null;
  const options = Array.isArray(roomAdvice?.options) ? roomAdvice.options : [];
  return options.find((option) => typeof option?.option_id === "string" && option.option_id.length > 0) ?? null;
}

/** A useful option has a checked room choice and complete guest assignments. */
export function hasUsefulRoomOptions(roomAdvice) {
  return Array.isArray(roomAdvice?.options) && roomAdvice.options.some((option) =>
    Array.isArray(option?.rooms) && option.rooms.length > 0
      && Array.isArray(option?.assignments) && option.assignments.length > 0);
}

/** Validate the approved Pine party without adding an unrequested child bed constraint. */
export function checkPinePartyBrief(brief, expectedAge) {
  const child = brief?.party?.children?.[0];
  return brief?.party?.adults === 1 && brief.party.children?.length === 1
    && child?.age === expectedAge && typeof child.member_id === "string"
    && brief.party.guardians?.[child.member_id] === "adult-1"
    && hasExactBedSharingConsent(brief, ["adult-1", child.member_id], true)
    ? child.member_id : null;
}

/** A case advances only after its private coordinator semantic receipt is exact and passing. */
export function semanticReviewReceiptValid(receipt, expected) {
  return receipt !== null && typeof receipt === "object"
    && receipt.run_id === expected.run_id
    && receipt.candidate_sha256 === expected.candidate_sha256
    && receipt.approved_case_turn === expected.approved_case_turn
    && receipt.verdict === "pass"
    && receipt.response_sha256 === expected.response_sha256;
}

/** A hard-conflict result cannot expose a selectable option; unknown checks may remain partial. */
export function roomAdviceHardChecksConsistent(roomAdvice) {
  const options = Array.isArray(roomAdvice?.options) ? roomAdvice.options : [];
  if (roomAdvice?.status === "conflict") return options.length === 0;
  return options.every((option) => Array.isArray(option?.checks)
    && option.checks.every((check) => check?.status !== "conflict"));
}

export function hasCanonicalSeparateBedConstraint(brief) {
  return (brief?.room_requirements?.hard_bed_types ?? [])
    .some((bed) => bed === "single" || bed === "twin");
}

/** Separate-bed intent is explicit when sharing is denied or a canonical bed type is required. */
export function hasExplicitSeparateBedResolution(brief) {
  return hasExactBedSharingConsent(brief, ["adult-1", "adult-2"], false)
    || hasCanonicalSeparateBedConstraint(brief);
}

/** This approved City2 case denies sharing without naming a physical bed type. */
export function checkCity2Brief(brief) {
  return brief?.room_requirements?.budget_amount === 6_500_000
    && brief.room_requirements?.budget_strength === "hard"
    && hasExactBedSharingConsent(brief, ["adult-1", "adult-2"], false)
    && !(brief.room_requirements?.hard_bed_types ?? []).length;
}

/** Two adults have separate checked surfaces when they occupy distinct beds or rooms. */
export function hasDistinctAssignedBeds(option, memberIds) {
  const assignments = (option?.assignments ?? []).filter((item) => memberIds.includes(item.member_id));
  if (assignments.length !== memberIds.length) return false;
  const roomIndexes = assignments.map((item) => item.room_index);
  if (!roomIndexes.every(Number.isInteger)) return false;
  const surfaces = assignments.map((item) => Number.isInteger(item.bed_index)
    ? `${item.room_index}:${item.bed_index}` : null);
  if (surfaces.every((surface) => surface !== null)) return new Set(surfaces).size === surfaces.length;
  return new Set(roomIndexes).size === roomIndexes.length;
}

/** Adult consent must name exactly the two adults and allow sharing. */
export function hasExactBedSharingConsent(brief, memberIds, allowShare) {
  if (!Array.isArray(memberIds) || memberIds.length < 2 || typeof allowShare !== "boolean") return false;
  const expected = [...memberIds].sort();
  return (brief?.party?.bed_sharing ?? []).some((group) => {
    const actual = group?.member_ids;
    return group?.allow_share === allowShare && Array.isArray(actual) && actual.length === expected.length
      && [...actual].sort().every((id, index) => id === expected[index]);
  });
}

export function retainsTwoHardAccessibilityNeeds(brief) {
  const needs = brief?.room_requirements?.hard_accessibility_needs ?? [];
  return needs.length === 2 && needs.every((need) => typeof need === "string" && need.trim().length > 0);
}

/** Require the checked-M2 accessibility question to explain hotel verification, not restate needs. */
export function hasUsefulVietnameseAccessibilityVerification(question) {
  return question?.field === "room_requirements.hard_accessibility_needs"
    && question.presentation_key === "question.accessibility_confirmation"
    && question.locale?.toLowerCase().startsWith("vi")
    && question.locale_fallback === false
    && question.reason?.includes("Tôi đã ghi nhận yêu cầu tiếp cận")
    && question.reason?.includes("nhờ khách sạn xác nhận");
}

export function browserRunDirectory(runId, attemptSuffix) {
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/u.test(runId)
      || !/^[a-z0-9][a-z0-9-]{0,15}$/u.test(attemptSuffix)) {
    throw new Error("Invalid private browser run directory identity");
  }
  return `/private/tmp/staylead-s7-browser-${runId}-${attemptSuffix}`;
}

/** Validate the pure-booking UI against only the server-provided channel. */
export function trustedBookingBoundaryValid({ response, channel, anchor, disclosure, channelLanguage }) {
  const responseLanguage = response?.presentation?.language_tag?.toLowerCase().split("-")[0];
  const renderedLanguage = channelLanguage?.toLowerCase().split("-")[0];
  if (!response || response.booking_request?.requested !== true || Object.hasOwn(response, "room_advice")
      || responseLanguage !== "en" || renderedLanguage !== "en") return false;
  const destination = channel?.destination_url;
  if (typeof destination !== "string" || destination !== destination.trim()
      || /[\\\s\u0000-\u001f\u007f]/u.test(destination)) return false;
  let parsed;
  try { parsed = new URL(destination); } catch { return false; }
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash
      || !parsed.hostname || (parsed.port && parsed.port !== "443")) return false;
  if (anchor?.href !== destination || anchor?.target !== "_blank" || anchor?.referrerpolicy !== "no-referrer") return false;
  const rel = new Set((anchor?.rel ?? "").toLowerCase().split(/\s+/u).filter(Boolean));
  if (!rel.has("noopener") || !rel.has("noreferrer")) return false;
  const text = typeof disclosure === "string" ? disclosure : "";
  if (!text.includes("Check price, availability, and terms on the destination site.")
      || !text.includes("does not reserve a room or make a payment")) return false;
  if (channel?.destination_kind === "synthetic_demo"
      && !text.includes("Demonstration link only; it does not open a real booking site.")) return false;
  const visiblePayload = JSON.stringify({ response, channel, anchor, disclosure });
  if (/untrusted\.example|guest@example\.com/iu.test(visiblePayload)) return false;
  return true;
}
