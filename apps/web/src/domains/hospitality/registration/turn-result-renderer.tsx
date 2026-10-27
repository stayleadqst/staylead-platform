"use client";

import type { GuestTurnResultRendererProps } from "@/composition/domain_registry";
import { safeBookingDestination } from "@/domains/hospitality/registration/booking-channel";
import { roomAdviceCostView } from "@/domains/hospitality/registration/room-advice-cost";
import { roomAdviceStatusLabel } from "@/domains/hospitality/registration/room-advice-status";
import { directionForLanguageTag, normalizeLanguageTag } from "@/shared/chat/presentation";

type BookingChannelData = {
  destination_url: string | null;
  contact: string | null;
  destination_kind: "synthetic_demo" | "configured";
};
type RoomAdvice = {
  result_id: string; result_version: number; currentness: "current" | "stale";
  status: string; availability: "unknown"; selection: { result_id: string; option_id: string } | null;
  source_refs: Record<string, unknown>[];
  options: Array<{
    option_id: string; rooms: Array<{ room_index: number; room_type_id: string }>;
    assignments: Array<{ member_id: string; room_index: number; bed_type: string | null }>;
    checks: Array<{ code: string; status: string }>;
    rationale: Array<{ claim_code: string; text: string; locale: string; locale_fallback: boolean }>;
    cost: { currency: string | null; nightly_subtotal: number | null; total: number | null; status: string;
      breakdown: Array<{ label: string; amount: number | null; currency: string | null; basis: string }> };
  }>;
  questions: Array<{ field: string; reason: string; locale: string; locale_fallback: boolean }>;
};

