import { NextResponse, type NextRequest } from "next/server";
import { buildUpstreamUrl } from "@/shared/api/proxy-url";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 8 * 1024;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_VIDEO_BYTES = 20 * 1024 * 1024;
const MAX_CAPTIONS_BYTES = 256 * 1024;
// The API owns a 45-second whole-turn deadline; leave a small transport margin.
const UPSTREAM_TIMEOUT_MS = 50_000;
const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SAFE_ID_PATTERN = /^[A-Za-z0-9._:-]{1,120}$/;

type RouteContext = { params: Promise<{ path: string[] }> };

function proxyError(status: number, code: string, message: string, retryable = false) {
  return NextResponse.json(
    { error: { code, message, retryable } },
    { status, headers: { "cache-control": "no-store" } },
  );
}

function getBackendBase(): URL | undefined {
  const configured = process.env.STAYLEAD_API_BASE_URL;
  if (!configured) return undefined;
  try {
    const base = new URL(configured);
    if (
      (base.protocol !== "https:" && !(base.protocol === "http:" && ["localhost", "127.0.0.1"].includes(base.hostname)))
      || base.username || base.password || base.search || base.hash
    ) return undefined;
    return base;
  } catch {
    return undefined;
  }
}

async function readBoundedBody(request: NextRequest): Promise<string | undefined> {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BODY_BYTES) {
      await reader.cancel();
      return undefined;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}

async function readBoundedResponse(response: Response, limit: number): Promise<Uint8Array | undefined> {
  if (!response.body) return new Uint8Array();
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      return undefined;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

async function forward(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const method = request.method.toUpperCase();
  let backendPath: string;
  let requiresJsonBody = false;
  let binaryLimit: number | undefined;

  if (method === "GET" && path.length === 1 && path[0] === "health") {
    backendPath = "/health";
  } else if (method === "GET" && path.length === 2 && path[0] === "hotels" && /^[a-z0-9-]{1,120}$/.test(path[1])) {
    backendPath = `/v1/guest/hotels/${path[1]}`;
  } else if (method === "POST" && path.length === 1 && path[0] === "sessions") {
    backendPath = "/v1/guest/sessions";
    requiresJsonBody = true;
  } else if (
    method === "POST" && path.length === 3 && path[0] === "sessions"
    && SESSION_ID_PATTERN.test(path[1]) && path[2] === "messages"
  ) {
    backendPath = `/v1/guest/sessions/${path[1]}/messages`;
    requiresJsonBody = true;
  } else if (
    method === "GET" && path.length === 4 && path[0] === "sessions"
    && SESSION_ID_PATTERN.test(path[1]) && path[2] === "media" && SAFE_ID_PATTERN.test(path[3])
  ) {
    backendPath = `/v1/guest/sessions/${path[1]}/media/${encodeURIComponent(path[3])}`;
    binaryLimit = MAX_VIDEO_BYTES;
  } else {
    return proxyError(404, "proxy_route_not_found", "This API route is not available.");
  }

  const base = getBackendBase();
  if (!base) {
    return proxyError(503, "api_target_unavailable", "The guest API target is not configured.");
  }

  let body: string | undefined;
  if (requiresJsonBody) {
    if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
      return proxyError(415, "unsupported_media_type", "A JSON request body is required.");
    }
    body = await readBoundedBody(request);
    if (body === undefined) return proxyError(413, "request_too_large", "The request body is too large.");
    try {
      JSON.parse(body);
    } catch {
      return proxyError(400, "invalid_json", "The request body must be valid JSON.");
    }
  }

  const headers = new Headers({ accept: "application/json" });
  if (requiresJsonBody) headers.set("content-type", "application/json");
  const authorization = request.headers.get("authorization");
  const scopedGuestRequest = (method === "POST" && path.length === 3 && path[2] === "messages")
    || (method === "GET" && path.length === 4 && path[2] === "media");
  if (scopedGuestRequest && authorization?.startsWith("Bearer ")) {
    headers.set("authorization", authorization);
  }

  const target = buildUpstreamUrl(base, backendPath);
  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    if (binaryLimit !== undefined) {
      if (!upstream.ok) {
        const errorBytes = await readBoundedResponse(upstream, MAX_BODY_BYTES);
        if (!errorBytes) return proxyError(502, "invalid_api_response", "The guest API returned an invalid response.");
        return new Response(new TextDecoder().decode(errorBytes), {
          status: upstream.status,
          headers: { "content-type": upstream.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
        });
      }
      const contentType = (upstream.headers.get("content-type") ?? "").split(";", 1)[0].trim().toLowerCase();
      const limit = contentType === "image/png" ? MAX_IMAGE_BYTES
        : contentType === "video/mp4" ? MAX_VIDEO_BYTES
          : contentType === "text/vtt" ? MAX_CAPTIONS_BYTES : 0;
      const declaredLength = Number(upstream.headers.get("content-length") ?? 0);
      if (!limit || declaredLength > limit) {
        await upstream.body?.cancel();
        return proxyError(502, "invalid_media_response", "The media response is invalid.");
      }
      const bytes = await readBoundedResponse(upstream, limit);
      if (!bytes) {
        return proxyError(502, "media_response_too_large", "The media response exceeds its size limit.");
      }
      const exactBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
      return new Response(exactBuffer, { status: upstream.status, headers: {
        "content-type": contentType,
        "content-length": String(bytes.byteLength),
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      } });
    }
    const responseBody = await upstream.text();
    return new Response(responseBody, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return proxyError(
      504,
      timedOut ? "api_proxy_timeout" : "api_proxy_unavailable",
      timedOut ? "The guest API did not respond in time." : "The guest API is unavailable.",
      true,
    );
  }
}

export const GET = forward;
export const POST = forward;
