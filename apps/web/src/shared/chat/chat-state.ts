export type FailureInput = Readonly<{
  code?: string;
  retryable?: boolean;
  outcome?: "unknown" | "rejected";
}>;

export type RetryMode = "same-request" | "new-request" | "new-session" | "none";

export function classifyFailure(error: FailureInput): { message: string; retryMode: RetryMode } {
  if (error.outcome === "unknown" || error.code === "request_in_progress") {
    return {
      message: "Your request may still be processing. Retry to check the same request.",
      retryMode: "same-request",
    };
  }
  if (error.code === "request_failed") {
    return {
      message: "That request ended without an answer. Retry to submit it as a new request.",
      retryMode: "new-request",
    };
  }
  if (error.code === "invalid_session" || error.code === "session_scope_mismatch") {
    return {
      message: "This chat session is no longer valid. Start a new chat to continue.",
      retryMode: "new-session",
    };
  }
  if (error.code === "provider_auth") {
    return {
      message: "The hotel assistant is temporarily unavailable. Your question is still here; try again later.",
      retryMode: "none",
    };
  }
  if (error.code === "stale_source") {
    return {
      message: "Hotel records changed while this answer was being prepared. Ask again to use the latest records.",
      retryMode: "none",
    };
  }
  if (error.outcome === "rejected" && error.retryable) {
    return {
      message: "The previous attempt failed. Retry to submit it as a new request.",
      retryMode: "new-request",
    };
  }
  return {
    message: "We could not answer this request. You can ask a new question or start a new chat.",
    retryMode: "none",
  };
}

export function canStartRequest(
  hasSession: boolean,
  activeRequestForCurrentSession: boolean,
  unresolvedRequest = false,
): boolean {
  return hasSession && !activeRequestForCurrentSession && !unresolvedRequest;
}

export function hasUnresolvedRequest(turns: readonly { retryMode?: RetryMode }[]): boolean {
  return turns.some((turn) => turn.retryMode === "same-request");
}

export function classifySessionFailure(error: FailureInput): { message: string; retryable: boolean } {
  if (error.code === "hotel_unavailable") {
    return {
      message: "This hotel is not available yet. Check the hotel link or try again after it has been added.",
      retryable: false,
    };
  }
  if (error.code === "contract_mismatch") {
    return {
      message: "This website and the chat service use incompatible versions, so a chat session was not opened.",
      retryable: false,
    };
  }
  if (error.outcome === "unknown" || (error.outcome === "rejected" && error.retryable)) {
    return {
      message: "We could not start a chat right now. Please try again.",
      retryable: true,
    };
  }
  return {
    message: "We could not start a chat for this hotel.",
    retryable: false,
  };
}

export function claimRequest(
  generation: number,
  lock: { current: number | null },
): boolean {
  if (lock.current === generation) return false;
  lock.current = generation;
  return true;
}

export function releaseRequest(generation: number, lock: { current: number | null }): void {
  if (lock.current === generation) lock.current = null;
}

export function isCurrentGeneration(expected: number, actual: number): boolean {
  return expected === actual;
}
