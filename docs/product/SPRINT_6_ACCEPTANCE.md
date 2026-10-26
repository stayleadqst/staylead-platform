# Sprint 6 — acceptance and execution report

**Chưa Done.** #91/#92/#93/#74 **Blocked** vì shared actual semantic/UI DoD; #95 remediation và #94 coordination **In Progress**. Reviewed source `b666454970829c56ae52d3cfe184b7414c4d8cd4` đã chốt; full nine-turn actual acceptance trên bản này chưa chạy. Không ghép các lượt đạt từ candidate/batch khác nhau thành matrix PASS.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|
| Language / grounding / preparation | A — gpt-6-luna/high | b666454 implemented, locally verified, independently reviewed | 95 focused contracts; affected S6 PG/API4; Ruff/compile/diff PASS | Actual model/UI confirmation after allowance decision |
| Consumer / bounded harness | B — gpt-6-luna/high | Namespace10 mapping prepared only; production web unchanged | Runtime17; prior39 harness/7routing; 32 screenshot hashes verified ignored/untracked | No NS10 initialization or calls without explicit allowance transfer |
| Independent review | Q — gpt-6.1-sol/high | Native-preparation READY, no remaining scoped finding | Strict-schema/Ajv positives and negatives; captured NS9 replay; mocked Codex/Foundry transport | Full actual9case semantics still unproven |
| Integration / delivery | C — root runtime ID/effort unavailable | Source pinned b666454; NS9 paused after1request | Final schema4tests/diff PASS; prior af4 gates retained | Publish code/text; incremental1+transfer17 requested, pending |

## Story status / AC map

| Story | Status | Established evidence | Missing before Done |
|---|---|---|---|
| #91 L1-AC1–5 language state | Blocked | Preference scope/CAS/restart/replay/late-response and same-child continuity; separate revision | Complete fixed-candidate mutation/answer/UI sequence |
| #92 L2-AC1–4 grounding | Blocked | Source/numeric/URL/injection/revocation/conflict negatives; lexical baseline/per-case observations | Complete actual semantic verdict on current source |
| #93 L3-AC1–4 presentation | Blocked | Production build/layout/RTL/CJK/Devanagari/races/fallback evidence | Full nine-turn actual UI/copy matrix |
| #74 B12a-AC1–4 current copy | Blocked | Current/stale/late-state and clipboard success/failure/selection fallback | Full current-candidate actual UI/copy matrix |
| #95 R1-AC1–5 remediation | In Progress | Concrete captured failures/offline reproducer, bounded correction, scoped review, PG recovery checks | Actual semantics and final delivery gates |
| #94 C-AC1–3 coordination | In Progress | Owners/leases/handoffs, versions/counters/failures preserved | Final AC verdict and delivery |

No story is newly Done. Existing #95 is P0/E2 in Sprint6, linked to #91/#92/#93/#74/#94 and contains problem, impact, attempts, evidence and AC. Current wire/semantic failures remain within that remediation scope; **no duplicate new story created**. Keep parents/epics/milestone open.

## Actual results and accounting

| Batch | Actual requests | Evidence / outcome |
|---|---:|---|
| Original +NS1+NS2+NS3 | 2+4+6+8=20 | Historical failures/counters retained |
| NS4 |18| UI1–6/API7–9; candidate changed during diagnosis, not fixed-matrix PASS |
| NS5 |4| T1PASS; T2 label-only rejected; remaining14 transferred once with approved increment4 |
| NS6 |18| All9state targetsPASS,7answersPASS/2FAIL; UI1–2/API3–9 |
| NS7 |18| T6 qualification gap, T8 date state/answer failure; T9 API only |
| NS8 |18| T2 label drift; T4 spurious member pending; T6 URL punctuation rejection; T8 unrelated unknown; UI1–4/API5–9 |
| NS9 |1| T1 structurally invalid authorization.op; stopped immediately; T2–9 NOT_EXECUTED |
| **Total** |**97**| No counter reset; no automatic retries; prior explicit receipt resumes retained |

NS9 is paused with `authorized_for_live_calls:false`; **17 unused requests are reserved and have not been transferred**. A smallest increment1+transfer17 into a new maximum18 batch is requested and awaiting explicit approval. No namespace10 private config/state/init/call yet. Stop at the first blocking live failure and investigate offline; unused allowance is not a requirement to spend.

Same requested `gpt-6-luna/low`, CodexCLI0.153.4, max2calls/HTTP turn,25s/provider,45s/turn,700-token postcheck. Served-model identity, native pre-generation hard cap, full tokens/billing and agent token/cache usage remain unavailable. No Grok or extra judge/translation calls. Default tests/build/startup remain offline.

## Latest actual evidence

