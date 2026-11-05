import assert from "node:assert/strict";
import test from "node:test";

import {
  formatLocalGuidePrice,
  formatTransportPrice,
  approvedSyntheticTransportUrl,
  localGuideSourceLine,
  localGuideVerificationText,
  transportCheckLabel,
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

test("flat transport provenance keeps source identity and fact IDs visible", () => {
  const line = localGuideSourceLine({
    source_id: "TRANSPORT-SOURCE-1", source_version: "1", source_hash: "a".repeat(64),
    source_generation: 3, section: "Transport", fact_id: "VEHICLE-1-SEATS", status: "confirmed",
  });
  assert.match(line, /TRANSPORT-SOURCE-1/);
  assert.match(line, /generation 3/);
  assert.match(line, /VEHICLE-1-SEATS/);
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

test("transport totals preserve null and use only the server-provided one-way basis", () => {
  assert.equal(formatTransportPrice({ amount: 28000, total_amount: 140000, currency: "VND", basis: "per_person_one_way", status: "known" }, "en"), "140,000 VND · total, one way");
  assert.equal(formatTransportPrice({ amount: 28000, total_amount: null, currency: "VND", basis: "per_person_one_way", status: "known" }, "en"), "28,000 VND · per person, one way");
  assert.equal(formatTransportPrice({ amount: null, total_amount: null, currency: null, basis: null, status: "unknown" }, "en"), "Price unknown or not comparable");
  assert.equal(formatTransportPrice({ amount: 28, total_amount: null, currency: "VND", basis: "per_vehicle_one_way", status: "known" }, "en"), "28 VND · per vehicle, one way");
});

test("transport contact accepts exact official service pages and scoped synthetic HTTPS example.com paths", () => {
  assert.equal(approvedSyntheticTransportUrl("https://example.com/providers/van"), "https://example.com/providers/van");
  assert.equal(approvedSyntheticTransportUrl("https://www.grab.com/vn/transport/car/"), "https://www.grab.com/vn/transport/car/");
  assert.equal(approvedSyntheticTransportUrl("https://www.greensm.com/vn-vi/greensm-car"), "https://www.greensm.com/vn-vi/greensm-car");
  for (const value of ["http://example.com/providers/van", "https://example.com.evil.test/providers/van",
    "https://example.com/", "https://example.com/providers/van?email=guest", "https://user@example.com/provider",
    "https://www.grab.com/vn/transport/car/?guest=1", "https://evil.example/www.grab.com/vn/transport/car/",
    "https://www.greensm.com.evil.test/vn-vi/greensm-car", null]) {
    assert.equal(approvedSyntheticTransportUrl(value), null);
  }
});

test("transport check unknowns stay explicit and never imply fit", () => {
  assert.equal(transportCheckLabel("unknown"), "Could not confirm");
  assert.equal(transportCheckLabel("not_fit"), "Does not fit the supplied requirement");
  assert.equal(transportCheckLabel("not_required"), "No requirement supplied");
});
