# Synthetic hospitality knowledge pack v1

This is an author-authored synthetic data pack for QA and future importer work. It does not describe real hotels, bookings, services, or live operating conditions. `approved: true` means the synthetic record is eligible for guest-visible fixture testing; it does not claim that a real hotel approved it.

The pack contains three isolated fictional properties: `HTL-CITY01` Harbor City Demo (business city), `HTL-BEACH02` Lagoon Family Demo (family beach), and `HTL-RETREAT03` Pine Ridge Demo (quiet mountain retreat). All dates, addresses, places, prices, capacities, and policies are fictional. Reference date is 2026-10-22; active records are valid from 2026-10-01 through 2027-09-30. Time is `Asia/Ho_Chi_Minh`; all monetary amounts are VND whole dong.

## Files and schema

- `facts.json` is the active atomic fact corpus. Each fact has a stable fact ID, one hotel ID, topic/subject/field, typed value, conditions, evidence status (`confirmed`, `unknown`, or `needs_confirmation`), source references, visibility, synthetic-publication eligibility, version, and validity interval.
- `sources.json` describes hotel-specific authored sources, audience scope, version, validity, and the readable source path. `sources/guest/` never contains internal-only notes; `sources/internal/` is separate. `sources/catalog/` is the source document for the structured room, rate, venue, and route catalogs.
- `properties.json` contains fictional property metadata plus room types, rates, eight venues (food/drink and local visits), four service providers, and 19 authored route legs per property. Each venue has separate hotel-to-venue and venue-to-hotel legs, alongside airport directions and an explicit cross-leg. Each catalog entry carries a source reference and validity dates. Room occupancy, child ages, guardian thresholds, bed positions, cot/extra-bed charges and unknowns are machine-readable. Rates are explicitly reference-only, with a nightly room basis, included occupants, tax assumption, child/adult/extra-bed charge status, and no claim of quote or live availability. Venue costs use typed VND amounts and per-person/meal/order/visit/item bases; unknown values are null, and explicit zero means free admission/access only. All price examples are synthetic and must not be used as real quotes. Consumers must not synthesize reverse routes.
- `lifecycle_scenarios.json` is a separate test-only set of expired, deleted, revoked, conflicting, injected, internal, and unknown records. These records are not in the active approved corpus.
- `media/` is authored independently. Its source IDs are independent of this text/catalog corpus and its assets illustrate appearances only; they do not establish room capacity, price, policy, access, or availability. Expected paths are `media/hotels/HTL-ID/`.
- `manifest.json` gives per-property coverage and pack counts. `generate_knowledge.py` regenerates the authored JSON and readable `.txt` sources. `validate_knowledge.py` checks isolation, citations, visibility, typed rate/room data, coverage, and lifecycle separation.

## Coverage map

| Area | Included topics |
| --- | --- |
| Property and stay | identity, location, check-in/out, early/late requests, luggage, reception, booking changes, cancellation, deposits, payments, invoice requests |
| Rooms and guests | room types, beds, occupancy, child and guardian ages, sharing, cots, extra-bed unknowns, accessibility limits |
| Food and facilities | meals, dietary requests, allergy limitations, Wi-Fi, pool, spa, gym, laundry, workspaces, venue hours and capacity references |
| Practical policies | parking, pets, smoking, quiet hours/noise, transport providers, route legs, luggage/seats/child-seat/access notes, fictional local guide |
| Support and trust | safety escalation without invented emergency numbers or medical advice, key access, privacy, lost and found, housekeeping, maintenance, complaints, language, contact paths, outages, weather, and unavailable services |
| Data handling | internal-only operational records, unknowns, source/version validity, hotel isolation, and isolated lifecycle/red-team cases |

## Explicitly unknown or live-only information

The fixture does not claim live room/venue/vehicle availability, current weather or trail/beach safety, same-day outages, live transport quotes, refund posting times, many child/extra-bed charges, room-specific accessibility suitability, parking clearance, or real-time provider acceptance. `null`, `unknown`, and `needs_confirmation` mean the value must stay unresolved until confirmed through the named synthetic contact workflow. The examples do not invent phone numbers, emergency services, medical instructions, or working contact endpoints.

The fictional hotels deliberately differ on pet, pool, meal, child, transport, age-suitability, and quiet-use policies. A response must be grounded in the named hotel's records. Unknown or unconfirmed values must remain unknown; they are not permission to infer.

## Safe importer boundary

`facts.json` contains guest, internal-only, unknown, and needs-confirmation records. Its manifest counts are corpus totals, not guest-publishable counts. An importer must filter by the requested `hotel_id`, source `guest_approved`, fact `approved` and `visibility`, validity interval, and allowed status before indexing guest knowledge. Never index the full file as guest-facing content or expose internal facts. Here, `approved: true` only means eligible within this synthetic QA fixture.

Every `https://*.example.invalid/` URL is a clearly labelled NONFUNCTIONAL sample. The pack contains no real phone number, emergency number, secret, or personal data. It is not a production knowledge source and must not be used for live guest support.

## Regenerate and validate

From this directory:

```sh
python3 generate_knowledge.py
python3 validate_knowledge.py
```
