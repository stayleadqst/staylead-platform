export const LABEL_KEYS = [
  "send", "sending", "copy", "copied", "copy_failed", "retry_answer", "check_status",
  "brief", "stay", "nights", "adults", "children", "age", "unknown", "pending_age",
  "updated", "partial_success", "stale_answer", "ai_notice", "synthetic_notice",
] as const;

export type LabelKey = typeof LABEL_KEYS[number];
export type LabelBundle = Readonly<Partial<Record<LabelKey, string>>>;

export const ENGLISH_LABELS: Readonly<Record<LabelKey, string>> = {
  send: "Send",
  sending: "Sending…",
  copy: "Copy",
  copied: "Copied",
  copy_failed: "Copy failed. Select the answer and copy it manually.",
  retry_answer: "Retry answer",
  check_status: "Check whether this answer is current",
  brief: "Current trip details",
  stay: "Stay",
  nights: "nights",
  adults: "adults",
  children: "children",
  age: "age",
  unknown: "Could not confirm",
  pending_age: "age needed",
  updated: "The update was applied.",
  partial_success: "The update was applied, but the answer did not finish.",
  stale_answer: "This answer may no longer be current. Ask again for an updated answer.",
  ai_notice: "Ask this AI assistant about the hotel. It will show the records used and anything it could not confirm.",
  synthetic_notice: "Demo experience using synthetic hotel information.",
};

const labelCache = new Map<string, LabelBundle>();

export function normalizeLanguageTag(value: unknown): string | undefined {
  if (typeof value !== "string" || !value.trim() || value.length > 64) return undefined;
  try {
    return Intl.getCanonicalLocales(value.trim())[0];
  } catch {
    return undefined;
  }
}

export function directionForLanguageTag(value: unknown): "ltr" | "rtl" {
  const tag = normalizeLanguageTag(value);
  if (!tag) return "ltr";
  const language = tag.split("-")[0].toLowerCase();
  return ["ar", "he", "fa", "ur", "ps", "sd", "ug", "yi"].includes(language) ? "rtl" : "ltr";
}

function isPlainLabel(value: unknown): value is string {
  return typeof value === "string"
    && value.trim().length > 0
    && [...value].length <= 120
    && !/[<>\u0000-\u0008\u000B\u000C\u000E-\u001F]/u.test(value)
    && !/https?:\/\/|www\./iu.test(value)
    && !/[{}]/u.test(value);
}

/** Validate a complete response bundle before replacing the cached locale bundle. */
export function validateLabelBundle(value: unknown): LabelBundle | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length || entries.some(([key, label]) => !LABEL_KEYS.includes(key as LabelKey) || !isPlainLabel(label))) {
    return undefined;
  }
  return Object.freeze(Object.fromEntries(entries) as Partial<Record<LabelKey, string>>);
}

export function labelsForLanguage(languageTag: unknown, freshBundle?: unknown): Readonly<Record<LabelKey, string>> {
  const normalized = normalizeLanguageTag(languageTag);
  const validated = validateLabelBundle(freshBundle);
  if (normalized && validated) labelCache.set(normalized, validated);
  const cached = normalized ? labelCache.get(normalized) : undefined;
  return { ...ENGLISH_LABELS, ...cached };
}

export function hasCompleteLabelBundle(languageTag: unknown): boolean {
  const normalized = normalizeLanguageTag(languageTag);
  const cached = normalized ? labelCache.get(normalized) : undefined;
  return Boolean(cached && LABEL_KEYS.every((key) => typeof cached[key] === "string"));
}

export function clearLabelCacheForTests(): void {
  labelCache.clear();
}

export type CopyResult = "copied" | "failed" | "unsupported" | "selection_fallback";

export async function copyPlainText(
  text: string,
  clipboard: Pick<Clipboard, "writeText"> | undefined,
  selectFallback: () => boolean,
): Promise<CopyResult> {
  if (clipboard && typeof clipboard.writeText === "function") {
    try {
      await clipboard.writeText(text);
      return "copied";
    } catch {
      return selectFallback() ? "selection_fallback" : "failed";
    }
  }
  return selectFallback() ? "selection_fallback" : "unsupported";
}
