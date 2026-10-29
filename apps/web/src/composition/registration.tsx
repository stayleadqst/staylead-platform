import { hospitalityRegistration } from "@/domains/hospitality/registration";
import {
  DomainRegistrationError,
  resolveDomainRegistration as resolveRegisteredDomain,
  type DomainRegistration,
  type DomainTarget,
} from "@/composition/domain_registry";

export type { AnswerRendererProps, GuestBriefRendererProps, GuestBriefConfirmationChange, GuestBriefConfirmationLine, GuestTurnResultRendererProps, TurnResultActions, DomainRegistration, DomainTarget } from "@/composition/domain_registry";
export { DomainRegistrationError } from "@/composition/domain_registry";

export function resolveDomainRegistration(
  target: DomainTarget,
  registrations: readonly DomainRegistration[] = [hospitalityRegistration],
): DomainRegistration {
  return resolveRegisteredDomain(target, registrations);
}

export function resolveConfiguredTarget(
  registrations: readonly DomainRegistration[] = [hospitalityRegistration],
): DomainTarget {
  const domain = process.env.NEXT_PUBLIC_STAYLEAD_DOMAIN;
  const guestContractVersion = process.env.NEXT_PUBLIC_STAYLEAD_GUEST_CONTRACT_VERSION;
  if (!domain || !guestContractVersion) {
    throw new DomainRegistrationError("Public domain and guest contract configuration are required.");
  }
  const registration = registrations.find((candidate) => candidate.domain === domain);
  if (!registration) {
    throw new DomainRegistrationError(`Domain profile ${domain} is not registered.`);
  }
  const target: DomainTarget = {
    domain,
    guestContractVersion,
    apiBasePath: registration.apiBasePath,
  };
  resolveRegisteredDomain(target, registrations);
  return target;
}
