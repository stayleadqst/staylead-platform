# Independent remediation review

Reviewer: fresh `/root/remediation_review`, `gpt-6.1-sol/high`, read-only assignment. No provider calls, server starts or product edits by reviewer. C records the returned findings and verdicts here; no separate enforced read-only sandbox was available.

Final pre-live candidate: `9929c33a77eb1354e8468b5130d2b36df12e919e`, tree `ecdcde712379330852bea2bad95beb461cf0dd60`. Reviewer confirmed ready for the explicitly approved namespace2 batch, with no remaining blocking code finding. This is readiness, not semantic acceptance.

| Finding | Disposition / verification |
|---|---|
| P1: sanitized receipt removed the ID used by continuation | Raw receipt retained in memory only; public evidence hashes it. Actual explicit T1 continuation later returned200. |
| P1: HTTP502 exited before partial-success recovery | Partial receipt routing precedes generic HTTP failure; four actual routing tests pass. |
| P2: capture initially inherited umask before chmod | Exclusive no-follow creation with0600, directory0700/symlink refusal; permission tests pass. |
| Observed actual guard rejection | Schema parsed. Semantically correct slash dates differed from canonical ISO literals; prompt now preserves exact canonical/source date/time/numeric literals. Guard unchanged. Historic rejected schema field remains unknown. |
| Recovery composer lock | Matching only parent resumeReceiptId left older unknown answer-only siblings unresolved. Reconcile same-receipt siblings, preserve historical answers; production-browser mocked distinct-continuation proof passes. |
| P2: completed turn exclusion used old client ID | Resolver now excludes actual new request ID; changed-ID test passes. |
| Hardcoded English prefix in requested-language answer | Removed from answer prose; typed guest_claims/refs and canonical brief/receipt provenance remain. VI exact-text/refs regression passes. |
| Driver exception attribution / orphan response waits | Uses current RUN_ID, handles response promise rejection immediately, saves screenshot/result and holds browser without sending another request. |
| Unsupported network-zero claim | New observer records browser-context external origin/hash/count. Server network metric explicitly remains unmeasured. |

Independent focused checks reported:37 backend,15 chat-state,14 runtime,4 routing tests, Node syntax and diff checks PASS. C separately verified41 backend contracts,14 runtime,4 routing tests and backend Ruff/compile. Relevant PostgreSQL10 PASS. B verified36 web contracts/lint/typecheck/productionbuild, with actual production-browser mocked recovery proof; C confirmed the build is newer than changed web sources.

Actual semantic verdict for namespace2: pending recorded observations and fresh reviewer assessment.

## URL correction and bounded diagnostic follow-up

- Q independently passed64 focused backend tests and source-removal/index restriction probes for URL retention. Only exact same-hotel preliminary URL evidence inside candidate index survives selector omission; final current-source and claim-own-citation guards remain.
- C passed68 backend contracts and Ruff on559a3d2. Diagnostic helper passed14 tests; actual read-only PG preflight caught a wrong table import and demonstrated failedT6 has a request record without a user-message row. Fixed in0227; Q rechecked imports/counts/hashes and found no blocking issue. No model calls occurred during failed preflight.
- Q reviewed NS5 path-only preparation:16 tests, unchanged9/18/2 caps, distinct paths, refuseoverwrite and JavaScript syntax passed. No NS5 private files initialized; no calls authorized by preparation.
- Q classified diagnosticT7 state PASS but answer FAIL: choices13/14 are wrong for guest12/13, not a numeric false positive. Typed pending-date clarification must bind options to the exact current utterance and year to nonpending check-in; ordinary unknown guards stay strict.
- Q classifiedT8 state PASS, overall semantic degraded by unsolicited false breakfast/Wi-Fi unknowns. Current-turn scope correction is required; HTTP200 alone is insufficient.
- Q approved investigating a typed fixed courtesy intent forT9 while preserving empty-output rejection. A number-free arbitrary sentence can still assert hotel facts; do not claim numeric filters formally prove translation semantics. Final actual semantic review remains necessary.

## Final clarification and courtesy candidate — b9abb91

Q found and closed two defects: digit-set parsing accepted decimal/clock/reordered full dates; a no-year pending clarification was incorrectly brief-independent. Final complete-token validation rejects those forms,13/14 andyear2027; source12/13 with allowedyear or noyear passes. A domain-specific validator is injected by composition; the neutral default rejects, and preparation may not emit committed clarification. No-year clarification is brief-dependent at version4 without a pending value reference. PG replay after resolution at the same language revision is stale and adds no provider call.

