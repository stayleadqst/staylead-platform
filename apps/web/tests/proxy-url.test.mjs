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
