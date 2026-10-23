import type { DomainTarget } from "@/composition/registration";

export type GuestSession = Readonly<{
  session_id: string;
  access_token: string;
  token_type: "Bearer";
  expires_at: string;
  hotel: Record<string, unknown>;
  config_version: string;
}>;

export type GuestEvidence = Readonly<{
  fact_id: string;
  hotel_id: string;
  source_id: string;
  source_version: string;
  section: string;
  fact_version: string;
  imported_at: string;
}>;

export type GuestMessageResponse = Readonly<{
  request_id: string;
  status: "completed";
  answer: string;
  evidence: readonly GuestEvidence[];
  unknowns: readonly string[];
  trace: Readonly<Record<string, unknown>>;
  config_version: string;
  state_version: number;
}>;

export type GuestContractMetadata = Readonly<{
  status: "ok";
  domain: string;
  guest_contract_version: string;
}>;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId?: string;
  readonly outcome: "unknown" | "rejected";

  constructor(args: {
    status: number;
    code: string;
    message: string;
    retryable?: boolean;
    requestId?: string;
    outcome: "unknown" | "rejected";
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code;
    this.retryable = args.retryable ?? false;
    this.requestId = args.requestId;
    this.outcome = args.outcome;
  }
}

// The API turn limit is 45 seconds; allow its response plus proxy transit time.
const REQUEST_TIMEOUT_MS = 52_000;

function endpoint(target: DomainTarget, suffix = ""): string {
  if (!target.apiBasePath.startsWith("/") || target.apiBasePath.startsWith("//")) {
    throw new ApiError({
      status: 0,
      code: "invalid_api_binding",
      message: "The configured API binding is invalid.",
      outcome: "rejected",
    });
  }
  return `${target.apiBasePath}${suffix}`;
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      headers: { accept: "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: "network_outcome_unknown",
      message: "The request did not return a response. Its completion is unknown; retry with the same request ID.",
      retryable: true,
      outcome: "unknown",
    });
  }

  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    const errorBody = body && typeof body === "object" && "error" in body
      ? (body as { error?: unknown }).error
      : undefined;
    const details = errorBody && typeof errorBody === "object"
      ? errorBody as { code?: unknown; message?: unknown; retryable?: unknown }
      : undefined;
    const requestId = body && typeof body === "object" && "request_id" in body
      && typeof (body as { request_id?: unknown }).request_id === "string"
      ? (body as { request_id: string }).request_id
      : undefined;
    throw new ApiError({
      status: response.status,
      code: typeof details?.code === "string" ? details.code : "request_rejected",
      message: typeof details?.message === "string" ? details.message : "The request was rejected.",
      retryable: details?.retryable === true,
      requestId,
      outcome: typeof details?.code === "string" && details.code.startsWith("api_proxy_")
        ? "unknown"
        : "rejected",
    });
  }

  try {
    return await response.json() as T;
  } catch {
    throw new ApiError({
      status: response.status,
      code: "invalid_api_response",
      message: "The service returned an unreadable response.",
      retryable: true,
      outcome: "unknown",
    });
  }
}

export async function getGuestContract(
  target: DomainTarget,
): Promise<GuestContractMetadata> {
  const metadata = await request<GuestContractMetadata>(endpoint(target, "/health"));
  if (
    metadata.status !== "ok"
    || metadata.domain !== target.domain
    || metadata.guest_contract_version !== target.guestContractVersion
  ) {
    throw new ApiError({
      status: 409,
      code: "contract_mismatch",
      message: "The selected website and API target are incompatible. No guest data was sent.",
      outcome: "rejected",
    });
  }
  return metadata;
}

export async function createGuestSession(args: {
  hotelSlug: string;
  target: DomainTarget;
}): Promise<GuestSession> {
  await getGuestContract(args.target);
  return request<GuestSession>(endpoint(args.target, "/sessions"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ hotel_slug: args.hotelSlug }),
  });
}

export async function sendGuestMessage(args: {
  sessionId: string;
  accessToken: string;
  requestId: string;
  question: string;
  target: DomainTarget;
}): Promise<GuestMessageResponse> {
  const sessionId = encodeURIComponent(args.sessionId);
  return request<GuestMessageResponse>(endpoint(args.target, `/sessions/${sessionId}/messages`), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${args.accessToken}`,
    },
    body: JSON.stringify({ request_id: args.requestId, question: args.question }),
  });
}
