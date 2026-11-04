# Sprint 15 — D02 technical acceptance

Story: [D02 #47](https://github.com/stayleadqst/staylead-platform/issues/47). Sprint: [#114](https://github.com/stayleadqst/staylead-platform/issues/114). Target: `sprint-5-canonical-brief`. Local technical acceptance precedes publication; actual PR/merge and Sprint Review/Retro outcomes are recorded on #114.

## Candidate and authority

Product fingerprint `a2de725ab376220105c79b4df2011e7850e82a8b9c8c65c6be2ea87f61b70492`, 315 source/config/data/test pins. Independent Q found zero mismatches. Corrected local harness pin SHA-256 `78879a980eb4f605a8dbd6ad70ead3b05d4f0c976639fe1e0290a2b00edb04b3`; two harness Python files remain pinned. Canonical base `99a6036924d7d3d777ca83c42591079c8d5d4414`, tree `33ea07e92a10a6da30af30dbc8485fe65ea29552`. Divergent local history is never pushed; publication uses a canonical parent.

Hieu authorized the sprint and two explicit extensions. Final reserved totals: product **8/8**, backend harness **10/10**, browser harness **9/9**. The last extension adds only one shared harness batch, no product round. Historical failures, unreserved retry deviation and inherited publication failures 3 are retained; no reset or retrospective approval.

## Research and representative model

Research preceded solution, representative fixtures and planning. The existing synthetic hotel is in TP.HCM. The new representative pack distinguishes GrabCar and Green SM Car as app-based urban car services; all four directional legs and durations are explicitly demo data. Vehicle capacity excluding the driver, luggage, child-seat quantity, accessibility, trip price and availability remain unknown where the reviewed public sources do not establish them. Walking does not carry vehicle seats or vehicle prices. The original S13 pack remains labelled boundary evidence, not market validity.

Sources accessed 04/11/2026: [Grab service table, updated 08/07/2026](https://www.grab.com/vn/blog/bang-thong-tin-cac-dich-vu-tren-ung-dung-grab/), [GrabCar](https://www.grab.com/vn/transport/car/), [Green SM Car](https://www.greensm.com/vn-vi/greensm-car). The newer Grab table's 4/6-seat labels are not converted into confirmed passenger capacity. App quotes and service-specific fees are not replaced with invented scalar prices. [Decision Lab H1 2026](https://www.decisionlab.co/blog/similar-usage-different-preference-how-each-generation-chooses-vietnams-leading-digital-platforms) supports considering both widely used platforms, not suitability for a particular party.

Public research is not real hotel-approved M1 data. Source activation occurred only in a new private synthetic S15 database. No old revoked source was reapproved or reseeded.

## AC evidence

| AC | Expected and observed | Level and limits |
|---|---|---|
| AC1 | Four passenger seats excluding driver cannot fit five people in boundary tests. Missing, incomplete or pending party/child-seat need remains unknown; only explicit current zero or a complete current empty-child party justifies zero. Actual initial canonical party was adults null / children empty, and rendered capacity and child-seat checks remained unknown. | Current focused tests plus actual B-operated UI/API flow. Synthetic numeric boundaries are not facts about Grab or Green SM. |
| AC2 | Service-specific app/pickup trade-offs are sourced; missing price, licence, insurance, eligibility and current availability are not assured. Actual cards showed unconfirmed fit and unknown price/capacities. | Research, deterministic checks and actual desktop/mobile rendering. No app quote, field study, real vehicle availability or hotel acceptance. |
| AC3 | Normal quote confirmation committed taxi mode at version 1; luggage-only confirmation committed count 2 at version 2, preserving unknown party. Checks recomputed required luggage 2 while capacity/price/fit remained unknown. Exact official service-page URLs carry no query/PII or booking action. False capacity and unsupported assurances remain covered by current boundary/shared guard tests. | B-operated UI→API→M2/M5→UI, desktop and mobile 390×844; Q source/pin/test/research triangulation. Unchanged confirmation/version/replay/currentness guards reuse valid S14 evidence; no new bespoke UI replay or source-revoke claim. |

## Local checks and independent review

- Focused transport/invariants/local-guide parser: **25 passed**.
- Explicit configured Ruff on affected Python paths: **PASS**, using `--config apps/api/pyproject.toml --select E4,E7,E9,F,I`; compile: **PASS**.
- Web contracts: **58 passed**; lint, typecheck and configured production build: **PASS**.
- Full backend: **477 passed, 3 failed, 1 skipped**. The command remains failed. S3's stale contract/contact-hours expectation is the known exact baseline. The other two failures reproduce on canonical-equivalent untouched HEAD: the room-rate unit test is wall-clock expired, and the S7 harness overwrite test reaches a missing historical private receipt. Both tests and associated production files are byte-identical to HEAD. No expectation, prior receipt, production freshness guard or historical counter was changed.
- Q final verdict: `PASS_SCOPED_TECHNICAL_WITH_EXPLICIT_EVIDENCE_LIMITS`, no blocking product finding. Coordinator accepts AC1–3 within the existing technical scope. Runtime model/effort/token telemetry is unavailable.

The earlier Ruff command without the required API configuration remains **FAIL**; independent comparison proved the import block unchanged from S14. Other failed commands and both failed candidates are preserved.

## Evidence limits and handoff

Workspace evidence is retained under `validation/sprint-15-20261104/`, including authority/counters, candidates and source archives, A checks, B `consumer-evidence.json`, Q reviews and exact HEAD baseline reproduction. These are local artifacts, not claimed to be committed with this document.

`consumer-evidence.json` is a sanitized transcription of actual B-operated UI semantics, with reported read-only M2/M5 readbacks. Q independently inspected source/pins/tests/research; Q did not independently inspect screenshots or raw persisted response JSON. The attempted raw export is empty/invalid and excluded. Screenshots exist only in B's CUA tool transcript. No real model, real hotel/guest acceptance, RTL sample, deployment, booking or PII send is claimed.

One diagnostic tool output exposed temporary synthetic confirmation tokens; their values were not repeated, saved to artifacts or published. An unplanned pnpm reconciliation created a local untracked lockfile; it is preserved and excluded from this product publication. The 315 product pins remain unchanged. Five user-requested skill directories were copied locally and verified; they are outside the product candidate. The token-optimizer proxy was not enabled.

Supported output is a grounded comparison and safe official information links. A guest must independently obtain a trip quote and confirm their concrete capacity, luggage, child-seat, accessibility and availability requirements with the provider. No transaction is performed by StayLead.
