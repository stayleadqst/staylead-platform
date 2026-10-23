import assert from "node:assert/strict";
import test from "node:test";

import { buildUpstreamUrl } from "../src/shared/api/proxy-url.ts";

test("root API base keeps the configured upstream host", () => {
  const target = buildUpstreamUrl(new URL("http://127.0.0.1:18083"), "/health");
  assert.equal(target.hostname, "127.0.0.1");
  assert.equal(target.port, "18083");
  assert.equal(target.pathname, "/health");
});

test("path-prefixed API base appends only the allowlisted backend path", () => {
  const target = buildUpstreamUrl(new URL("https://api.example.test/platform/v1/"), "/health");
  assert.equal(target.hostname, "api.example.test");
  assert.equal(target.pathname, "/platform/v1/health");
});

test("leading double slashes remain a path and cannot replace the configured host", () => {
  const target = buildUpstreamUrl(new URL("https://api.example.test//platform"), "/health");
  assert.equal(target.hostname, "api.example.test");
  assert.equal(target.pathname, "//platform/health");
});

test("upstream query parameters stay separate from the media path", () => {
  const target = buildUpstreamUrl(
    new URL("http://127.0.0.1:18083"),
    "/v1/guest/sessions/session/media/media-room?generation=1&source_id=SRC-ONE&source_version=2&source_hash=abc&sha256=def",
  );
  assert.equal(target.pathname, "/v1/guest/sessions/session/media/media-room");
  assert.equal(target.searchParams.get("generation"), "1");
  assert.equal(target.searchParams.get("source_id"), "SRC-ONE");
  assert.equal(target.searchParams.get("sha256"), "def");
});