const LABELS = {
  en: {
    bookingTitle: "Continue to booking", bookingOpen: "Open the configured booking channel",
    bookingContact: "Configured hotel contact", bookingMissing: "No booking link or contact is configured for this hotel yet.",
    bookingDemo: "Demonstration link only; it does not open a real booking site.",
    bookingNext: "Check price, availability, and terms on the destination site. Opening this link does not reserve a room or make a payment.",
    bookingRequested: "You asked how to continue with booking. Use this hotel-configured channel.",
    roomOptions: "Room suggestions", roomOption: "Option", roomSelect: "Choose this option", roomSelected: "Selected option",
    roomStale: "This suggestion is out of date. Ask again for an updated recommendation.",
    roomFreshnessError: "Could not verify this suggestion is still current. Refresh it before choosing.",
    availabilityUnknown: "Live availability is unknown. Confirm it with the hotel.",
    noOptions: "No checked room option is available from the current information.",
    cost: "Reference cost", costIncomplete: "The total is incomplete because some charges are unknown.",
    nightlyReference: "Reference base per night", stayTotalUnknown: "This is not a stay total; dates or additional charges may be unknown.",
    fallback: "Shown in English because a reviewed phrase is not available in your language.",
    guest: "guest", guests: "guests", records: "Hotel records used", unknownCheck: "Could not confirm this check",
    selectionFailed: "This option could not be selected. Refresh the suggestion and try again.",
  },
  vi: {
    bookingTitle: "Tiếp tục đặt phòng", bookingOpen: "Mở kênh đặt phòng do khách sạn cấu hình",
    bookingContact: "Liên hệ khách sạn đã cấu hình", bookingMissing: "Khách sạn chưa cấu hình liên kết hoặc thông tin liên hệ đặt phòng.",
    bookingDemo: "Chỉ là liên kết minh họa; không mở trang đặt phòng thật.",
    bookingNext: "Hãy kiểm tra giá, tình trạng phòng và điều khoản trên trang đích. Mở liên kết không giữ phòng hoặc thanh toán.",
    bookingRequested: "Bạn muốn biết cách tiếp tục đặt phòng. Hãy dùng kênh do khách sạn cấu hình.",
    roomOptions: "Gợi ý phòng", roomOption: "Phương án", roomSelect: "Chọn phương án này", roomSelected: "Đã chọn phương án",
    roomStale: "Gợi ý này đã cũ. Hãy hỏi lại để nhận đề xuất mới.", availabilityUnknown: "Chưa biết tình trạng phòng trực tiếp. Hãy xác nhận với khách sạn.",
    roomFreshnessError: "Chưa thể xác minh gợi ý này còn mới hay không. Hãy tải lại trước khi chọn.",
    noOptions: "Không có phương án phòng đã kiểm tra từ thông tin hiện có.", cost: "Chi phí tham khảo",
    costIncomplete: "Tổng chưa đầy đủ vì chưa biết một số khoản phí.", nightlyReference: "Mức cơ bản tham khảo mỗi đêm",
    stayTotalUnknown: "Đây không phải tổng tiền lưu trú; ngày ở hoặc các khoản phí bổ sung có thể chưa rõ.",
    fallback: "Nội dung hiển thị bằng tiếng Anh vì chưa có câu đã được duyệt bằng ngôn ngữ của bạn.",
    guest: "khách", guests: "khách", records: "Hồ sơ khách sạn đã dùng", unknownCheck: "Chưa thể xác nhận mục này",
    selectionFailed: "Không thể chọn phương án này. Hãy tải lại gợi ý rồi thử lại.",
  },
  zh: {
    bookingTitle: "继续预订", bookingOpen: "打开酒店配置的预订渠道", bookingContact: "酒店配置的联系方式",
    bookingMissing: "酒店尚未配置预订链接或联系方式。", bookingDemo: "仅为演示链接，不会打开真实预订网站。",
    bookingNext: "请在目标网站确认价格、房态和条款。打开链接不会预留客房或付款。", bookingRequested: "您询问了如何继续预订，请使用酒店配置的渠道。",
    roomOptions: "客房建议", roomOption: "方案", roomSelect: "选择此方案", roomSelected: "已选择方案",
    roomStale: "此建议已过期。请重新询问以获取最新建议。", availabilityUnknown: "实时房态未知，请向酒店确认。",
    roomFreshnessError: "无法确认此建议是否仍然有效。请刷新后再选择。",
    noOptions: "根据当前信息没有可确认的客房方案。", cost: "参考费用", costIncomplete: "部分费用未知，因此总额不完整。",
    nightlyReference: "每晚参考基础房价", stayTotalUnknown: "这不是整个住宿的总价；入住日期或额外费用可能尚未确定。",
    fallback: "由于没有可用的审核短语，以下内容以英语显示。", guest: "位客人", guests: "位客人",
    records: "使用的酒店记录", unknownCheck: "无法确认此项", selectionFailed: "无法选择此方案，请刷新建议后重试。",
  },
  ja: {
    bookingTitle: "予約に進む", bookingOpen: "ホテル設定の予約窓口を開く", bookingContact: "ホテル設定の連絡先",
    bookingMissing: "予約リンクまたは連絡先はまだ設定されていません。", bookingDemo: "デモ用リンクです。実際の予約サイトは開きません。",
    bookingNext: "リンク先で料金、空室状況、条件をご確認ください。リンクを開いても部屋の確保や支払いは行われません。",
    bookingRequested: "予約方法についてのお問い合わせです。ホテルが設定した窓口をご利用ください。",
    roomOptions: "客室の提案", roomOption: "候補", roomSelect: "この候補を選択", roomSelected: "選択済み",
    roomStale: "この提案は古くなっています。最新の提案を依頼してください。", availabilityUnknown: "現在の空室状況は不明です。ホテルにご確認ください。",
    roomFreshnessError: "この提案が最新か確認できません。選択する前に更新してください。",
    noOptions: "現在の情報から確認できる候補はありません。", cost: "参考料金", costIncomplete: "不明な料金があるため合計は未確定です。",
    nightlyReference: "1泊あたりの参考基本料金", stayTotalUnknown: "これは滞在全体の合計ではありません。日程または追加料金が未確定の場合があります。",
    fallback: "確認済みの表現がないため、英語で表示しています。", guest: "名", guests: "名", records: "使用したホテル記録",
    unknownCheck: "この項目は確認できません", selectionFailed: "選択できませんでした。提案を更新して再度お試しください。",
  },
} as const;

