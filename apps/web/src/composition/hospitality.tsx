import { resolveConfiguredTarget, resolveDomainRegistration } from "@/composition/registration";
import { hospitalityRegistration, hospitalityTarget } from "@/domains/hospitality/registration";

export { hospitalityRegistration, hospitalityTarget };

/** Composition root for the only domain profile scaffolded in this repository. */
export function HospitalitySkeleton() {
  const target = resolveConfiguredTarget();
  const registration = resolveDomainRegistration(target);
  const Landing = registration.landing;
  return <Landing />;
}
