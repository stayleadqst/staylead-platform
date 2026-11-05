import { NextResponse, type NextRequest } from "next/server";
import { buildUpstreamUrl } from "@/shared/api/proxy-url";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 8 * 1024;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const PROPERTY_ID = /^HTL-[A-Z0-9-]{1,76}$/;
type RouteContext = { params: Promise<{ path: string[] }> };

function error(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, retryable: false } }, {
    status, headers: { "cache-control": "no-store", "referrer-policy": "no-referrer" },
  });
}

function backendBase(): URL | null {
  const raw = process.env.STAYLEAD_API_BASE_URL;
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if ((url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)))
      || url.username || url.password || url.search || url.hash) return null;
    return url;
  } catch { return null; }
}

async function bodyText(request: NextRequest): Promise<string | undefined> {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) { await reader.cancel(); return undefined; }
    chunks.push(value);
  }
  const merged = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { merged.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder().decode(merged);
}

async function readBody(body: ReadableStream<Uint8Array> | null, limit: number): Promise<Uint8Array | undefined> {
  if (!body) return new Uint8Array();
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) { await reader.cancel(); return undefined; }
    chunks.push(value);
  }
  const merged = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { merged.set(chunk, offset); offset += chunk.byteLength; }
  return merged;
}

async function forward(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const method = request.method.toUpperCase();
  let backendPath: string;
  let upstreamMethod = method;
  let body: string | undefined;
  let isLogin = false;
  let isCallback = false;
  if (path.length === 2 && path[0] === "auth" && path[1] === "login" && method === "GET") {
    backendPath = "/v1/operator/auth/login"; isLogin = true;
  } else if (path.length === 2 && path[0] === "auth" && path[1] === "callback" && method === "GET") {
    const values = request.nextUrl.searchParams;
    body = new URLSearchParams(["code", "state", "error"].flatMap((key) => values.has(key) ? [[key, values.get(key)!]] : [])).toString();
    if (body.length > 4096) return error(400, "invalid_callback", "The sign-in response is invalid.");
    backendPath = "/v1/operator/auth/callback"; upstreamMethod = "POST"; isCallback = true;
  } else if (path.length === 2 && path[0] === "auth" && path[1] === "session" && method === "GET") {
    backendPath = "/v1/operator/auth/session";
  } else if (path.length === 2 && path[0] === "auth" && path[1] === "logout" && method === "POST") {
    backendPath = "/v1/operator/auth/logout";
  } else if (path.length === 4 && path[0] === "properties" && PROPERTY_ID.test(path[1]) && path[2] === "guide"
    && ["preview", "import", "activate", "refresh", "delete", "revoke"].includes(path[3])) {
    const action = path[3];
    if (method !== (action === "preview" ? "GET" : "POST"))
      return error(405, "method_not_allowed", "This operator action does not support that method.");
    backendPath = `/v1/operator/properties/${path[1]}/guide/${action}`;
    if (method === "POST") {
      if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json"))
        return error(415, "unsupported_media_type", "A JSON request body is required.");
      body = await bodyText(request);
      if (body === undefined) return error(413, "request_too_large", "The operator request is too large.");
      try { JSON.parse(body); } catch { return error(400, "invalid_json", "The operator request must be valid JSON."); }
    }
  } else return error(404, "operator_route_not_found", "This operator API route is not available.");

  const base = backendBase();
  if (!base) return error(503, "api_target_unavailable", "The operator API target is not configured.");
  const headers = new Headers({ accept: "application/json" });
  if (upstreamMethod === "POST") headers.set("content-type", isCallback ? "application/x-www-form-urlencoded" : "application/json");
  const authorization = request.headers.get("authorization");
  if (authorization?.startsWith("Bearer ")) headers.set("authorization", authorization);
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const origin = request.headers.get("origin");
  if (origin) headers.set("origin", origin);
  try {
    const upstream = await fetch(buildUpstreamUrl(base, backendPath), {
      method: upstreamMethod, headers, body, cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(15_000),
    });
    if (upstream.status >= 300 && upstream.status < 400) {
      const location = upstream.headers.get("location");
      if (!location) return error(502, "invalid_redirect", "The sign-in redirect is unavailable.");
      let target: URL;
      try { target = new URL(location); } catch { return error(502, "invalid_redirect", "The sign-in redirect is unavailable."); }
      const expected = isLogin ? process.env.STAYLEAD_OIDC_AUTHORIZATION_ENDPOINT : process.env.STAYLEAD_OPERATOR_BROWSER_ORIGIN;
      if (!expected) return error(503, "operator_auth_unconfigured", "Operator sign-in is not configured.");
      const allowed = new URL(expected);
      if (target.origin !== allowed.origin || target.username || target.password || target.hash
        || (isLogin ? target.pathname !== allowed.pathname
          : target.pathname !== "/operator" || (target.search && target.search !== "?auth=error")))
        return error(502, "invalid_redirect", "The sign-in redirect is unavailable.");
      const redirect = NextResponse.redirect(target, upstream.status);
      redirect.headers.set("cache-control", "no-store");
      redirect.headers.set("referrer-policy", "no-referrer");
      for (const cookie of upstream.headers.getSetCookie()) redirect.headers.append("set-cookie", cookie);
      return redirect;
    }
    const bytes = await readBody(upstream.body, MAX_RESPONSE_BYTES);
    if (!bytes) return error(502, "invalid_api_response", "The operator API response is too large.");
    const responseBody = upstream.status === 204 || upstream.status === 304 ? null : Buffer.from(bytes);
    const response = new Response(responseBody, { status: upstream.status, headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
    } });
    for (const cookie of upstream.headers.getSetCookie()) response.headers.append("set-cookie", cookie);
    return response;
  } catch {
    return error(503, "api_unavailable", "The operator API is unavailable.");
  }
}

export const GET = forward;
export const POST = forward;
