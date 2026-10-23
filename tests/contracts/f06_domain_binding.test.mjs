import assert from "node:assert/strict";
import test from "node:test";

import {
  DomainRegistrationError,
  resolveDomainRegistration,
} from "../../apps/web/src/composition/domain_registry.ts";

const landingA = () => null;
const answerA = () => null;
const landingB = () => null;
const answerB = () => null;

const hospitality = {
  domain: "hospitality",
  guestContractVersion: "1",
  apiBasePath: "/api/guest",
  landing: landingA,
  answerRenderer: answerA,
  themeClass: "theme-hospitality",
  content: { brand: "Hospitality", syntheticDisclosure: "Synthetic", demoHotelSlugs: [] },
};

const alternate = {
  domain: "test-equipment",
  guestContractVersion: "3",
  apiBasePath: "/api/test-equipment",
  landing: landingB,
  answerRenderer: answerB,
  themeClass: "theme-test-equipment",
  content: { brand: "Test profile", syntheticDisclosure: "Test-only", demoHotelSlugs: [] },
};

test("a target selects its own landing, theme, content, renderer and API binding", () => {
  const selected = resolveDomainRegistration({
    domain: "test-equipment",
    guestContractVersion: "3",
    apiBasePath: "/api/test-equipment",
  }, [hospitality, alternate]);

  assert.equal(selected.landing, landingB);
  assert.equal(selected.answerRenderer, answerB);
  assert.equal(selected.themeClass, "theme-test-equipment");
  assert.equal(selected.content.brand, "Test profile");
  assert.equal(selected.apiBasePath, "/api/test-equipment");
});

test("unknown profiles and domain/contract/API mismatches fail without fallback", () => {
  assert.throws(() => resolveDomainRegistration({
    domain: "not-registered",
    guestContractVersion: "1",
    apiBasePath: "/api/guest",
  }, [hospitality]), DomainRegistrationError);

  assert.throws(() => resolveDomainRegistration({
    domain: "hospitality",
    guestContractVersion: "2",
    apiBasePath: "/api/guest",
  }, [hospitality]), /Guest contract mismatch/);

  assert.throws(() => resolveDomainRegistration({
    domain: "hospitality",
    guestContractVersion: "1",
    apiBasePath: "https://other.example/api",
  }, [hospitality]), /API binding mismatch/);
});
