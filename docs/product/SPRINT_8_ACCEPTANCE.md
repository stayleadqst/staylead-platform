# Sprint 8 — reviewed candidate, actual guest acceptance pending

**Guide/operator technical scope is verified. Shortlist implementation and offline readiness pass independent review; Sprint 8 is not fully Done because the actual-model guest acceptance batch has not been authorized or run.** All data and approvals are synthetic technical-demo records, not real hotel approval. Nothing is deployed.

Owner branch `sprint-8-guide-shortlist` starts at accepted Sprint7 merge `12122f7d012c0617670438de5419efdc3d7729ab`; PR base remains `sprint-5-canonical-brief`. Publication/merge states are recorded on GitHub; this report alone does not assert a push or merge. Existing PRs83/89 and broader parents45/46 were not changed.

| Work | Owner/model/effort | Stage/candidate | Verification | Blocker/next action |
|---|---|---|---|---|
| #101 typed guide/protected operator | A+B / gpt-6-luna/high | Implemented, verified, independently reviewed | G1–G4 PASS in synthetic technical scope; actual operator browser/M1 lifecycle and zero-SQL denials | Publish evidence; no inference needed for this story |
| #102 grounded shortlist/M6 | A+B / gpt-6-luna/high | Implemented; offline verified/readiness reviewed | L1–L3 deterministic checks and fake-provider M2→M3→domain→UI/source bindings; actual-model L1–L4 unverified | New bounded actual acceptance authority |
| #100 coordination/acceptance | C / exact runtime model+effort unavailable | C1 complete; C2/C3 engineering/readiness complete, actual guest portion pending | Contracts/leases/oracles, integrated operator demo, seven Q findings repaired | Request exact4/8 proposal; no full SprintDone/merge yet |
| Independent review | Fresh Q / gpt-6.1-sol/high | PASS, zero open actionable engineering findings |273product/4control hashes; scoped probes, native Ajv and Chromium DOM; actual model unverified | Observe authorized actual batch when approved |

Product fingerprint **`f4af97b878f78986015a5203edb5ff33c103732897b2eb226dd0aaf6bec53182`**,273files: [manifest](evidence/sprint-8/candidate-manifest.json). Controls fingerprint **`66c7f6d466d5e8edacf6673a8ee5d700be093229f745a5685dd94ddd46df8a24`**,4files: [controls](evidence/sprint-8/acceptance-controls-manifest.json). Documentation/evidence are outside the product fingerprint. [Independent report](evidence/sprint-8/independent-review.json), [independent oracle](evidence/sprint-8/independent-oracle.json), [execution/leases](../execution/SPRINT_8_EXECUTION.md).

## AC evidence

| AC | Expected → observed |
|---|---|
| G1 / A05-AC1 | Six typed venue records with stable IDs/location/timezone/hours/closure/duration/price basis/currency/sponsor and source/checked/expiry; staged protected preview preserves unknown/conflict/expired records and synthetic labels. Parser/domain tests, independent raw-fixture oracle and actual operator preview PASS. |
| G2 / A05-AC2 | Two providers with seats excluding driver, bounded luggage/child-seat/access/availability unknowns; four directional source-backed legs. No reverse route, unlimited capacity or availability inference. Independent oracle/provider/route checks PASS. |
| G3 / A05-AC3 | Import staged→zero guest facts; activate→current guest facts; refresh100000→110000; second-source refresh resolves hours conflict; revoke/delete remove eligibility; old request409stale_source and no extra provider calls. Real PostgreSQL/API tests and actual browser operator flow PASS. |
| G4 | Missing/invalid/guest401, wrong-property403, missing write permission403 before any guide read. Q real-app SQL observer measured zero SQL on every denial; C used an actual signed guest token through direct API. Correct operator can preview via production web/proxy/API. Dev-only, not OIDC/F03 completion. |
| L1 | Independent same-catalog preference fit, closure/expiry/hard-price checks PASS offline. Actual model interpretation/explanation UNVERIFIED. |
| L2 | Positive evidence must match the specific hard need; generic access does not prove wheelchair suitability. Peanut/access/child-safety unknowns remain verification-only with specific localized steps. Offline probes PASS; actual capture/language UNVERIFIED. |
| L3 | Quiet/nature/budget and culture/social/indoor yield different fits/tradeoffs on identical sources; sponsor disclosed and cannot override constraints. IDs/prices/bases/durations/source state independently checked. Actual Chinese/French paraphrases UNVERIFIED. |
| L4 | Actual API+PG with fake provider commits quoted M2 preferences before M3/domain computation, preserves hard needs on edit, needs no dates/party profile/room selection; domain M6 renderer has currentness, nested source trace and readable prices. Native output schema and fourth-turn DOM locator independently checked. Actual web→model→domain→UI remains UNVERIFIED. |
| C1–C3 | Contracts/data/identity/limits/leases and inherited evidence recorded before dependent editing; independent review/fix and integrated operator demo complete. Full actual guest matrix and final sprint closure remain pending. |

