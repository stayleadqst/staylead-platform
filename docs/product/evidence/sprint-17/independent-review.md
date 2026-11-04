# Sprint 17 B05 — independent resumed final review

**Ready to merge: YES — full B05 AC1–3 and local technical DoD accepted on frozen candidate v3. No open actionable finding remains.** This verdict follows Hieu's explicit Sprint 17/B05 resume and the fresh repaired consumer run. It does not rewrite the expired first run or its Ready NO verdict in `REVIEW_FINAL.md`, claim real-model/hotel acceptance, or claim publication/merge/deployment.

Reviewer: `/root/q_b05_independent`. Requested model/effort: `gpt-6.1-sol/high`; actual runtime model/effort/token telemetry unavailable. Resumed Q deadline was 22:50 +07, within the new explicit human-authorized schedule; this review completed before that deadline. No candidate, index, branch, DB, service, browser or GitHub mutation by Q. Q wrote only `q/` evidence and dispatched no subagents.

## Candidate and independent verification

- Base `62a3a30d89dc60deba24b6558c8f0ff224588564`, tree `edeb630e1b67e9535c761d327f53fa390f9fa94b`; branch `sprint-17-b05-safe-edits`; checkout `/private/tmp/staylead-s17-canonical`.
- Final nine-file candidate fingerprint: `1b9717bb977274467d8329f7c502e3daa6ebccd4cae6a2e0ae2e20776a937416`. Exact paths/hashes are in `../candidate-v3.json` and `../b/candidate-v3-final-pins.json`. The original six v2 files are unchanged; product repair 3 adds changes only to `GuestChat.tsx`, `chat-state.ts` and its focused test.
- Q independently verified all nine source hashes before and after the final review/consumer evidence; see `resumed-v3-review-before.json` and `resumed-v3-review-after.json`. The latter also verifies all four harness and four fixture hashes against the pre-UI freeze. No source edits followed the freeze.
- Final production build ID `hPiQFBQXrGEUo6xs_Aydx` agrees between the final source/build pins and post-fix UI report. Historical `ui-freeze-pins.json` describes the original v2 run/build, not the repaired v3 run.
- Q read the three new source/test diffs and independently executed the actual pure helper against ten state-transition expectations: old/current/future versions, existing stale signal, null/undefined metadata, absent current brief, cancel/no version advance, partial commit and version zero. **10 PASS**, `resumed-v3-currentness-probe.json`. This required no HTTP, database, service or browser action.
- Q independently compared the exact full M4 projections at provider calls 10 and 12 against expected retained dates, party, access and budget fields. Both match; the clear removes only the view, then the lower-budget step changes only the amount. This proof is recorded in `resumed-v3-review-after.json`.

## Strengths

- The optional room view remains bounded, explicitly soft and guest-stated. It uses the native preparation schema, exact current-turn authorization, canonical confirmation and generic M2 patch/receipt flow. It introduces no hard view, view-fit guarantee or source approval.
- The applied receipt formatter covers all thirteen supported room fields and uses actual applied values rather than narrative. Clear-view and amount-only UI receipts match the intended deltas.
- The currentness repair is small and domain-neutral: render stale when an existing stale flag is true or both known brief versions differ. Both the room result and answer card use it. The current authoritative header brief remains monotonic. There are no new provider calls, HTTP requests, M2 mutations, domain imports, services or algorithms in this repair.

## Findings and repairs

### Q17-1 — Important / P2 — CLOSED

V1 native room schema could represent thirteen fields while the domain clear list and authorization target list capped at twelve (`guest_brief.py:107`, `:212`; native `preparation_output.py:131`). Q reproduced both rejection paths. Product repair 2 changed exactly those bounds to thirteen; generic operation max12 remains unchanged.

On matching v2 pins, Q actually completed four successful checks: domain clear13, domain set13, exact thirteen-target authorization for the clear, and the same authorization for the set. Date and party retention assertions then also passed. The inline probe subsequently exited **KeyError** because Q incorrectly expected an empty room dictionary after clearing all fields; existing `guest_brief.py:754–755` omits an empty optional container. Q did not correct or rerun that probe. `cardinality-v2-recheck.json` preserves the partial successes and overall probe failure; its raw traceback is in the tool transcript, not a separate raw file. The four actual cardinality checks, source and A's 22 passing affected tests close the product finding. The failed overall Q probe is not relabeled PASS.

