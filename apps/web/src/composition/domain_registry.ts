import type { ComponentType } from "react";

export type DomainTarget = Readonly<{
  domain: string;
  guestContractVersion: string;
  apiBasePath: string;
}>;

export type AnswerRendererProps = Readonly<{ answer: string }>;

export type DomainRegistration = Readonly<{
  domain: string;
  guestContractVersion: string;
  apiBasePath: string;
  landing: ComponentType;
  answerRenderer: ComponentType<AnswerRendererProps>;
  themeClass: string;
  content: Readonly<{
    brand: string;
    syntheticDisclosure: string;
    demoHotelSlugs: readonly string[];
  }>;
}>;

export class DomainRegistrationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DomainRegistrationError";
  }
}

export function resolveDomainRegistration(
  target: DomainTarget,
  registrations: readonly DomainRegistration[],
): DomainRegistration {
  if (!target.domain || !target.guestContractVersion || !target.apiBasePath) {
    throw new DomainRegistrationError("Domain target configuration is incomplete.");
  }
  const registration = registrations.find((candidate) => candidate.domain === target.domain);
  if (!registration) {
    throw new DomainRegistrationError(`Domain profile ${target.domain} is not registered.`);
  }
  if (registration.guestContractVersion !== target.guestContractVersion) {
    throw new DomainRegistrationError(
      `Guest contract mismatch for domain ${target.domain}: expected ${registration.guestContractVersion}, received ${target.guestContractVersion}.`,
    );
  }
  if (registration.apiBasePath !== target.apiBasePath) {
    throw new DomainRegistrationError(`API binding mismatch for domain ${target.domain}.`);
  }
  return registration;
}
