import type { DomainRegistration, GuestBriefRendererProps } from "@/composition/domain_registry";
import { HospitalityLanding } from "@/domains/hospitality/landing/HospitalityLanding";
import { formatHospitalityBriefDelta } from "@/domains/hospitality/registration/brief-format";
import { HospitalityTurnResultRenderer } from "@/domains/hospitality/registration/turn-result-renderer";
import { ENGLISH_LABELS } from "@/shared/chat/presentation";
import { selectGuestRoomAdviceOption } from "@/shared/api/client";

type RoomAdviceIdentity = Readonly<{ result_id: string; result_version: number }>;
function roomAdviceIdentity(value: unknown): RoomAdviceIdentity | null {
  if (!value || typeof value !== "object") return null;
  const result = value as Record<string, unknown>;
  return typeof result.result_id === "string" && typeof result.result_version === "number"
    ? { result_id: result.result_id, result_version: result.result_version }
    : null;
}

function attachRoomSelection(response: unknown, result: unknown, selection: unknown): unknown {
  if (!response || typeof response !== "object") return response;
  const responseRecord = response as Record<string, unknown>;
  const current = responseRecord.room_advice;
  const resultIdentity = roomAdviceIdentity(result);
  const selectionRecord = selection && typeof selection === "object" ? selection as Record<string, unknown> : null;
  if (!current || typeof current !== "object" || !resultIdentity || !selectionRecord
    || selectionRecord.result_id !== resultIdentity.result_id
    || selectionRecord.result_version !== resultIdentity.result_version) return response;
  const currentRecord = current as Record<string, unknown>;
  if (currentRecord.result_id !== resultIdentity.result_id) return response;
  return { ...responseRecord, room_advice: { ...currentRecord, selection: selectionRecord } };
}

function HospitalityAnswerRenderer({ answer }: { answer: string }) {
  return <p className="guest-answer-text">{answer}</p>;
}

function HospitalityGuestBriefRenderer({ brief, receipt, delta, labels: suppliedLabels }: GuestBriefRendererProps) {
  const labels = { ...ENGLISH_LABELS, ...suppliedLabels };
  const snapshot = brief as {
    brief_version: number;
    dates: { check_in: string | null; check_out: string | null; nights: number | null };
    party: { adults: number | null; children: readonly { member_id: string; age: number | null }[] };
    pending_fields: readonly string[];
  };
  const dates = snapshot.dates;
  const party = snapshot.party;
  const children = party.children.map((child, index) => child.age === null
    ? `${labels.children} ${index + 1} (${labels.pending_age})`
    : `${labels.children} ${index + 1}, ${labels.age} ${child.age}`).join(", ");
  if (receipt) {
    const changes = (delta ?? (receipt as { applied_delta?: unknown }).applied_delta ?? {}) as Parameters<typeof formatHospitalityBriefDelta>[0];
    return <p className="brief-delta-text">{formatHospitalityBriefDelta(changes)}</p>;
  }
  const childIndex = new Map(party.children.map((child, index) => [child.member_id, index + 1]));
  const pendingLabels = snapshot.pending_fields.map((field) => {
    if (field === "dates.check_in") return "check-in date";
    if (field === "dates.check_out") return "check-out date";
    if (field === "party.adults") return `${labels.adults} count`;
    if (field === "party.children.member") return `${labels.children} to update`;
    const match = /^party\.children\.([^.]+)\.age$/.exec(field);
    if (match) return `${labels.age} of ${labels.children} ${childIndex.get(match[1]) ?? ""}`.trim();
    return "trip details";
  });
  return (
    <>
      <section className="brief-summary" aria-label="Current trip details">
        <h2>{labels.brief}</h2>
        <p>
          {dates.check_in || dates.check_out
            ? `${dates.check_in ?? "Check-in not set"} to ${dates.check_out ?? "check-out not set"}`
            : "Dates not set"}
            {dates.nights !== null ? ` · ${dates.nights} ${labels.nights}` : ""}
        </p>
        <p>
          {party.adults === null ? `${labels.adults} not set` : `${party.adults} ${labels.adults}`}
          {children ? ` · ${children}` : party.children.length === 0 ? ` · 0 ${labels.children}` : ""}
        </p>
        {!!pendingLabels.length && <p className="status-note">Still needed: {pendingLabels.join(", ")}</p>}
        <small>Trip details version {snapshot.brief_version}</small>
      </section>
    </>
  );
}

export const hospitalityTarget = {
  domain: "hospitality",
  guestContractVersion: "1",
  apiBasePath: "/api/guest",
} as const;

export const hospitalityRegistration: DomainRegistration = {
  ...hospitalityTarget,
  landing: HospitalityLanding,
  answerRenderer: HospitalityAnswerRenderer,
  guestBriefRenderer: HospitalityGuestBriefRenderer,
  turnResultRenderer: HospitalityTurnResultRenderer,
  turnResultActions: {
    selectOption: async ({ sessionId, accessToken, result, optionId, target }) => {
      const identity = roomAdviceIdentity(result);
      if (!identity) throw new Error("The selected option is unavailable.");
      return selectGuestRoomAdviceOption({
        sessionId, accessToken, resultId: identity.result_id, resultVersion: identity.result_version,
        optionId, target,
      });
    },
    attachSelection: attachRoomSelection,
  },
  themeClass: "theme-hospitality",
  content: {
    brand: "StayLead · Hospitality",
    syntheticDisclosure: "Demo experience using synthetic hotel information.",
    demoHotelSlugs: ["harbor-city-demo", "lagoon-family-demo", "pine-ridge-demo"],
  },
};
