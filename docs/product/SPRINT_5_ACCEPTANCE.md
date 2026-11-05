# Sprint 5 — canonical brief and safe edits: acceptance report

**Current outcome: real Codex consumer acceptance and fresh independent review PASS.** Hieu explicitly requested backend requests use results returned by Codex/ChatGPT instead of Grok. The local/test `codex_cli` adapter now supplies real model JSON to the existing backend; canonical validation, scoped PostgreSQL commits and rendered answers remain in the normal M1–M6 flow. This resolves the shared Sprint5 acceptance blocker under that provider amendment. It does not establish Grok recovery or production readiness for personal ChatGPT authentication.

Delivery: existing [PR #89](https://github.com/stayleadqst/staylead-platform/pull/89), branch `sprint-5-canonical-brief`, base `sprint-4-source-lifecycle`. No main/PR83 merge, deployment, paid-resource creation or parent/epic/milestone closure. Final leaf status and exact published identity are recorded on #87/#90; all earlier Blocked reports are historical and superseded only for the explicitly amended provider gate.

## Work, ownership and current stage

| Work | Owner / actual model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| #84 canonical dates/members | A `/root/brief_backend`, gpt-6-luna/high | Implemented; frozen product | Domain/PG/API, persistence/restart/scope/version; real Codex capture and clarification | None; local AC/DoD review PASS |
| #85 exact edits/receipt/recovery | A with B integration, both gpt-6-luna/high | Implemented; frozen product | Atomic receipts/CAS/idempotency/partial failure/replay/resume; real stable-child update/removal | None; local AC/DoD review PASS |
| #86 mixed FAQ and web | B `/root/brief_consumer`, gpt-6-luna/high | Production consumer verified | Desktop/mobile/late response/freshness; actual Codex answers and canonical UI state | None; local AC/DoD review PASS |
| #90 Sprint5 blocker remediation | B, gpt-6-luna/high; coordinator integration | Opt-in Codex adapter implemented and real sequence PASS | Default offline, production rejection, isolated tool-free subprocess, timeout/cancel cleanup, exact four-turn gate | Historical Grok cause remains unknown; no longer blocks revised slice |
| Acceptance harness and PG observation | Reused helper `/root/acceptance_runtime`, gpt-6-luna/high | Separate persisted Codex accounting and read-only PG proof | Offline 8/4/2 limits, redaction and reload refusal; actual state proof | No further provider calls |
| #87 coordination/integration | Coordinator `/root`, exact runtime model/effort unavailable | Evidence/report/backlog/publication | Candidate pin, expected/observed mapping, frozen historical attempts | Published; all scoped AC/DoD PASS |
| Independent review | Fresh `/root/sprint5_codex_review`, gpt-6.1-sol/high | Code and actual local acceptance PASS | Independent adapter9tests, Ruff/compile, harness limits, exact192 hashes, real events/UI/PG | [Review](evidence/sprint-5/codex-review.md) |

One active editor per file. Builders owned product code/tests; helper owned new harness/observation scripts; coordinator owned integration/runtime/evidence/docs/GitHub; fresh reviewer owned only its report. Prior independent source/receipt/recovery reviews remain valid for unchanged paths. No additional reporting-only agent.

## Fixed candidate and actual consumer result

[Manifest](evidence/sprint-5/codex-candidate-manifest.json): **192 files**, SHA-256 aggregate `511babeb7c0a3312ab24350d18381a087eaf8d4ec3153ba794b65bc946d2b5b4`, independently rechecked after the sequence. [Live boundary](evidence/sprint-5/codex-live-boundary.json) pins harness, unchanged original semantic expectations and frozen previous Grok state before the first Codex call. Product/tests/fixtures were not changed during acceptance. Evidence-only files are outside this product fingerprint.

Actual path: existing production-build UI → normal guest API/composition → `build_provider` → installed CodexCLI0.153.4 using existing ChatGPT login → returned JSON → normal server validation/commit → dedicated PostgreSQL18 → rendered answer. The source is authored synthetic hotel information; model responses are real. No fixture responses or direct database edits supplied acceptance state.

| Original sequential guest request | Expected → observed | API latency |
| --- | --- | --- |
| Dates +2adults + breakfast | Briefv1: 2026-12-10→13, nights3, adults2, children0; breakfast06:30–09:30 at Bến Gió tầng1, fact040 | 9.015s |
| Add one child, age not supplied | Briefv2: same dates/adults; one new stable child, age null; exact pending-age field and targeted age question | 9.361s |
| Child7; checkout14; retain checkin/adults | Briefv3: same child ID, age7, no duplicate; checkout14/nights4; unchanged checkin/adults; pending cleared | 9.760s |
| Remove child; explicitly no additions; breakfast | Briefv4: children0/adults2, dates10→14/nights4 retained; exact old child removed; grounded breakfast fact040 | 8.749s |

All four returned HTTP200/completed using two calls each. PostgreSQL independently contains brief/state version4 and four request/utterance-linked receipts with the exact deltas0→1→2→3→4. Missing age is a partial semantic update with a completed clarification answer, not a provider failure.

Evidence: [observations/checks](evidence/sprint-5/codex-observations.json), [actual runtime events](evidence/sprint-5/codex-runtime-events.jsonl), [read-only PostgreSQL snapshot](evidence/sprint-5/codex-db-observation.json), [initial capture](evidence/sprint-5/codex-turn-1.jpg), [child pending](evidence/sprint-5/codex-turn-2.jpg), [rendered age question](evidence/sprint-5/codex-age-clarification.jpg), [rendered correction](evidence/sprint-5/codex-correction-answer.jpg), [final rendered answer](evidence/sprint-5/codex-final-answer.jpg). Later screenshots show currentv4 separately from historical receipts/answers.

## Local quality gates

- New adapter full integrated backend: **110 passed** on isolated PostgreSQL before the final narrow custom-provider-alias correction. Final affected adapter/Foundry checks: **11 passed**; fresh reviewer independently ran **9 adapter contracts**, Ruff and in-memory compilation. [Current log](evidence/sprint-5/codex-backend-tests.log), [review](evidence/sprint-5/codex-review.md).
- Adapter checks cover explicit dev/test opt-in, disabled default/production rejection, exact subprocess argv/stdin/environment, actual usage/model fields, output validation, tool-event rejection, timeout/cancellation and whole-process-group cleanup including descendants after parent exit. Local CLI profile/features preflight exit0, no inference: [configuration proof](evidence/sprint-5/codex-config-preflight.json).
- New harness offline probes passed persistent8requests/4turns/2calls bounds, missing/malformed state refusal, reload refusal, separate resumes, redaction and zero startup calls. [Harness proof](evidence/sprint-5/codex-harness-check.json). Snapshot helper Ruff/compile passed; actual PG read required sandbox network permission after an initial pre-transaction connection refusal.
- Existing core verification reused: initial86backend; final affected46; remediation99backend before narrow follow-ups; finalgrounded23, focusedcontracts/API/consumerPG34 and final8consumerPG. Relevant failure regressions independently reproduced pre-fixFAIL/currentPASS. [Original review](evidence/sprint-5/review-findings.md), [remediation review](evidence/sprint-5/remediation-review.md).
- Unchanged web: **32 contract tests**, ESLint, typecheck and configured Next16.4.2 production build passed; actual desktop/mobile390px consumer, partial/resume, lost acknowledgment/same-ID replay and late-response checks passed. [Contracts](evidence/sprint-5/consumer-timeout-ack-web-contracts.log), [lint](evidence/sprint-5/consumer-timeout-ack-web-lint.log), [typecheck](evidence/sprint-5/consumer-timeout-ack-web-typecheck.log), [build](evidence/sprint-5/consumer-timeout-ack-web-build.log). The same production build ran the real Codex sequence.
- Modified Python Ruff/compile and whitespace checks passed. Existing Starlette/httpx warning retained. No manual GitHub CI/rerun or CI wait gate; automatic workflows may run after branch publication, no CI result asserted.

## Acceptance criteria mapping

| AC | Expected / observed and evidence |
| --- | --- |
| B1-AC1 capture | Explicit dates/adults/child become scoped canonical state with durable refs/stable ID. Actual PG/API/real Codexv1–v4 and screenshots PASS. |
| B1-AC2 clarification | Partial/ambiguous dates preserve confirmed fields; pending age created without invention and cleared on answer. Domain tests/[pending probe](evidence/sprint-5/review-probes/pending-recovery-final.json) plus real turns2–3 PASS. |
| B1-AC3 next consumer | Persisted brief survives window/restart and supports validated guest claims. [Restart consumer](evidence/sprint-5/review-probes/restart-consumer.json), API tests and real later-turn edits/negation/answers PASS. |
| B1-AC4 scope/version | Forged scope/fields rejected, one CAS winner, FAQ/no-op keeps briefversion. Producer PG/consumer HTTP/independent foreign-receipt404+zero-call probes PASS. |
| B2-AC1 exact delta | Checkout-only omits unchanged checkin; same-child update/removal preserves unrelated values. Domain tests, React/browser and actual Codex/PG deltas PASS. |
| B2-AC2 atomic receipt | Rollback preserves brief/ref/receipt/delta consistency; durable receipt survives answer failure. Producer PG and actual partial/resume consumer PASS. |
| B2-AC3 CAS/idempotency | Concurrent writes do not overwrite, same-ID replay does not duplicate child; scope/payload bound. PG concurrency and consumer probes PASS. |
| B2-AC4 partial success | Forced post-apply failures retain effect and explicit partial result; lost/delayed acknowledgment recovers receipt with0 replay calls. [Lost-ack](evidence/sprint-5/review-probes/recovery-final.json), [timeout](evidence/sprint-5/review-probes/timeout-ack-final.json), [in-flight](evidence/sprint-5/review-probes/inflight-consumer.json) PASS. |
| B2-AC5 resume | Failed add→same-ID replay→receipt-only answer resume leaves one child/version unchanged; no edit reparse. Consumer PG, independent Q4 and production browser partial/resume PASS. These injected mechanics are offline; no extra Codex failure injection claimed. |
| B3-AC1 mixed | FAQ and edit handled together; pureFAQ needs no profile. Actual Codex turns1/4 and unchanged ordinaryFAQ consumer PASS. |
| B3-AC2 UI state | Summary/pending/delta use committedstate; historical receipt distinct; unknowncompletion uses correct recovery. Desktop/mobile, [unknown replay](evidence/sprint-5/browser-unknown-same-id-recovered.jpg), and actual Codex screenshots PASS. |
| B3-AC3 authority | Hotel claims use approved M1 facts; guest claims use validatedbriefrefs; foreign/unsupportedclaims rejected. Domain tests plus actual Codex responses/PG PASS. |
| B3-AC4 in-flight | Brief/source changes reject obsolete completion; late oldhotel response cannot overwrite current state. [Independent probe](evidence/sprint-5/review-probes/inflight-consumer.json), [late UI](evidence/sprint-5/browser-late-response-other-hotel.jpg) PASS. |
| B3-AC5 completed replay | Old dependentanswer markedstale afteredit with historicalreceipt preserved/0calls; pureFAQ uses appropriate sourcefreshness. PG/consumer/replay probes and actual historical UI PASS. |
| C-AC1–3 | Ownership/contracts/dependencies explicit; findings reproduced/repaired/reviewed; expected/observed/checks/pin/limits/handoff retained; final backlog and publication state reported. |
| R2-AC1 | Protocol field fixed; semantic-selection leak reproduced and fixed; timing evidence distinguishes actual failures. Grok underlying timeout cause remains unknown, explicitly recorded as allowed by AC1. |
| R2-AC2 | Small infrastructure-only Codex adapter, same M1–M6 and scope/CAS/receipt behavior,25sprovider/45sturn/max2calls, defaultoffline/productionreject; affected regressions PASS. |
| R2-AC3 | Exact unchanged four-turn sequence on one fixed candidate through real production UI/API/PG/Codex, all expectations PASS. |
| R2-AC4 | Unchanged partial/receipt/same-ID/resume guards retain valid independent evidence; new adapter timeout/cancel contracts PASS; no autonomous retry. |
| R2-AC5 | Relevant checks, independent fixed-candidate review, truthful usage and branch publication/report; dependent stories have all amended AC/DoD verified. Historical phase rules are revoked and impose no closure restriction. |

## Limits, usage and remaining scope

Separate [Codex state](evidence/sprint-5/codex-run-state.json): **8/8 invocations,4/4 semantic turns,0 resumes,8 returned results,0 provider failures/cancellations,0 automatic retries**. Provider latency4.257–5.071s; turns8.749–9.760s, within25s/provider and45s/turn. Reported usage:62,798 input tokens and988 output tokens; CLI total_tokens and billing unavailable. Requested profile `gpt-6-luna`/`low`; actual served-model ID unreported and left null, not inferred.

The installed CLI lacks a verified native pre-generation output-token cap in this invocation. The adapter bounds input/event/error/output bytes, validates JSON/domain contracts and rejects reported output_tokens above the request cap after completion; this does not establish a hard generation/billing cap. Real outputs were within the unchanged700token per-request checks. This bridge is intentionally development/test only with native existing ChatGPT login, not a shared production service. [Official non-interactive CLI documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

No remaining blocker for the amended Sprint5 slice. Production provider deployment, operator/real-source acceptance, broader parent stories and Grok latency recovery remain outside this acceptance. No new issue emerged requiring a further remediation story. Existing #88 preserves the original problem/impact/attempts/evidence/AC/E2/P0/affectedstorylinks; #90 was created and executed in Sprint5 as requested. #88 is historical/superseded for the current provider gate; no promise that Grok works and no deferral to Sprint6.

## Preserved failure history and corrections

OriginalGrok1attempt returnedHTTP504 before mutation. ContinuedGrok7observedattempts returned5results including a tiny diagnostic; child persisted safely but answer/resume timedout. Cumulative8observedGrokattempts remain frozen; Hieu declined9/10extensions. [Initial observations](evidence/sprint-5/live-observations.json), [continued events](evidence/sprint-5/remediation-runtime-events.jsonl), [previous report](https://github.com/stayleadqst/staylead-platform/blob/6cbe19b5646c3a58278a5f876c1c898e898a9eea/docs/product/SPRINT_5_ACCEPTANCE.md). Prior partial runs were not combined into the new PASS. Failed/cancelled usage and exact Grok cause remain unavailable.

Pre-inference Codex configuration checks caught exec-only flag placement and reserved builtin-provider override; final custom profile passed without model calls. An observation checker initially compared removed-member objects to ID strings; corrected against the public delta contract with explanation retained, without changing product/semantic expectations. Read-only PG observation initially hit sandbox network denial, then succeeded with authorized local-network access. No extra model call was used for these corrections.

## Final handoff

Fresh final review PASS: [codex-review.md](evidence/sprint-5/codex-review.md). Exact published/local commit and tree identities are recorded on #87/#90 and PR89 after verified publication; this avoids a self-referencing commit hash in this document. Runtime counters are retained at8/4/0. Dedicated acceptance API18085, production web13015 and PostgreSQL55455 were stopped after verification; data and sanitized evidence retained. No merge/deployment or parent/epic/milestone closure is part of delivery.

## Verified publication and current rule correction

Published implementation/evidence commit `3a7b7974a9c2a2d4e21b5f31ab22b8ef42065647` and local `b2c517eb81c18ae237fe1ff58a4f1dacd9b2c5e7` have identical tree `c0d1322b5597f18b34e3e63b215ec0bb156169c2`. PR89 remains draft on the designated base. This report-only update does not change the accepted product fingerprint or evidence.

On2026-10-26 Hieu explicitly revoked every historical R0/R1/R2 rule. The previous automatic-review rejection of closing#84 is retained only as history; it is not a current restriction or approval gate. Workspace and repository AGENTS.md record the revocation. Those old rules must never be used to block current work.

#84–#87 and Sprint5 remediation #90 are **Done / GitHub Closed (completed) on2026-10-26**, with all amended AC/DoD PASS, independently reviewed and published. Closure follows the original Sprint5 execution instruction after Hieu explicitly revoked the historical phase rules; no further permission is required by those rules. No technical blocker remains for the Codex slice. #88 remains historical Grok diagnosis, superseded for this acceptance gate. No new story was required beyond #90, which was executed inSprint5. Current Sprint5-specific parent/epic/milestone and delivery boundaries are independent of the revoked rules.
