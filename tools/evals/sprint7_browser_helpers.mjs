/** Small pure helpers shared with offline tests for bounded browser branches. */
export function selectionOptionForAcceptanceTurn(turnNumber, roomAdvice) {
  if (turnNumber !== 7) return null;
  const options = Array.isArray(roomAdvice?.options) ? roomAdvice.options : [];
  return options.find((option) => typeof option?.option_id === "string" && option.option_id.length > 0) ?? null;
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

export function retainsTwoHardAccessibilityNeeds(brief) {
  const needs = brief?.room_requirements?.hard_accessibility_needs ?? [];
  return needs.length === 2 && needs.every((need) => typeof need === "string" && need.trim().length > 0);
}

/** A turn's explicit pair-sharing authorization must be present in persisted M2 before continuing. */
export function hasExactBedSharingConsent(brief, memberIds, allowShare) {
  if (!Array.isArray(memberIds) || memberIds.length < 2 || typeof allowShare !== "boolean") return false;
  const expected = [...memberIds].sort();
  return (brief?.party?.bed_sharing ?? []).some((group) => {
    const actual = group?.member_ids;
    return group?.allow_share === allowShare && Array.isArray(actual) && actual.length === expected.length
      && [...actual].sort().every((id, index) => id === expected[index]);
  });
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