const UNKNOWN_CHECK_LABELS = {
  en: {
    occupancy: "Room occupancy capacity is not confirmed.", bed_configuration: "The bed configuration is not confirmed.",
    bed_sharing_consent: "Guest consent for bed sharing is not confirmed.", bed_sharing_preference: "The bed-sharing preference is not confirmed.",
    child_age_policy: "The child age rule is not confirmed.", guardian_relationship: "The required guardian relationship is not confirmed.",
    bunk_position_policy: "The bunk position rule is not confirmed.", bunk_position_capacity: "Bunk position capacity is not confirmed.",
    accessibility: "Accessibility fit is not confirmed.", occupancy_policy: "The occupancy policy is not confirmed.",
    hard_budget: "The budget fit is not confirmed.", rate_basis: "The price basis is not confirmed.",
    rate_validity_window: "The rate validity dates are not confirmed.", charges_confirmation: "Some charges are not confirmed.",
  },
  vi: {
    occupancy: "Chưa xác nhận được sức chứa phòng.", bed_configuration: "Chưa xác nhận được cấu hình giường.",
    bed_sharing_consent: "Chưa xác nhận sự đồng ý dùng chung giường.", bed_sharing_preference: "Chưa xác nhận được yêu cầu dùng chung giường.",
    child_age_policy: "Chưa xác nhận được quy định độ tuổi trẻ em.", guardian_relationship: "Chưa xác nhận được yêu cầu về người giám hộ.",
    bunk_position_policy: "Chưa xác nhận được quy định vị trí giường tầng.", bunk_position_capacity: "Chưa xác nhận được sức chứa giường tầng.",
    accessibility: "Chưa xác nhận được mức độ phù hợp về khả năng tiếp cận.", occupancy_policy: "Chưa xác nhận được quy định sức chứa.",
    hard_budget: "Chưa xác nhận được mức độ phù hợp với ngân sách.", rate_basis: "Chưa xác nhận được cơ sở tính giá.",
    rate_validity_window: "Chưa xác nhận được thời hạn áp dụng giá.", charges_confirmation: "Chưa xác nhận được một số khoản phí.",
  },
  zh: {
    occupancy: "尚未确认客房可容纳人数。", bed_configuration: "尚未确认床铺配置。", bed_sharing_consent: "尚未确认客人是否同意共用床铺。",
    bed_sharing_preference: "尚未确认共床偏好。", child_age_policy: "尚未确认儿童年龄规则。", guardian_relationship: "尚未确认监护人关系要求。",
    bunk_position_policy: "尚未确认上下铺位置规则。", bunk_position_capacity: "尚未确认床位容量。", accessibility: "尚未确认无障碍适配情况。",
    occupancy_policy: "尚未确认入住人数规则。", hard_budget: "尚未确认是否符合预算。", rate_basis: "尚未确认价格计算方式。",
    rate_validity_window: "尚未确认价格有效日期。", charges_confirmation: "部分费用尚未确认。",
  },
  ja: {
    occupancy: "客室の定員は未確認です。", bed_configuration: "ベッド構成は未確認です。", bed_sharing_consent: "ベッド共有への同意は未確認です。",
    bed_sharing_preference: "ベッド共有の希望は未確認です。", child_age_policy: "子どもの年齢規則は未確認です。", guardian_relationship: "保護者との関係条件は未確認です。",
    bunk_position_policy: "二段ベッドの位置規則は未確認です。", bunk_position_capacity: "二段ベッドの定員は未確認です。", accessibility: "バリアフリー適合性は未確認です。",
    occupancy_policy: "宿泊人数規則は未確認です。", hard_budget: "予算への適合性は未確認です。", rate_basis: "料金の計算基準は未確認です。",
    rate_validity_window: "料金の有効期間は未確認です。", charges_confirmation: "一部の料金は未確認です。",
  },
} as const;

