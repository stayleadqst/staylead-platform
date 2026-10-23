import type { DomainRegistration } from "@/composition/domain_registry";
import { HospitalityLanding } from "@/domains/hospitality/landing/HospitalityLanding";

function HospitalityAnswerRenderer({ answer }: { answer: string }) {
  return <p className="guest-answer-text">{answer}</p>;
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
  themeClass: "theme-hospitality",
  content: {
    brand: "StayLead · Hospitality",
    syntheticDisclosure: "Demo experience using synthetic hotel information.",
    demoHotelSlugs: ["harbor-city-demo", "lagoon-family-demo", "pine-ridge-demo"],
  },
};