## Local verification and retained findings

C final relevant run: **263 passed**, including three new real-PG integration cases and two affected existing room/FAQ API regressions, with disabled/fake model only. One upstream Starlette/httpx deprecation warning. After the last narrow native mixed-channel guard fix, **99 affected native/orchestrator tests passed**; Q independently reprobed seven Ajv cases. Counts overlap and are not a unique summed total. Canonical Ruff (`cwd apps/api`), compilation and whitespace checks PASS on final source. [Backend log](evidence/sprint-8/final-backend-checks.log), [check summary](evidence/sprint-8/local-checks-summary.json), [static log](evidence/sprint-8/final-static-checks.log).

B web: **43 contract tests**, lint, typecheck and configured Next production build PASS. The final CSS-only mobile correction was rebuilt/linted; unchanged TypeScript/contract evidence reused. Q independently ran pre-read denial probes, three PG cases, four source-derived domain scenarios, child-safety unknowns, native-schema positives/negatives and real Chromium synthetic two-result DOM selection.

Seven Q findings were fixed and independently reprobed: per-venue unknown-code ownership; unreachable secondary-hours validation; unsatisfiable guide-only native schema; browser startup state handoff; same-session fourth-turn locator; hard-need set ordering; mixed-channel empty-response regression. No unresolved engineering finding or new backlog story remains. Initial failures are retained in the Q report/local evidence; none is relabeled as a prior PASS. Root canonical lint additionally exposed import-only formatting differences; parsed ASTs remained unchanged after correction.

Actual operator demo used linked offline browser segments after a driver selector correction and observed mobile CSS fix. Final mobile body/viewport both390; price refresh/conflict resolution/revoke/delete and denied signed guest/wrong property verified, final guest facts0. API/web stopped with exit143. [Sanitized demo summary](evidence/sprint-8/operator-browser-summary.json). Screenshots/raw credentials stay private0600 outside Git.

## Concrete live proposal — not authorization

[Exact proposal/pins](evidence/sprint-8/live-acceptance-proposal.json), [four inputs/expected](evidence/sprint-8/acceptance-cases-proposed.json), [independent expected oracle](evidence/sprint-8/independent-oracle.json). Proposed case SHA **`680840d55ecf61df8b95fb011c43a575901648845e4307fe9f0f4e10eb106a78`**; oracle SHA **`f2a1b9561f18f6a2b265ed592f2f81fceef7fd71ac99d091d3612d40fc9fa874`**. Data/prompt/config pins are the candidate files map, raw fixture hashes and exact baseline primary1.0/secondary1.0 source hashes/generation3 in the independent oracle.

Requires NEW explicit approval on #100: **4 guest turns/max8 requests; gpt-6.1-sol/low; max2calls/turn,25s/call,45s/turn,700output tokens; no automatic retry/fallback; stop on first blocking failure.** Two fresh Chinese/French briefs use the same catalog. A third session handles mixed/RTL hard suitability unknown, then clarification/edit and language change while preserving hard needs. Mobile/RTL observed within those4turns. Only the reviewed browser controller advances after exact root/Q semantic receipts; C stops/seals on failure, including unused slots. Last turn needs independent verdict before completed sealing.

Inherited `codex_cli` has **no verified native generation token cap**: it post-checks reported output usage and rejects above700. This is an acceptance/output check, not a guaranteed generation/billing cap. No new cap/provider/automatic retry is introduced. Requested profile, returned model/usage and latency will be recorded when available; unavailable fields remain unavailable.

No Sprint8 actual model request, live-authorized config/state or allowance has been used. Sprint7 allowances remain closed. Coding token/retry/active-hour telemetry is unavailable;15–27 active-agent-hours remains an uncalibrated forecast, not measured actual, human-days or a deadline. No CI was manually started/rerun; automatic workflows may run on publication, and no CI PASS is claimed. No deployment, production OIDC, full itinerary/booking/payment/live inventory/maps/weather, real-hotel approval, or stretch47/48/53 is included.
