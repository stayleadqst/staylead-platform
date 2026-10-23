import { NextResponse, type NextRequest } from "next/server";
import { buildUpstreamUrl } from "@/shared/api/proxy-url";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 8 * 1024;
// The API owns a 45-second whole-turn deadline; leave a small transport margin.
const UPSTREAM_TIMEOUT_MS = 50_000;
const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

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

async function forward(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const method = request.method.toUpperCase();
  let backendPath: string;
  let requiresJsonBody = false;

  if (method === "GET" && path.length === 1 && path[0] === "health") {
    backendPath = "/health";
  } else if (method === "POST" && path.length === 1 && path[0] === "sessions") {
    backendPath = "/v1/guest/sessions";
    requiresJsonBody = true;
  } else if (
    method === "POST" && path.length === 3 && path[0] === "sessions"
    && SESSION_ID_PATTERN.test(path[1]) && path[2] === "messages"
  ) {
    backendPath = `/v1/guest/sessions/${path[1]}/messages`;
    requiresJsonBody = true;
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
  if (method === "POST" && path.length === 3 && authorization?.startsWith("Bearer ")) {
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
