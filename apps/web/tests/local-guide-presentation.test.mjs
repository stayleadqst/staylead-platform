import assert from "node:assert/strict";
import test from "node:test";

import {
  formatLocalGuidePrice,
  localGuideSourceLine,
  localGuideVerificationText,
  visibleLocalGuideClaims,
} from "../src/domains/hospitality/registration/local-guide-presentation.ts";

test("nested source references render identity, lifecycle, generation, validity, and exact facts", () => {
  const line = localGuideSourceLine({
    source: {
      source_id: "S8-GUIDE-PRIMARY", source_version: "1.1", status: "approved",
      localized_status: "Approuvé", source_generation: 4, valid_from: "2026-10-01",
      valid_to: "2027-01-01", source_hash: "1234567890abcdef",
    },
    fact_ids: ["DIN-01-PRICE"],
  });
  assert.match(line, /S8-GUIDE-PRIMARY/);
  assert.match(line, /Approuvé/);
  assert.match(line, /generation 4/);
  assert.match(line, /through 2027-01-01/);
  assert.match(line, /DIN-01-PRICE/);
  assert.doesNotMatch(line, /status unknown|version unknown/);
});

test("localized unknown verification stays code-specific and stale results hide candidate cards", () => {
  assert.deepEqual(localGuideVerificationText({ localized_unknowns: ["Vérifiez les allergènes."] }, "Confirm"), ["Vérifiez les allergènes."]);
  assert.deepEqual(localGuideVerificationText({ unknown_codes: ["allergy_unconfirmed"] }, "Confirm"), ["Confirm"]);
  const cards = [{ id: "DIN-01" }];
  assert.deepEqual(visibleLocalGuideClaims(cards, false, false), cards);
  assert.deepEqual(visibleLocalGuideClaims(cards, true, false), []);
  assert.deepEqual(visibleLocalGuideClaims(cards, false, true), []);
});

test("prices show amount, currency, and per-person basis in the requested locale", () => {
  const rendered = formatLocalGuidePrice({ amount: 110000, currency: "VND", basis: "per_person" }, "fr-FR", "Unknown", "par personne");
  assert.match(rendered, /110/);
  assert.match(rendered, /VND/);
  assert.match(rendered, /par personne/);
  assert.equal(formatLocalGuidePrice({ amount: "110000", currency: "VND", basis: "per_person" }, "fr", "Inconnu", "par personne"), "Inconnu");
});
