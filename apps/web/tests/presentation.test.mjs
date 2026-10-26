import test from "node:test";
import assert from "node:assert/strict";
import {
  clearLabelCacheForTests,
  copyPlainText,
  directionForLanguageTag,
  labelsForLanguage,
  normalizeLanguageTag,
  validateLabelBundle,
} from "../src/shared/chat/presentation.ts";

test("normalizes open language tags and follows explicit script direction before language defaults", () => {
  assert.equal(normalizeLanguageTag(" zh-hant "), "zh-Hant");
  assert.equal(normalizeLanguageTag("x-invalid-tag"), undefined);
  assert.equal(directionForLanguageTag("ar-EG"), "rtl");
  assert.equal(directionForLanguageTag("az-Arab"), "rtl");
  assert.equal(directionForLanguageTag("az-Hebr"), "rtl");
  assert.equal(directionForLanguageTag("en-Hebr"), "rtl");
  assert.equal(directionForLanguageTag("az-Latn"), "ltr");
  assert.equal(directionForLanguageTag("ar-Latn"), "ltr");
  assert.equal(directionForLanguageTag("hi-IN"), "ltr");
});

test("label bundles reject unsafe or unknown values atomically and preserve last good locale", () => {
  clearLabelCacheForTests();
  assert.deepEqual(validateLabelBundle({ send: "发送", copy: "复制" }), { send: "发送", copy: "复制" });
  labelsForLanguage("zh", { send: "发送", copy: "复制" });
  labelsForLanguage("zh", { send: "Envoyer", copy: "https://bad.example" });
  assert.equal(labelsForLanguage("zh").send, "发送");
  assert.equal(labelsForLanguage("zh").copy, "复制");
  assert.equal(labelsForLanguage("ar").send, "Send");
  assert.equal(validateLabelBundle({ send: "<b>Send</b>" }), undefined);
  assert.equal(validateLabelBundle({ surprise: "Send" }), undefined);
});

test("clipboard copy uses exact text and reports selection fallback outcomes", async () => {
  const copied = [];
  assert.equal(await copyPlainText("旅馆 １２３ https://example.test", {
    writeText: async (value) => copied.push(value),
  }, () => false), "copied");
  assert.deepEqual(copied, ["旅馆 １２３ https://example.test"]);
  assert.equal(await copyPlainText("answer", { writeText: async () => { throw new Error("denied"); } }, () => true), "selection_fallback");
  assert.equal(await copyPlainText("answer", undefined, () => false), "unsupported");
});
