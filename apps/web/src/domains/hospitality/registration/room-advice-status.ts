const STATUS_LABELS = {
  en: {
    needs_clarification: "I need one more detail before I can check the room fit.",
    infeasible: "No checked arrangement fits the confirmed requirements. You can adjust a requirement or ask the hotel.",
    unsupported: "I could not assess this request from the checked room records. Please confirm it with the hotel.",
    processing_limit: "This request is too complex to check in one pass. Try fewer guests or simpler room requirements.",
    conflict: "The checked room requirements or hotel rules do not fit together. Try adjusting a requirement or ask the hotel to confirm the applicable rule.",
    partial: "Some parts of this arrangement could not be confirmed. Review the checks below before deciding.",
  },
  vi: {
    needs_clarification: "Tôi cần thêm một chi tiết để kiểm tra mức độ phù hợp của phòng.",
    infeasible: "Không có cách sắp xếp đã kiểm tra nào đáp ứng các yêu cầu đã xác nhận. Bạn có thể điều chỉnh yêu cầu hoặc hỏi khách sạn.",
    unsupported: "Tôi không thể đánh giá yêu cầu này từ hồ sơ phòng đã kiểm tra. Vui lòng xác nhận với khách sạn.",
    processing_limit: "Yêu cầu này quá phức tạp để kiểm tra một lần. Hãy thử giảm số khách hoặc đơn giản hóa yêu cầu phòng.",
    conflict: "Các yêu cầu phòng đã kiểm tra hoặc quy định khách sạn chưa thể khớp với nhau. Hãy điều chỉnh một yêu cầu hoặc hỏi khách sạn xác nhận quy định áp dụng.",
    partial: "Chưa thể xác nhận một số phần của phương án. Hãy xem các mục kiểm tra bên dưới.",
  },
  zh: {
    needs_clarification: "在核验客房是否合适前，我还需要一项信息。",
    infeasible: "没有已核验的安排符合已确认的要求。您可以调整要求或联系酒店。",
    unsupported: "根据已核验的客房记录，我无法评估此请求。请向酒店确认。",
    processing_limit: "此请求过于复杂，无法一次核验。请减少人数或简化客房要求。",
    conflict: "已核验的客房要求或酒店规则无法同时满足。请调整一项要求，或联系酒店确认适用规则。",
    partial: "此安排的部分内容尚未核验。决定前请查看下方检查项。",
  },
  ja: {
    needs_clarification: "客室の適合性を確認するため、もう一つ情報が必要です。",
    infeasible: "確認済みの条件に合う配置はありません。条件を調整するか、ホテルにお問い合わせください。",
    unsupported: "確認済みの客室記録からこのリクエストを評価できません。ホテルにご確認ください。",
    processing_limit: "このリクエストは複雑すぎて一度に確認できません。人数を減らすか条件を簡潔にしてください。",
    conflict: "確認済みの客室条件またはホテル規則を両立できません。条件を調整するか、適用される規則をホテルにご確認ください。",
    partial: "一部の条件を確認できませんでした。決定前に以下の確認事項をご覧ください。",
  },
} as const;

export function roomAdviceStatusLabel(status: string, languageTag: string): string {
  const language = languageTag.split(/[-_]/, 1)[0].toLowerCase() as keyof typeof STATUS_LABELS;
  const labels = STATUS_LABELS[language] ?? STATUS_LABELS.en;
  return labels[status as keyof typeof labels] ?? labels.unsupported;
}
