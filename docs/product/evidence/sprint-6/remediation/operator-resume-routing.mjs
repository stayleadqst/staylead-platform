/** Pure routing decision shared by the real browser driver and offline tests. */
export function shouldOfferOperatorResume({ responseReceived, httpStatus, apiStatus, receiptId }) {
  return responseReceived === true &&
    Number.isInteger(httpStatus) && httpStatus >= 200 && httpStatus <= 599 &&
    apiStatus === "partial_success" &&
    typeof receiptId === "string" && receiptId.length > 0 && receiptId.length <= 512;
}

export function canAdvanceAfterKnownPartial({
  responseReceived, httpStatus, apiStatus, receiptStatus, receiptId,
  receiptMatchesRuntimeRequest, persistedState, expectedRunId, turn, nextPinnedTurnAvailable,
}) {
  return responseReceived === true &&
    Number.isInteger(httpStatus) && httpStatus >= 200 && httpStatus <= 599 &&
    apiStatus === "partial_success" &&
    receiptStatus === "partial_success" &&
    typeof receiptId === "string" && receiptId.length > 0 && receiptId.length <= 512 &&
    receiptMatchesRuntimeRequest === true &&
    expectedRunId === persistedState?.run_id &&
    persistedState?.authorized_for_live_calls === true &&
    Number.isInteger(turn) && turn >= 1 && persistedState?.guest_turns === turn &&
    persistedState?.max_guest_turns === 9 &&
    persistedState?.max_codex_requests === 18 &&
    Number.isInteger(persistedState?.codex_requests) &&
    persistedState.codex_requests >= 1 && persistedState.codex_requests < 18 &&
    persistedState?.max_calls_per_turn === 2 &&
    nextPinnedTurnAvailable === true;
}

export function matchesRuntimeReceiptRequest({ receiptIdHash, runtimeEvents, turn }) {
  if (typeof receiptIdHash !== "string" || !/^[a-f0-9]{16}$/.test(receiptIdHash) ||
      !Array.isArray(runtimeEvents) || !Number.isInteger(turn)) return false;
  const hashes = new Set(runtimeEvents
    .filter((event) => event?.stage === "provider_call_started" && event.guest_turn === turn)
    .map((event) => event.turn_request_id_sha256)
    .filter((hash) => typeof hash === "string" && /^[a-f0-9]{16}$/.test(hash)));
  return hashes.size === 1 && hashes.has(receiptIdHash);
}