Q independently passed77 focused tests and targeted boundary probes, confirmed maximum language-tag prompt2995<3000, and reported no remaining blocking code finding. C passed82 contracts/architecture plus4 PostgreSQL/API tests, Ruff, compile and diff checks. Actual provider scope/courtesy translation semantics remain unverified until the authorized fixed-candidate matrix. No live model calls during these checks.

## Structured output mechanism — e9424bc

Namespace5 repeated the empty-content class at turn2 (4requests used,14remaining): only valid labels, no answer content. Meaningful guard correctly rejected; ENrev2/briefv2/child-pending persisted. C stopped all services without retry and changed the mechanism rather than adding another task prompt.

Q independently passed84 focused contracts and17runtime checks, then checked the new Foundry compatibility regression. Ajv validation of the actual output schema rejects label-only,refs-only,whitespace-only unknowns,missing/extra labels, while accepting combined hotel+guest claims,valid unknowns,typed clarification and typed acknowledgement. Native CLI schema support and strict subset were checked in official documentation. Schema size22888bytes,223properties,depth3,2210property/enum chars does not require a refactoring workaround.

Two review findings closed: remove Codex transport-envelope instruction from shared domain prompt to preserve flat Foundry responses; rename telemetry to response_envelope_unwrap_requested because request configuration is not observed result proof. Exact request-controlled Codex envelope parsing rejects missing/extra/malformed envelopes; no arbitrary unwrap or flat fallback. Preparation remains unchanged and permits empty fact selection. Q reports no remaining concrete finding; C99contracts/architecture,4PG/API,17runtime,Ruff/compile/diff PASS. No live model calls during these checks. Actual CLI schema acceptance and answer semantics remain pending.


## Context-bound output — 536b90d / a059046

Q reviewed captured NS6T2/T7 semantics: both delivered no answer; all nine state targets pass, seven answer targets pass. Null-age ref rejection and exact-option rejection were correct. Nonnull pending checkout ref acceptance was a separate runtime gap found offline, not the observed T7 failure cause.

A now constrains refs to authoritative nonnull/nonpending fields; pending-age unknown/question is structurally required and prompt-targeted. Current pending checkout plus one slashpair requires nonnull typed clarification in every branch; runtime exact option order/numeric validation remains. Null and pending refs reject at runtime. Q independently10focused tests and9Ajv probes plus final required-question/empty-allowlist probes PASS, no concrete finding. C102contracts/architecture+4PG/API retained; final76grounded contracts+35runtime/helper+7routing,Ruff/compile/diff PASS. These checks do not prove actual model semantics.

B fixed receipt binding to the unique persisted same-turn runtime request hash and separated driver_checks_passed from matrix_pass (null until semantic review; false on known failures). Q independently7Node tests+syntaxPASS,17runtime reused. All findings closed before NS7. NS7 live allowance independently granted by Hieu; actual semantic review pending. No model calls during fixes/review.


## Namespace7 actual and95fcf27 prompt correction

NS7 product fixedthrough18requests: T1–5/T7 fullobservedPASS; T6corefacts/URLowncitation/state/copyPASS but contextualURLlabel omits pinnedsynthetic/nonfunctional qualification; T8wrongclarifypreparation instead of explicitset_dates, then unsupported15claim boundonlycheckin correctlyrejected. PGprovedbrief4/checkout14/pending unchanged whileKOrev8persisted. T9APIcourtesy/observedstatepreservationPASSdoesnotrepairT8orprovideUIcopy. FullmatrixFAIL; see namespace7-semantic-review.json.

A changed preparation guidance onlyfor pending dates.check_in/check_out: explicitunambiguous currentdate supersedesunresolvedstoredendpoint, notfalseconflict. Finalprompt preservescitedsource synthetic/nonfunctional qualification, nofixturehardcode. Qfinding narrowedinitialallpendingfieldwordingto datesonly; final2changedtestsPASS, max64taginstructions2970, no remainingcodefinding. Fakevalidpatch regression proves mutation/consumer/guardpath, not actualmodelpatchchoice. BNS8mappingisolated/capsunchanged, Q2mappingtests/syntaxPASS;17runtime/7routingretained. No newinferenceallowanceimplied.