### Q17-2 — Important / P2 — CLOSED on v3

The original Q source concern became an actual B consumer defect on v2: after normal confirmation advanced the brief, the old selected room still appeared current/enabled in the same focused page. `../b/browser-consumer-observations.json` preserves this failed run; no old selected action was clicked.

Product repair 3 changes the `TurnResultRenderer` and `AnswerCard` stale props in `GuestChat.tsx:775` / `:785` to use `isAnswerStale` from `chat-state.ts:10`. The helper preserves known stale signals, compares known response/current brief versions and preserves prior behavior when metadata is absent. It does not mutate saved state.

The fresh post-fix session on the same private DB reproduced baseline selection and the same confirmed child/access/view/budget edit. Before any focus/pageshow refresh or extra turn, B's actual AX observation showed the old result's out-of-date message and `Selected option` disabled. The new current result reported no checked option for the hard access need, without inventing a fit. This is a **new passing run**, not recovery of the failed original session. Q's independent helper checks and source review support the same behavior, including out-of-order/version and partial-commit cases.

### Other findings

No open Critical, Important or Minor actionable source finding remains. C's earlier omitted-field formatter defect and repair 1 are retained in the sprint evidence; the final formatter covers all thirteen fields. No optional framework, new planner or exhaustive negative UI gate is recommended.

## Actual consumer evidence and accounting

Q read the frozen B reports and raw deterministic provider observations; Q did not operate the browser or take screenshots. Browser AX states/screenshots are in B's CUA transcript; no screenshot file was persisted. The frozen text/step artifact is `../b/browser-consumer-postfix-observations.json`, independently verified SHA-256 `70ed4d8600fd9a83aba511ba594c4c14107b161185705dc0ca8e2b29a3bb0a4a`. Its producer/consumer account is supported by the actual next-stage M4 projections, source and build bindings.

| Scenario | Expected / actual observed result |
|---|---|
| Baseline → add child/needs | Normal production UI/proxy/API/M2/M4/UI path; two adults and Dec10→14 retained, child age5 and explicit access/soft view/budget proposed in review then confirmed. Baseline synthetic CITY-TWN selected; live availability remains unknown. |
| Immediate old selection after confirm | Original v2 FAILED; fresh v3 shows out-of-date badge and disabled old selected action before focus refresh or extra turn. New M4 result is current and reports unsupported access honestly. |
| Clear view | Review `city view → Not set`; applied receipt only “View preferences: Not set.” Call10 M4 projection has no preferred_views and retains adults2, child5, four-night dates, step_free, 15m VND/stay_total/hard and breakfast/taxes. |
| Lower budget | Review only 15m→12m; applied receipt only amount12000000. Call12 projection equals the previous projection except the amount; view remains absent. |
| Separate pending/cancel | New session confirms only baseline v1. Canceling the unconfirmed child/access/view/budget proposal shows “Changes were not saved”; current state stays v1/adults2/children0 with no saved room requirements. This demonstrates that a proposed edit does not become confirmed state. It is not a live-model test of tentative-language understanding. |

Production parser preflight exited zero for **8 parsed outputs = 4 scenarios × 2 production parsers**, not eight pairs. `../b/preflight-evidence.json` and `preflight-command-retry1.log` were inspected. The earlier wrong-Python preflight failure remains historical.

Q checked counts and separate recording constructors: `preflight_b05_payloads.py` creates a provider writing `preflight-provider-observations.json`; the API app writes `provider-observations.json`. There are **8 offline preflight + 15 offline UI = 23 stub invocations** in those separate contexts. UI calls split 4 preserved failing-run + 8 fresh fixed-run + 3 separate cancel-run. Provider-generated request IDs repeat across instances and are not globally unique IDs. The actual UI log SHA-256 is `e4e50f1a6912464f591a97c38beb264d9a3f47deabba66701421687e32c05cc1`; Q verified its fifteen records and binding to the frozen report. **Zero live-model calls**; no model token/billing or actual-property claim.

## Full AC matrix

