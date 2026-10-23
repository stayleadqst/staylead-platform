# Sprint 5 — canonical guest brief and safe chat edits

**Outcome: implemented and locally verified; Sprint DoD BLOCKED.** No Sprint 5 story is Done. The first real-Grok guest turn failed with `provider_timeout`/HTTP504 before any brief mutation. The shared four-turn semantic acceptance is unverified. Follow-up [S5-R1 #88](https://github.com/stayleadqst/staylead-platform/issues/88) is in the product backlog, linked to #84–#87 and E2 #4. No sprint, parent or epic was closed.

Delivery branch: `sprint-5-canonical-brief`, based on verified S4 local `65a901ef8bc681689e60183355dd5d4b466b18d8` / tree `f0b80eec93b0e7c398c8ef8a8fe92333bf483684`. Remote S4 commit `9576a59004667395bd91ee548eaab4bfdb518cb0` has the same tree; PR #83 remains unmerged. Delivery is branch/draft-PR only; publication identity is recorded on #87 at handoff. No main merge or deployment.

Final delivery source/test/fixture fingerprint: **`689dcbecfc207332f5ad58833fed300265d0aa2e992217c549e8522a51234c7d`**,198 files. Review/live used `743c25d3bb9b66a1a234b32503cc2ce583778e50db36d65f955fcbe639b2d7ba`; afterward one blank EOF line in a test was removed for the staged whitespace gate. Product source/fixtures are unchanged, and the cached reviewed test code equals the delivery compilation. [Manifest](evidence/sprint-5/candidate-manifest.json), [independent review](evidence/sprint-5/review-findings.md). Documentation/evidence are outside this fingerprint.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| #84 canonical dates/members | A `/root/brief_backend`, gpt-6-luna/high | Implemented, offline/PG/API/browser verified; final fingerprint | Explicit/partial dates, stable IDs, pending fields, persistence/scope/version and actual next consumer | **Blocked:** shared real-model gate; #88 |
| #85 safe edits/recovery | A plus B integration, both gpt-6-luna/high | Implemented and independently reviewed | CAS, atomic source/delta/receipt, partial failure, same-ID recovery, receipt-only resume | **Blocked:** shared real-model gate; #88 |
| #86 mixed FAQ/web | B `/root/brief_consumer`, gpt-6-luna/high | Production consumer locally verified | Mixed FAQ/edit, mobile/desktop, historical receipts, freshness and unknown completion | **Blocked:** shared real-model gate; #88 |
| #87 coordination/integration | Coordinator `/root`, exact model/effort unavailable | Contracts, integration, evidence and bounded delivery | AC/status mapping, retained failures and remediation backlog | **Blocked:** integrated Sprint Goal not accepted; next owner follows #88 |
| Acceptance harness | `/root/acceptance_runtime`, gpt-6-luna/high | Delivered; helper exited | Fake default, redacted events, fault controls, explicit live limits | No product finding; live process stopped |
| Independent review | Fresh `/root/sprint5_reviewer`, gpt-6.1-sol/high | Code/remediation and offline consumer **PASS** on final pin | Q1–Q5 fixed and independently reproduced; actual PG/API/React/browser evidence inspected | Sprint DoD **Blocked**, not a real-model PASS |

## Implemented behavior and ownership

A owned neutral contracts, Hospitality schema/prompts/validators, M2/orchestrator, persistence/store/migration and producer tests. B owned guest-chat composition, API entrypoints, client/UI/domain rendering and consumer tests. Coordinator owned integration, expected results, acceptance operation and delivery. Harness file had a single delegated owner. A fresh reviewer edited only review evidence/probes, with read-only behavior by instruction rather than enforced runtime permissions. No mutable product file had two active editors.

Database schema5 explicitly upgrades schema4 without reseeding existing hotel/source/session data. Canonical brief version is separate from chat state; no-op/FAQ does not advance it. Dates/nights, adult count, stable child IDs/ages and pending fields are validated in Hospitality; neutral core treats the data as opaque. One explicit date endpoint survives across turns; the missing endpoint remains pending and nights remain unknown. Ambiguous/conflicting input preserves confirmed values.

Typed proposals become authoritative only after trusted server scope/version validation. Brief, actual applied delta, durable source utterance/reference and request-bound receipt commit atomically. Guest claims have validated canonical references and separate numeric/URL authority; hotel claims retain M1 facts/citations. Summary and receipt delta are rendered by the Hospitality domain, without raw internal JSON/UUID paths.

High-overlap FAQ retains one call when no patch is proposed. Low-overlap selection combines semantic understanding and patch extraction; after commit, a final answer uses committed brief. Patch paths have at most two calls under the existing whole-turn deadline. Both prompts receive the exact domain patch grammar. Missing provider usage remains unavailable rather than zero.

Same-ID replay returns a stored status/effect, with zero mutation/model calls after an applied edit. Answer-only resume uses a new request referencing an original failed applied receipt and never reparses/reapplies the old edit. Unknown storage/freshness/timeout outcomes require same-ID verification; only explicit terminal failure/no-effect permits a fresh raw request. A failed acknowledgement after commit cannot add a child twice. Brief-dependent answer completion/replay checks `brief_version_used` together with S4 generation/approval/expiry; pure FAQ remains independent of unrelated brief edits.

## Local quality gates

- Initial integrated full backend: **86 passed** on isolated real PostgreSQL18, fake/disabled providers. [Log](evidence/sprint-5/backend-final-tests.log).
- Final affected backend suite after all behavioral repairs: **46 passed** on final candidate, including8 consumer PG and8 producer PG cases. Unaffected initial results were reused; import-only corrections were verified by Ruff/compile. [Final affected log](evidence/sprint-5/backend-repaired-focused-tests.log).
- Final web: **32 contract tests**, ESLint, typecheck and configured Next16.4.2 production build passed. [Contracts](evidence/sprint-5/consumer-timeout-ack-web-contracts.log), [lint](evidence/sprint-5/consumer-timeout-ack-web-lint.log), [typecheck](evidence/sprint-5/consumer-timeout-ack-web-typecheck.log), [build](evidence/sprint-5/consumer-timeout-ack-web-build.log).
- Modified/new Python configured Ruff, compileall and diff whitespace passed. [Lint](evidence/sprint-5/backend-final-lint.log), [compile](evidence/sprint-5/backend-final-compile.log). Existing Starlette/httpx deprecation remains a warning.
- Actual production UI→API→PostgreSQL fake-provider checks passed on desktop/mobile390px, including post-apply failure/resume, lost response/same-ID replay and late response after changing hotel. Fake outputs do not establish model semantics.
- Fresh independent review verifies all198 hashes and code/consumer behavior. [Report and probes](evidence/sprint-5/review-findings.md). The live gate failed, so this review is not a full DoD acceptance.

## AC: expected, observed and limitation

| AC | Expected → observed / evidence |
| --- | --- |
| B1-AC1 capture | Explicit dates/adults and later child retain correct canonical state, durable refs and stable child ID. Actual PG/API and fake production-browser sequence passed. Real-Grok capture **unverified**, blocked by #88. |
| B1-AC2 clarification | One-sided dates persist; ambiguous/conflicting values preserve confirmed fields; missing child age is pending; resolving a field clears only its pending flag. Final domain tests and [independent pending probe](evidence/sprint-5/review-probes/pending-recovery-final.json). Real-model clarification **unverified**. |
| B1-AC3 next consumer | Actual API/provider restart plus original utterance outside bounded history still supplies persisted brief and returns correctly referenced guest claims; independent paraphrase/correction expectations recorded. [Restart probe](evidence/sprint-5/review-probes/restart-consumer.json), consumer tests. Real-model semantics including negation remain **unverified**. |
| B1-AC4 scope/version | Wrong session/hotel or forged extra protocol fields reject; two expected-version writes have one CAS winner; FAQ/no-op keeps brief version. Producer PG, consumer HTTP and independent foreign receipt404/zero-call probe passed. |
| B2-AC1 exact delta | Precise member/date changes preserve unrelated fields; checkout-only delta omits unchanged check-in; ambiguous references remain pending. Domain tests, final React probe and desktop screenshot passed. |
| B2-AC2 atomic receipt | Injection/duplicate source failure rolls back brief/ref/receipt/delta; receipt and original utterance survive answer failure before transcript completion. Producer PG and actual partial/resume consumer tests passed. |
| B2-AC3 CAS/idempotency | Concurrent writes do not overwrite; same-ID replay has no duplicate child; request identity binds scope/payload/receipt. PG concurrency and same-ID actual consumer probes passed. |
| B2-AC4 partial success | Forced post-apply model/source/brief failures retain historical effect and explicit partial outcome. OperationalError, lost acknowledgement and delayed acknowledgement beyond real1s deadline recover receipt; same-ID replay adds0calls. [Final lost-ack](evidence/sprint-5/review-probes/recovery-final.json), [timeout](evidence/sprint-5/review-probes/timeout-ack-final.json), [in-flight](evidence/sprint-5/review-probes/inflight-consumer.json). |
| B2-AC5 resume | Actual failed add-child→same-ID replay→explicit receipt-only resume leaves one child and unchanged brief mutation version; old edit is not parsed. Consumer PG, independent Q4 and browser partial/resume passed. |
| B3-AC1 mixed | Actual production browser returns breakfast06:30–09:30 from synthetic approved M1 and applies requested brief edits; pure FAQ requires no profile. Real-Grok mixed outcome **unverified**. |
| B3-AC2 UI state | Domain current summary, pending labels and historical receipt/delta are distinct; no raw JSON/UUID paths or raw-new-ID retry after uncertain effect. Desktop/mobile screenshots plus actual hidden-response503→same-ID200 prove two initial fakecalls followed by0calls/one child. [Unknown completion](evidence/sprint-5/browser-unknown-completion.jpg), [recovered](evidence/sprint-5/browser-unknown-same-id-recovered.jpg). |
| B3-AC3 authority | Guest claims use canonical refs, hotel claims retain M1 facts and literal guards. Unsupported numbers/URLs/foreign refs reject; current UI summary derives from storage. Domain/orchestrator tests and independent restart consumer passed. Real-model separation **unverified**. |
| B3-AC4 in-flight | Concurrent briefv1→v2 or source revocation while fake answer paused prevents obsolete completion; partial receipt stays historical and current summary isv2; no automatic model retry. Late old-hotel response cannot overwrite new hotel/brief. [Independent probe](evidence/sprint-5/review-probes/inflight-consumer.json), [late browser](evidence/sprint-5/browser-late-response-other-hotel.jpg). |
| B3-AC5 completed replay | Completed dependent answer atv1 becomes stale afterv2; historical receipt remains intact/current brief separate;0 replay calls. Pure FAQ replay remains current if only brief changes. Producer/consumer PG and independent replay probes passed. |
| C-AC1 ownership | Actual owners, contracts, file leases and dependency handoffs fixed before implementation; two builders parallel, helper bounded, reviewer fresh. No dependency cycle or concurrent writer conflict. |
| C-AC2 findings | Reproduced failures had targeted owners, preserved evidence and rereview. Same unsafe-retry failure class was reassessed centrally rather than leaving independent path patches. Unresolved real-model gate is tracked in #88 with impact/attempts/evidence/AC/epic/priority. |
| C-AC3 handoff | This report binds candidate, checks, observations, failures and limitations. Every remaining live obligation is explicit; integrated Sprint Goal remains **Blocked**. |

## Actual browser evidence

- [Post-apply partial success](evidence/sprint-5/browser-partial-success.jpg): one child with unknown age, dates/adults retained, only receipt-linked continuation offered.
- [Fixed desktop receipt](evidence/sprint-5/browser-receipt-fixed-desktop.jpg): checkout changed to2026-12-14/nights4, without claiming check-in missing.
- [Mobile final state](evidence/sprint-5/browser-mobile-final.jpg):390px viewport/document width, dates2026-12-10→14, nights4, adults2, no child after removal.
- [Unknown response and replay](evidence/sprint-5/browser-unknown-same-id-recovered.jpg): same request ID, initial2 fakecalls then0; briefv1/one child.
- [Late old response](evidence/sprint-5/browser-late-response-other-hotel.jpg): delayed Harbor response leaves Lagoon page with no old brief/breakfast. No persistent transcript is claimed.
- [Initial receipt defect](evidence/sprint-5/browser-receipt-initial-failure.jpg) retained; final screenshot shows repaired wording.

## Real-model blocker and new backlog story

[Expected outcomes](evidence/sprint-5/semantic-expectations.json) were fixed before any live call, including explicit no-add negation in the fourth planned turn. [Run boundary](evidence/sprint-5/live-boundary.json) preserves four-turn/eight-call limits and the same candidate/expectations hash.

Only the first guest turn was attempted. Observed **1 provider attempt,0 successful returned model results**, HTTP504 `provider_timeout`, no automatic paid retry. Database: brief version0, chat state0, receipt count0, request terminal error. [Observations](evidence/sprint-5/live-observations.json), [runtime events](evidence/sprint-5/runtime-events.jsonl), [live failure screenshot](evidence/sprint-5/live-initial-failure.jpg).

Deployment read-only query reports `Succeeded`, model `grok-4-1-fast-reasoning`, version1. Credential retrieval succeeded and authenticated read-only GET models returned200 in4.256s; this does not prove inference readiness or a deployment alias error. [Diagnostics](evidence/sprint-5/live-provider-diagnostics.json). Adapter remains direct HTTPX with existing25s provider/45s turn limit and no automatic retry. Cause of inference timeout is **unknown**; do not claim transport/config latency has been ruled out.

[S5-R1 #88](https://github.com/stayleadqst/staylead-platform/issues/88), E2/P0, contains problem, impact, measures attempted, retained evidence, acceptance criteria and links to all affected stories. It is Draft in the product backlog, not automatically started or assigned to another sprint. #84–#87 retain Blocked and Open. Recovery requires diagnosis/remediation and a separately authorized bounded real-model acceptance; no limits were raised to force a pass.

## Repairs, usage and limits

Independent review fixed pending-field cleanup, one-sided-date retention, misleading date-delta rendering, and unsafe new-ID retries after lost apply acknowledgement, replay lookup failure and turn timeout. Final Q4 reproductions verify receipt recovery and central same-ID uncertainty classification. Both selector and answer receive exact patch rules; canonical pending clarification is permitted without invented values or hotel citations. Unknown usage stays null. Initial failures and final comparisons are retained in reviewer probes.

The initial web build omitted required public domain/contract configuration and failed prerender; configured production builds passed. A coordinator lint attempt additionally enabled an unnecessary broad style profile; its diagnostic is preserved locally outside the delivery, and the actual configured gate passed after five import-only corrections. No gate/config/expectation was weakened to accept a product failure. Default test/build/startup made no live calls.

Live tokens and monetary cost: **unavailable**; do not infer zero billing or assume provider processing stopped when the client timed out. Coding-agent token/active-time metrics are unavailable. First timing anchor17:00:22 local; earlier inspection was not precisely timed. No savings/velocity claim is made.

Sources/guests/media are synthetic/authored. No real hotel/operator acceptance, full parent stories, room/stay planners, persistent browser transcript, stretch #74, deployment, paid-resource creation, timeout/budget increase, main/PR83 merge or parent/epic/milestone closure. No manual GitHub CI invocation/rerun or CI wait gate; automatic workflows may run when publishing/updating the branch/PR, and no CI success is asserted. Secrets/Bearer/private runtime values are excluded from the delivery.

The live API is stopped. Local acceptance services are returned to fake/offline mode or stopped before handoff; private runtime/isolated databases remain local for recovery. Future owner starts from #88 and the final fingerprint without repeating unaffected checks or resetting consumed live-attempt accounting.
