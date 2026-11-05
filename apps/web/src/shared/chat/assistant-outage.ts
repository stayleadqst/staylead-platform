const OUTAGE_CODES = new Set([
  "api_proxy_timeout", "api_proxy_unavailable", "network_outcome_unknown",
  "provider_failure", "provider_rate_limited", "provider_timeout",
]);

const COPY = {
  en: {
    language: "en",
    message: "The assistant did not provide a complete answer. No external action was taken.",
    fallback: "This notice is shown in English because a reviewed version is not available in your language.",
  },
  vi: {
    language: "vi",
    message: "Trợ lý chưa đưa ra câu trả lời hoàn chỉnh. Hệ thống chưa thực hiện hành động bên ngoài.",
    fallback: "Thông báo này hiển thị bằng tiếng Anh vì chưa có bản dịch đã duyệt cho ngôn ngữ của bạn.",
  },
  fr: {
    language: "fr",
    message: "L’assistant n’a pas fourni de réponse complète. Aucune action externe n’a été effectuée.",
    fallback: "Ce message est affiché en anglais faute de version validée dans votre langue.",
  },
  zh: {
    language: "zh",
    message: "助手未能提供完整答复。系统未执行任何外部操作。",
    fallback: "由于没有经过审核的译文，此通知以英语显示。",
  },
  ja: {
    language: "ja",
    message: "アシスタントは完全な回答を提供できませんでした。外部への操作は行われていません。",
    fallback: "確認済みの翻訳がないため、この通知は英語で表示されています。",
  },
  ar: {
    language: "ar",
    message: "لم يقدم المساعد إجابة كاملة. لم يتم تنفيذ أي إجراء خارجي.",
    fallback: "يظهر هذا الإشعار بالإنجليزية لعدم توفر ترجمة معتمدة بلغتك.",
  },
} as const;

export function assistantOutageCopy(languageTag: unknown) {
  let language: string | undefined;
  if (typeof languageTag === "string" && languageTag.trim() && languageTag.length <= 64) {
    try { language = Intl.getCanonicalLocales(languageTag.trim())[0]?.split("-")[0].toLowerCase(); }
    catch { language = undefined; }
  }
  const selected = language && language in COPY ? COPY[language as keyof typeof COPY] : COPY.en;
  return { ...selected, fallbackVisible: selected.language === "en" && language !== "en" };
}

export function isAssistantOutage(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const value = error as { code?: unknown; status?: unknown };
  return (typeof value.code === "string" && OUTAGE_CODES.has(value.code))
    || value.status === 502 || value.status === 503 || value.status === 504;
}