| AC obligation | Evidence and compatibility | Verdict |
|---|---|---|
| AC1 remove view / lower budget / add member; exact delta and preserve still-valid fields | A22 domain/native/contract tests; Q cardinality recheck as qualified above; final formatter source/B27; actual confirmed add, clear and lower-budget UI sequence; Q's exact call10/call12 retention oracle. Existing child age/guardian preservation plus another child addition is asserted in A's domain case; the actual path separately proves child5 retention through subsequent edits. | PASS |
| AC1 tentative not confirmed | Canonical signed review before mutation, prompt rule, unchanged S9 scope/confirmation semantics, and actual separate unconfirmed/cancel run leaving committed v1 unchanged. No real-model language-quality claim. | PASS within controlled technical scope |
| AC2 same expected version / old patch or output refused | Specific S5 CAS/atomic receipt/in-flight evidence plus S9 signed expected-version confirmation; current source still checks session/brief version and dependent-answer version before commits. New room fields enter the same validated generic mutation transaction. | PASS by precise compatible integrated reuse |
| AC2 retry does not duplicate member/action | S5 same-ID/payload-bound receipt replay, durable generated member identity, answer-only continuation; S9 signed mutation preserves generated IDs. Current receipt/store paths remain field-generic; no S17 change bypasses them. | PASS by precise compatible integrated reuse |
| AC2 affected selection invalidated or clearly pending | Existing S7/S9 server currentness/stale-selection rejection; actual original failure and fresh repaired immediate UI pass; Q helper10/source review. No future response can be treated as matching a different known version; known stale is retained. | PASS |
| AC3 delta from actual applied patch | Typed applied delta feeds the receipt renderer; all13 formatter fields; actual clear-view and amount-only UI receipt; exact producer→M4 projection oracle. | PASS |
| AC3 concurrent/out-of-order old response | Specific S5 concurrency/in-flight/replay proof; `complete_request` still refuses stale dependent completion; monotonic `acceptBrief` refuses older header state; pure derived stale guard reacts to current authoritative version for both result and answer; Q old/current/future/zero checks. | PASS by source, independent checks and compatible integrated reuse |
| AC3 partial failure / continue without unrelated reset | Specific S5 durable partial receipt/lost-ack/same-ID/answer-only resume and S9 confirmation/recovery proof; source retains partial receipt and accepts committed brief before rendering. New helper makes old results stale when a partial commit advances the brief; absent commit/cancel leaves the current version unchanged. Actual session continued through clear and lower-budget without reset. No fresh forced-partial UI run is claimed. | PASS by actual continuation plus precise compatible recovery reuse |

## Reused evidence: exact scope, not blanket parent closure

- **S5** `docs/product/SPRINT_5_ACCEPTANCE.md`, `docs/product/evidence/sprint-5/{review-findings,remediation-review,codex-review}.md`: atomic state/utterance/delta/receipt, one expected-version CAS winner, request/payload-bound replay, no duplicate child, in-flight/completed-answer staleness, post-apply failure, lost acknowledgment and receipt-only continuation. New view/budget/member edits use the same validated JSON mutation and receipt contracts.
- **S7** `docs/product/SPRINT_7_ACCEPTANCE.md`: actual synthetic room result/selection and brief/source currentness. No new M4 algorithm is claimed; no view-fit claim exists. Selection is stale when the supporting brief version changes and cannot be accepted server-side as current.
- **S9** `docs/product/B09_ACCEPTANCE.md`, `docs/product/evidence/b09/independent-final-review.json`: signed canonical mutation review, no commit before confirmation, session/property/purpose/version/expiry binding, generated ID preservation, cancel and replay/recovery. These boundaries apply to the new optional field without a new authority path.
- `inherited-compatibility-source.json`: Q found the full `brief_confirmation.py` module definitions and store `get_guest_brief_receipt`, `complete_request`, `_room_advice_currentness` AST-identical to accepted S9@`876ce4f`. `apply_guest_brief_patch` only adds three post-lock/session-expiry checks; selection adds mapping/expiry checks. Q read the current relevant guards. No S17 edit changes these mechanisms. The old UI confirmation-currentness gap was **not** waived by this reuse; it was independently identified, actually reproduced and repaired above.

No fresh DB concurrency/failure injection or actual-model run was performed by Q. Reuse does not close broader epics/parents or claim entire historical/current candidates identical. The earlier failed S8 module lookup and Q probe expectation error remain disclosed in the previous final report.

