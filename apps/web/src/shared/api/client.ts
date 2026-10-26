import type { DomainTarget } from "@/composition/registration";

export type GuestSession = Readonly<{
  session_id: string;
  access_token: string;
  token_type: "Bearer";
  expires_at: string;
  hotel: Record<string, unknown>;
  config_version: string;
  language_preference?: GuestLanguagePreference;
}>;

export type GuestLanguagePreference = Readonly<{
  language_tag: string;
  source: "explicit" | "inferred" | "fallback";
  revision: number;
}>;

export type GuestPresentation = Readonly<{
  language_tag: string;
  direction: "ltr" | "rtl";
  preference_revision: number;
  labels: Readonly<Record<string, string>>;
  labels_fallback?: boolean;
  freshness: "current" | "stale";
  receipt_id: string | null;
}>;

export type GuestEvidence = Readonly<{
  fact_id: string;
  hotel_id: string;
  source_id: string;
  source_version: string;
  source_hash: string;
  source_generation: number;
  section: string;
  fact_version: string;
  imported_at: string;
}>;

export type GuestMediaDescriptor = Readonly<{
  media_id: string;
  hotel_id: string;
  fact_ids: readonly string[];
  kind: "image" | "video";
  mime_type: "image/png" | "video/mp4";
  byte_size: number;
  sha256: string;
  caption: string;
  alt_text: string;
  source_id: string;
  source_version: string;
  source_hash: string;
  source_generation: number;
  start_seconds?: number;
  end_seconds?: number;
  duration_seconds?: number;
  captions_media_id?: string;
  captions_sha256?: string;
}>;

export type GuestHotel = Readonly<{
  hotel_id: string;
  hotel_slug: string;
  public_config: Record<string, unknown>;
  config_version: string;
  guest_contract_version: string;
}>;

export type GuestMessageResponse = Readonly<{
  request_id: string;
  status: "completed" | "partial_success";
  answer?: string;
  evidence?: readonly GuestEvidence[];
  media?: readonly GuestMediaDescriptor[];
  unknowns?: readonly string[];
  guest_claims?: readonly Readonly<{ text: string; refs: readonly string[] }>[];
  trace?: Readonly<Record<string, unknown>>;
  config_version?: string;
  state_version?: number;
  source_generation?: number;
  guest_brief?: GuestBriefSnapshot;
  brief_receipt?: GuestBriefReceipt | null;
  applied_delta?: Record<string, unknown>;
  answer_status?: "pending" | "completed" | "failed";
  brief_version_used?: number | null;
  brief_dependent?: boolean;
  brief_narrative_stale?: boolean;
  replayed?: boolean;
  error?: Readonly<{ code: string; message: string }>;
  language_preference?: GuestLanguagePreference;
  presentation?: GuestPresentation;
  answer_eligibility?: "current" | "pending" | "stale";
}>;

export type GuestBriefMember = Readonly<{ member_id: string; age: number | null }>;
export type GuestBriefSnapshot = Readonly<{
  brief_version: number;
  dates: Readonly<{ check_in: string | null; check_out: string | null; nights: number | null }>;
  party: Readonly<{ adults: number | null; children: readonly GuestBriefMember[] }>;
  pending_fields: readonly string[];
}>;
export type GuestBriefReceipt = Readonly<{
  request_id: string;
  status: "applied" | "no_change" | "clarification" | "partial_success";
  brief_version_before: number;
  brief_version_after: number;
  applied_delta: Record<string, unknown>;
  source_refs: readonly Readonly<{ source_utterance_id: string; request_id: string; fields: readonly string[] }>[];
  answer_status: "pending" | "completed" | "failed";
  brief_version_used: number | null;
}>;

export type GuestPartialResult = Readonly<{
  request_id: string;
  status: "partial_success";
  guest_brief: GuestBriefSnapshot;
  brief_receipt: GuestBriefReceipt;
  applied_delta: Record<string, unknown>;
  answer_status: "failed";
  error: Readonly<{ code: string; message: string }>;
}>;

