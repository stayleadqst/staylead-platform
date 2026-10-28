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
    status, headers: { "cache-control": "no-store" },
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
  if (path.length !== 4 || path[0] !== "properties" || !PROPERTY_ID.test(path[1]) || path[2] !== "guide"
    || !["preview", "import", "activate", "refresh", "delete", "revoke"].includes(path[3])) {
    return error(404, "operator_route_not_found", "This operator API route is not available.");
  }
  const action = path[3];
  const expectedMethod = action === "preview" ? "GET" : "POST";
  if (method !== expectedMethod) return error(405, "method_not_allowed", "This operator action does not support that method.");

  const base = backendBase();
  if (!base) return error(503, "api_target_unavailable", "The operator API target is not configured.");
  let body: string | undefined;
  if (method === "POST") {
    if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json"))
      return error(415, "unsupported_media_type", "A JSON request body is required.");
    body = await bodyText(request);
    if (body === undefined) return error(413, "request_too_large", "The operator request is too large.");
    try { JSON.parse(body); } catch { return error(400, "invalid_json", "The operator request must be valid JSON."); }
  }
  const headers = new Headers({ accept: "application/json" });
  if (method === "POST") headers.set("content-type", "application/json");
  const authorization = request.headers.get("authorization");
  if (authorization?.startsWith("Bearer ")) headers.set("authorization", authorization);
  try {
    const upstream = await fetch(buildUpstreamUrl(base, `/v1/operator/properties/${path[1]}/guide/${action}`), {
      method, headers, body, cache: "no-store", signal: AbortSignal.timeout(15_000),
    });
    const bytes = await readBody(upstream.body, MAX_RESPONSE_BYTES);
    if (!bytes) return error(502, "invalid_api_response", "The operator API response is too large.");
    return new Response(Buffer.from(bytes), { status: upstream.status, headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store", "x-content-type-options": "nosniff",
    } });
  } catch {
    return error(503, "api_unavailable", "The operator API is unavailable.");
  }
}

export const GET = forward;
export const POST = forward;