NS8: [manifest](evidence/sprint-6/remediation/namespace8-candidate-manifest.json), [independent review](evidence/sprint-6/remediation/namespace8-semantic-review.json), [comparison](evidence/sprint-6/remediation/namespace8-case-comparison.json), [closed counters](evidence/sprint-6/remediation/namespace8-run-state-closed.json), [summary](evidence/sprint-6/remediation/namespace8-final-summary.json). Nine turns/18requests; no resumes/retries. Product unchanged. T1–3 core answer/state/copy PASS, but T2 label meaning drift. T4 FAQ answer/copy PASS but an unrequested clarify operation added pending member. T5 API core FAQ PASS with inherited wrong state. T6 API502 after an Arabic comma immediately following the exact trusted URL; raw answer qualification also deficient. T7 legitimate date clarification inherited member pending. T8 correctly resolved checkout15/nights5 but inherited wrong member pending and emitted unrelated hotel unknown. T9 preserved actual state, not the global target. Final readonly PG proof is embedded in independent review. No full matrix PASS.

NS9: [manifest](evidence/sprint-6/remediation/namespace9-candidate-manifest.json), [independent review](evidence/sprint-6/remediation/namespace9-semantic-review.json), [stop decision](evidence/sprint-6/remediation/namespace9-stop-decision.json), [paused counters](evidence/sprint-6/remediation/namespace9-run-state-paused.json). On af4b42f, T1 proposed correct dates/adults/intents/quotes but both authorization.op fields were operation objects rather than enum strings. Parser rejected before M2/preference/receipt; readonly PG found no committed brief/preference/receipt. Changing only those types offline passes parsing and authorization. This diagnostic control is not an accepted live answer. T2–9 were not executed. One request, no retry/resume, no calls after blocker; max provider5.940s/HTTP6.055s/reported output205tokens.

Historical NS6/7 evidence remains immutable: [NS6 review](evidence/sprint-6/remediation/namespace6-semantic-review.json), [NS7 review](evidence/sprint-6/remediation/namespace7-semantic-review.json), [NS7 comparison](evidence/sprint-6/remediation/namespace7-case-comparison.json).

## Implemented corrections / current gates

Reviewed af4b42f introduced current-turn per-operation authorization, same-call intents, source-bound response channels, required pending questions, canonical English labels/source-label context, persisted scope in existing receipt JSON and Unicode terminal URL punctuation handling. Raw quotes are not persisted; no DB migration or new model call. Same-model intent/quotes are not formal semantic proof. See [af4 gates](evidence/sprint-6/remediation/current-turn-local-gates.json); its cumulative96 field is a historical pre-NS9 snapshot.

Reviewed b666454 adds Hospitality-owned strict native preparation schemas to both low/high preparation paths using existing provider-neutral schema/envelope ports. Authorization.op can only be an operation-name string. Low empty fact selection/no-op stays valid; high preparation rejects empty/committed-only acknowledgement or clarification channels, matching its consumer. Foundry keeps the flat prompt/parser contract. Final answer/source/state guards remain strict; no extra model call or automatic retry.

[Current manifest](evidence/sprint-6/remediation/native-preparation-candidate-manifest.json):220 files, SHA256 `c33812807c537ffed561564528e72e70d219acc8a8eaca1929aefe2b1a24411a`. [Current gates](evidence/sprint-6/remediation/native-preparation-local-gates.json), [independent scoped review](evidence/sprint-6/remediation/native-preparation-review.json). Builder95focused contracts and4affected PG/API PASS; coordinator4final schema tests PASS. Prior native-preparation112contracts/architecture,39harness/7routing; mapping17runtime; Ruff/compile/diff PASS. Counts overlap and must not be summed. Mocked transport proves schema forwarding/envelope cleanup/Foundry compatibility, not actual model compliance. Prior unchanged web36contracts/15state/productionbuild/layout/copy recovery evidence reused.

## Delivery / privacy

Reviewed local source b666454 maps to prepared GitHub source object `eb8be575489bab9b4aa23e1b9e00726b91311d4e`, equal tree `77da592271da3e3cb01ab32bde72468a20b2b461`. At this report's prepublication checkpoint, branch head is f697edb; final publication/fetch receipt is recorded outside Git and in PR96. PR96 stays draft on `sprint-5-canonical-brief`, unmerged/not deployed. No manual CI/rerun or waiting gate; automatic workflows may run on branch update, no CI PASS claimed.

All **32 screenshots remain local**, ignored/untracked, per Hieu's explicit instruction. [Hash index](evidence/sprint-6/remediation/local-screenshot-index.json) is text only. No private captures/configs/secrets/image bytes or local backup refs may be published. No deploy/newpaidresources/old-repo changes/baseline or main merge/parent closure.