export type GuestFreshnessResponse = Readonly<{ status: "current" | "stale" }>;

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
  readonly partialResult?: GuestPartialResult;

  constructor(args: {
    status: number;
    code: string;
    message: string;
    retryable?: boolean;
    requestId?: string;
    outcome: "unknown" | "rejected";
    partialResult?: GuestPartialResult;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code;
    this.retryable = args.retryable ?? false;
    this.requestId = args.requestId;
    this.outcome = args.outcome;
    this.partialResult = args.partialResult;
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
      partialResult: body && typeof body === "object" && "status" in body
        && (body as { status?: unknown }).status === "partial_success"
        ? body as GuestPartialResult
        : undefined,
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
  await getGuestHotel({ hotelSlug: args.hotelSlug, target: args.target });
  return request<GuestSession>(endpoint(args.target, "/sessions"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ hotel_slug: args.hotelSlug }),
  });
}

export async function getGuestHotel(args: { hotelSlug: string; target: DomainTarget }): Promise<GuestHotel> {
  const slug = encodeURIComponent(args.hotelSlug);
  const hotel = await request<GuestHotel>(endpoint(args.target, `/hotels/${slug}`));
  if (hotel.hotel_slug !== args.hotelSlug || hotel.guest_contract_version !== args.target.guestContractVersion) {
    throw new ApiError({
      status: 409,
      code: "hotel_contract_mismatch",
      message: "This hotel is not available for the selected website.",
      outcome: "rejected",
    });
  }
  return hotel;
}

export async function sendGuestMessage(args: {
  sessionId: string;
  accessToken: string;
  requestId: string;
  question?: string;
  answerOnlyReceiptId?: string;
  target: DomainTarget;
}): Promise<GuestMessageResponse> {
  const sessionId = encodeURIComponent(args.sessionId);
  return request<GuestMessageResponse>(endpoint(args.target, `/sessions/${sessionId}/messages`), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${args.accessToken}`,
    },
    body: JSON.stringify({ request_id: args.requestId, ...(args.question ? { question: args.question } : {}),
      ...(args.answerOnlyReceiptId ? { answer_only_receipt_id: args.answerOnlyReceiptId } : {}) }),
  });
}

export async function fetchGuestMedia(args: {
  sessionId: string;
  media: GuestMediaDescriptor;
  mediaId?: string;
  sha256?: string;
  accessToken: string;
  target: DomainTarget;
  signal: AbortSignal;
}): Promise<Blob> {
  const sessionId = encodeURIComponent(args.sessionId);
  const requestedMediaId = args.mediaId ?? args.media.media_id;
  const mediaId = encodeURIComponent(requestedMediaId);
  const query = new URLSearchParams({
    generation: String(args.media.source_generation),
    source_id: args.media.source_id,
    source_version: args.media.source_version,
    source_hash: args.media.source_hash,
    sha256: args.sha256 ?? args.media.sha256,
  });
  let response: Response;
  try {
    response = await fetch(endpoint(args.target, `/sessions/${sessionId}/media/${mediaId}?${query}`), {
      method: "GET",
      cache: "no-store",
      signal: args.signal,
      headers: { accept: "image/png, video/mp4, text/vtt", authorization: `Bearer ${args.accessToken}` },
    });
  } catch {
    throw new ApiError({ status: 0, code: "media_unavailable", message: "Hotel media could not be loaded.", retryable: true, outcome: "unknown" });
  }
  if (!response.ok) {
    throw new ApiError({ status: response.status, code: "media_unavailable", message: "Hotel media could not be loaded.", outcome: "rejected" });
  }
  const mime = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  if (!mime || !["image/png", "video/mp4", "text/vtt"].includes(mime)) {
    throw new ApiError({ status: 502, code: "invalid_media_type", message: "Hotel media could not be displayed.", outcome: "rejected" });
  }
  return response.blob();
}

export async function checkGuestFreshness(args: {
  sessionId: string;
  accessToken: string;
  requestId: string;
  target: DomainTarget;
}): Promise<GuestFreshnessResponse> {
  const sessionId = encodeURIComponent(args.sessionId);
  return request<GuestFreshnessResponse>(endpoint(args.target, `/sessions/${sessionId}/freshness`), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${args.accessToken}`,
    },
    body: JSON.stringify({ request_id: args.requestId }),
  });
}