function labelsFor(tag: string) {
  const language = normalizeLanguageTag(tag)?.split("-")[0].toLowerCase();
  const selected = language && language in LABELS ? language as keyof typeof LABELS : "en";
  return {
    ...LABELS[selected],
    fallbackLocale: language !== "en" && !["vi", "zh", "ja"].includes(language ?? ""),
    unknownChecks: UNKNOWN_CHECK_LABELS[selected],
  };
}
function sameLanguage(left: string, right: string): boolean {
  return normalizeLanguageTag(left)?.split("-")[0].toLowerCase()
    === normalizeLanguageTag(right)?.split("-")[0].toLowerCase();
}
function amount(value: number, currency: string | null) {
  if (!currency) return String(value);
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value); }
  catch { return `${value} ${currency}`; }
}
function unknownCheckLabel(code: string, labels: ReturnType<typeof labelsFor>) {
  return labels.unknownChecks[code as keyof typeof labels.unknownChecks] ?? labels.unknownCheck;
}

function BookingChannel({ channel, languageTag, requested }: { channel?: BookingChannelData; languageTag: string; requested: boolean }) {
  const labels = labelsFor(languageTag);
  const destination = safeBookingDestination(channel?.destination_url);
  return <aside className="booking-channel" aria-label={labels.bookingTitle} lang={languageTag} dir={directionForLanguageTag(languageTag)}>
    <h2>{labels.bookingTitle}</h2>
    {requested && <p>{labels.bookingRequested}</p>}
    {destination ? <a href={destination} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{labels.bookingOpen}</a>
      : channel?.contact ? <p>{labels.bookingContact}: {channel.contact}</p> : <p>{labels.bookingMissing}</p>}
    {channel?.destination_kind === "synthetic_demo" && <p className="status-note" role="note">{labels.bookingDemo}</p>}
    <p className="status-note">{labels.bookingNext}</p>
    {labels.fallbackLocale && <p className="status-note" lang="en">{labels.fallback}</p>}
  </aside>;
}

