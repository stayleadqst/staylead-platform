import type { DomainRegistration, GuestBriefRendererProps } from "@/composition/domain_registry";
import { HospitalityLanding } from "@/domains/hospitality/landing/HospitalityLanding";
import { formatHospitalityBriefDelta } from "@/domains/hospitality/registration/brief-format";

function HospitalityAnswerRenderer({ answer }: { answer: string }) {
  return <p className="guest-answer-text">{answer}</p>;
}

function HospitalityGuestBriefRenderer({ brief, receipt, delta }: GuestBriefRendererProps) {
  const snapshot = brief as {
    brief_version: number;
    dates: { check_in: string | null; check_out: string | null; nights: number | null };
    party: { adults: number | null; children: readonly { member_id: string; age: number | null }[] };
    pending_fields: readonly string[];
  };
  const dates = snapshot.dates;
  const party = snapshot.party;
  const children = party.children.map((child, index) => child.age === null
    ? `child ${index + 1} (age needed)`
    : `child ${index + 1}, age ${child.age}`).join(", ");
  if (receipt) {
    const changes = (delta ?? (receipt as { applied_delta?: unknown }).applied_delta ?? {}) as Parameters<typeof formatHospitalityBriefDelta>[0];
    return <p className="brief-delta-text">{formatHospitalityBriefDelta(changes)}</p>;
  }
  const childIndex = new Map(party.children.map((child, index) => [child.member_id, index + 1]));
  const pendingLabels = snapshot.pending_fields.map((field) => {
    if (field === "dates.check_in") return "check-in date";
    if (field === "dates.check_out") return "check-out date";
    if (field === "party.adults") return "number of adults";
    if (field === "party.children.member") return "which child to update";
    const match = /^party\.children\.([^.]+)\.age$/.exec(field);
    if (match) return `age of child ${childIndex.get(match[1]) ?? ""}`.trim();
    return "trip details";
  });
  return (
    <>
      <section className="brief-summary" aria-label="Current trip details">
        <h2>Current trip details</h2>
        <p>
          {dates.check_in || dates.check_out
            ? `${dates.check_in ?? "Check-in not set"} to ${dates.check_out ?? "check-out not set"}`
            : "Dates not set"}
          {dates.nights !== null ? ` · ${dates.nights} nights` : ""}
        </p>
        <p>
          {party.adults === null ? "Adults not set" : `${party.adults} ${party.adults === 1 ? "adult" : "adults"}`}
          {children ? ` · ${children}` : party.children.length === 0 ? " · no children recorded" : ""}
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
  themeClass: "theme-hospitality",
  content: {
    brand: "StayLead · Hospitality",
    syntheticDisclosure: "Demo experience using synthetic hotel information.",
    demoHotelSlugs: ["harbor-city-demo", "lagoon-family-demo", "pine-ridge-demo"],
  },
};