## DoD matrix

| DoD | Evidence / result |
|---|---|
| 1 AC expected/observed on fixed versions | Full matrix above; nine source pins checked before/after; frozen harness/fixture/build/UI/provider evidence agrees. PASS. |
| 2 actual UI→API→processor→UI | New ordinary confirmation/selection/edit/cancel sequence runs production build/proxy/API/M2/M4 with controlled provider and private PostgreSQL. Reported actual AX/step observations are bound to exact next-stage processor state and v3 build. PASS at offline integrated level. |
| 3 deterministic independent expectations | Q's v1 cardinality reproduction, v3 ten state-transition expectations and exact retained-field projection oracle; synthetic prices/unknown access preserved. PASS. |
| 4 authority/auth/scope/rendering/atomicity/currentness | New field remains typed/current-turn authorized and signed-confirmed; new strings render as React text; unchanged S5/S7/S9 authority/CAS/idempotency/source/selection guards reused precisely; immediate stale UI fixed. PASS. |
| 5 real-model evidence when AC requires | These generic state AC require no new real-model batch. Controlled provider cases are independently assessed without semantic/live-model claims. Satisfied; no live acceptance invented. |
| 6 relevant local checks | A v2 22 tests, Ruff4, in-memory compile4 and diff PASS; unchanged backend pins retained. B final focused27 (including formatter6), ESLint/typegen/tsc and fourth/final production webpack build PASS. Q inspected final focused/build logs and source, plus own helper10. The earlier builds/expectation failures remain failures, not an all-history PASS claim. PASS. |
| 7 fixed independent review / no acceptance finding | Q17-1 and Q17-2 closed on exact repaired candidates; no remaining actionable finding. PASS. |
| 8 evidence levels / unexecuted checks labeled | Actual controlled-provider integrated app, component probes and inherited integration evidence distinguished. No new model/source/target/participant or fresh forced-negative UI claim. PASS. |
| 9 handoff limits/commands/versions/status | This report, machine verdict, candidate manifests and `../b/T3-FINAL-HANDOFF.md` state pins, limits, commands/logs and remaining delivery ownership. C owns authorized publication/merge and actual Review/Retro. PASS for technical handoff. |
| 10 historical F01 baseline | Not changed or reopened by B05. No additional claim or retrospective gate. |

## Preserved failures, limits and declined-to-judge

The old timebox outcome, earlier Ready NO report, v1 cardinality defect, original v2 UI failure, failed Python/initdb/build operations, exhausted counters and Q's overall KeyError probe remain preserved. One intermediate Ruff raw log was overwritten and a read-only guessed log filename returned ENOENT; neither is hidden or called a product pass. The actual focused log was discovered and read without a source/test change. Product repairs **3/3** and shared harness repairs **3/3 exhausted**; this review grants no further attempts or authority.

Behaviors considered and set aside:

- Real-model tentative-language quality or injection resistance: no new real-model evidence authorized/required; server confirmation enforcement is the accepted controlled scope.
- Real hotel price, availability, view/access fit, provider fulfillment, source approval or participant acceptance: generic researched synthetic fixture has no view facts and no checked access fit; no commercial claim follows.
- New concrete room/itinerary recomputation algorithms: owned by #39/#48; B05 preserves existing M4 and generic edit semantics.
- Deployment, CI result, publication, merge and wider parent/epic completion: not Q actions or claims. No manual CI/rerun or CI-wait gate is introduced.
- New retention/resource policy, framework or exhaustive optional UI negatives: outside demonstrated B05 needs. Existing supported D4 bounds remain unchanged.

Q read B's final handoff reporting owned API/Next/PG stopped, no listeners on private ports and agent browser tabs closed; data, failed/successful sessions and private key preserved. Q did not independently poll processes or DB and does not claim a fresh runtime shutdown check. Q owns no runtime resource.

## Assessment and release

**Ready to merge: YES for B05 full local technical AC1–3/DoD on v3.** Authorized owner-branch publication/merge into the designated integration branch and Sprint Review/Retro remain C's work; they are not claimed complete here. All Q candidate-read/freeze/runtime needs and leases are **RELEASED**. No remaining Q blocker, product edit, runtime action, new sprint plan or additional repair request.