export function HospitalityTurnResultRenderer(props: GuestTurnResultRendererProps) {
  const bookingChannel = props.bookingChannel as BookingChannelData | undefined;
  const response = props.response as { booking_request?: unknown; room_advice?: unknown } | null;
  const result = response?.room_advice as RoomAdvice | undefined;
  if (!response && !bookingChannel) return null;
  if (!result) return <BookingChannel channel={bookingChannel} languageTag={props.languageTag} requested={Boolean(response?.booking_request)} />;
  const labels = labelsFor(props.languageTag);
  const stale = result.currentness !== "current" || props.stale || props.freshnessError;
  return <>
    {Boolean(response?.booking_request) && <BookingChannel channel={bookingChannel} languageTag={props.languageTag} requested />}
    <section className="room-advice" data-testid="room-advice" data-room-advice="true"
      lang={props.languageTag} dir={directionForLanguageTag(props.languageTag)} aria-label={labels.roomOptions}>
      <h2>{labels.roomOptions}</h2>
      <p className="status-note">{labels.availabilityUnknown}</p>
      {result.status !== "ready" && <p className="status-note" role="status">
        {roomAdviceStatusLabel(result.status, props.languageTag)}
      </p>}
      {props.freshnessError
        ? <p className="status-note" role="status" data-testid="room-advice-freshness-error">{labels.roomFreshnessError}</p>
        : stale && <p className="status-note" role="status" data-testid="room-advice-stale">{labels.roomStale}</p>}
      {!result.options.length && <p>{labels.noOptions}</p>}
      {result.options.map((option, optionIndex) => {
        const assignments = new Map<number, typeof option.assignments>();
        for (const room of option.rooms) assignments.set(room.room_index, []);
        for (const assignment of option.assignments) assignments.set(assignment.room_index, [...(assignments.get(assignment.room_index) ?? []), assignment]);
        const selected = result.selection?.result_id === result.result_id && result.selection.option_id === option.option_id;
        const costView = roomAdviceCostView(option.cost);
        return <article className="room-option" data-testid="room-option" data-room-option-id={option.option_id} key={option.option_id}>
          <h3>{labels.roomOption} {optionIndex + 1}</h3>
          <ul className="room-layout">{option.rooms.map((room) => {
            const guests = assignments.get(room.room_index) ?? [];
            const bedSummary = [...new Set(guests.map((guest) => guest.bed_type).filter(Boolean))].join(", ");
            return <li key={room.room_index}><span>{room.room_type_id} · {guests.length} {guests.length === 1 ? labels.guest : labels.guests}</span>{bedSummary && <small>{bedSummary}</small>}</li>;
          })}</ul>
          {!!option.rationale.length && <ul className="room-rationale">{option.rationale.map((claim, index) => <li key={`${claim.claim_code}-${index}`}>
            <span lang={claim.locale}>{claim.text}</span>{(claim.locale_fallback || !sameLanguage(claim.locale, props.languageTag))
              && <small className="room-language-fallback" lang="en"> {labels.fallback}</small>}
          </li>)}</ul>}
          {!!option.checks.filter((check) => check.status === "unknown").length && <ul className="status-note" role="note">
            {option.checks.filter((check) => check.status === "unknown").map((check) => <li key={check.code}>{unknownCheckLabel(check.code, labels)}</li>)}
          </ul>}
          <div className="room-cost"><strong>{labels.cost}:</strong> {costView.confirmedStayTotal !== null
            ? amount(costView.confirmedStayTotal, option.cost.currency) : labels.costIncomplete}
            {costView.referenceNightlyBase !== null && <p>{labels.nightlyReference}: {amount(costView.referenceNightlyBase, option.cost.currency)} · {labels.stayTotalUnknown}</p>}
            {labels.fallbackLocale && <small className="room-language-fallback" lang="en"> {labels.fallback}</small>}
            <ul>{option.cost.breakdown.map((line, index) => <li key={`${line.label}-${index}`} lang="en">
              {line.label}: {line.amount === null ? labels.costIncomplete : amount(line.amount, line.currency)}{line.basis ? ` · ${line.basis}` : ""}
              {!sameLanguage("en", props.languageTag) && <small className="room-language-fallback"> {labels.fallback}</small>}
            </li>)}</ul>
          </div>
          <button className="text-button" type="button" data-testid="room-select" data-room-select={option.option_id}
            disabled={stale || props.selectionDisabled || Boolean(props.pendingOptionId)} onClick={() => props.onSelectOption(props.turnId ?? "", result, option.option_id)}>
            {selected ? labels.roomSelected : props.pendingOptionId === option.option_id ? "Sending…" : labels.roomSelect}
          </button>
        </article>;
      })}
      {!!result.questions.length && <div className="room-questions"><ul>{result.questions.map((question, index) => <li key={`${question.field}-${index}`}>
        <span lang={question.locale}>{question.reason}</span>{(question.locale_fallback || !sameLanguage(question.locale, props.languageTag))
          && <small className="room-language-fallback" lang="en"> {labels.fallback}</small>}
      </li>)}</ul></div>}
      {!!result.source_refs.length && <details className="evidence-list"><summary>{labels.records} ({result.source_refs.length})</summary><ul>
        {result.source_refs.map((raw, index) => {
          const source = raw.source && typeof raw.source === "object" ? raw.source as Record<string, unknown> : raw;
          const factIds = Array.isArray(raw.fact_ids) ? raw.fact_ids : raw.fact_id ? [raw.fact_id] : [];
          return <li key={`${String(factIds[0] ?? index)}-${index}`}>Record {String(factIds[0] ?? "hotel source")} · source {String(source.source_id ?? "unknown")}
            {typeof source.source_version === "string" ? ` · version ${source.source_version}` : ""}</li>;
        })}
      </ul></details>}
      {props.selectionError && <p role="alert">{labels.selectionFailed}</p>}
      {labels.fallbackLocale && <p className="room-language-fallback" lang="en">{labels.fallback}</p>}
    </section>
  </>;
}
