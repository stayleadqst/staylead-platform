# Sprint 7 — execution report

2026-10-27 (Asia/Ho_Chi_Minh). **In progress: full AC/DoD has not been achieved.**

Hieu requested continued investigation, implementation and verification to remove all blockers and complete Sprint7. [S7-F1 #98](https://github.com/stayleadqst/staylead-platform/issues/98) is in **Sprint7 / P0 / In Progress**; its historical future-sprint deferral is superseded. [C01 #39](https://github.com/stayleadqst/staylead-platform/issues/39), [coordination #97](https://github.com/stayleadqst/staylead-platform/issues/97) remain **Blocked** pending acceptance. **B07 #28 has passed all AC1–3 and is Done independently** within the approved synthetic pilot; code/evidence are included in this publication. C01 and the sprint are not Done.

## Work, ownership and verification

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| M1/M2 preparation and M4 checks/math | A / gpt-6-luna / high | Implemented; atomic per-operation quote protocol | Independent malformed-output/quote/intent checks; guardian/sharing/child separate-bed and unknown-budget-strength regressions | Fixed-candidate actual semantic acceptance remains incomplete |
| Persistence and registered consumer | B / gpt-6-luna / high | Implemented; budget question CAS and localization repaired | FastAPI/PostgreSQL currentness, selection, replay, language and stale-result coverage | 31 PostgreSQL tests PASS; B07 AC1–3 accepted; actual C01 sequences still missing |
| Bounded runtime/browser driver | B / gpt-6-luna / high | Cont6 original9 completed; actual API/browser stopped | Exact parent counters/source/oracle pins; no absent-option selection; truthful nightly-vs-total math; pure booking response handled | Original9 browser PASS; no advice selection/French claim |
| Independent review | Q / gpt-6.1-sol / high | Atomic protocol, consumer and localization repairs independently reviewed | Both native output paths fail closed; repeated derivation does not mutate payload; quotes excluded from canonical M2 | Case8 French FAIL preserved; case9 independently accepted, B07 AC1–3 PASS |
| Integration, gates, backlog and delivery | Coordinator / current session; exact model/effort metadata unavailable | [Draft PR99](https://github.com/stayleadqst/staylead-platform/pull/99), unmerged | Local gates, source-bound evidence and preserved failures/counters | Publish reviewed candidate/evidence; full AC required before Done/merge |

One mutable-file owner at a time. M1–M6 boundaries remain mandatory. Hospitality derives authorization metadata behind the existing neutral platform port; platform does not import domain code. No language parser, fabricated M2 history or extra narrative call was added.

## Actual acceptance and root causes

| Attempt / candidate | Actual observation | Diagnosis / disposition |
| --- | --- | --- |
| Original batch1 / `9a4833b8` | HTTP502 after1turn/1request; no M2 commit | Authorization grammar, omitted guest_edit and inferred max_rooms. Original bad output retained and still rejected |
| Resumed batch2 / `e0557ed0` | City1 HTTP200/2calls: solo,3n,hard6m,Standard5.4m | Browser wrongly compared flat source refs/raw TXT hashes. Correct projected M1 owner/hash/version/generation independently proven; harness repaired |
| Cont1 / `de8afd91` | Exact City1 API replay0calls; City2/3 used4calls; global3/6 | Rejected Family8.7m polluted surviving Standard5.4m budget question; noncanonical `separate beds` rejected valid Twin5.85m. Both repaired offline; failed actual observations remain failures |
| Cont2 / `8055d6b8` | Family4 HTTP200/2calls; global4/8 | Missing-age clarification/no options valid, but explicit guardian/adult sharing/child sleeping requirements lost. False guardian-sharing refusal also ignored by server. Product repaired; browser absent-option crash repaired |
| Cont3 r1 / `3b78e34f` | Bootstrap failed before any new guest/provider request | Driver compared parent run ID to base case-file ID. Void attempt sealed at4/8; identity guard repaired |
| Cont3 r2 / `5ca69c45` | Exact Family4 API replay0calls; case5 first provider attempt failed before output/M2; global5/9 | Native schema contained unsupported `not`; replaced with strict closed `anyOf` variants. Exact CLI exit cause unavailable because ephemeral stderr was discarded; causal attribution to that attempt remains an inference |
| Cont4 / `59362f6c` | Replay0calls; case6 HTTP200/2calls; case7 HTTP502 after preparation; global7/12 | Case6 has correct5.2m subtotal/unknown fees but omitted reconfirmed guardian and budget strength. Case7 duplicate parallel authorization rows and missing adult count fail closed; no Pine brief/history commit |
| Cont5 / `93b38c30` | Amended8 HTTP200/2calls; global8/14 | Correct explicit party/guardian/sharing/dates, LOFT4.4m base and unknown child fee. French labels were valid but discarded after claim filtering, producing English fallback; actual FAIL |
| Cont6 / `b91ea362` | Original9 in fresh session HTTP200/2calls; global9/16 | Booking-only browser PASS: English, trusted destination despite injected URL, safe navigation attributes and truthful external-confirmation/no booking disclosure. Independent B07 AC1–3 PASS |

Repeated serialization failures led to a mechanism change: the native preparation wire now carries `current_turn_quote` inside each typed operation. Hospitality deterministically derives operation index/name/targets and then runs existing quote/current-question/intent/semantic validation. It rejects missing or forged quotes, old parallel/mixed metadata and unauthorized edits. Canonical M2/GuestBriefProposal and platform interfaces remain unchanged. No old failed capture is reclassified as PASS.

The provider schema restriction is documented in [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). That source establishes unsupported syntax, not the discarded CLI stderr of case5.

Child separate-bed intent now has a typed initial value and stable-child setter. Explicit false-sharing refusals persist; separate sleeping surfaces, including known bunk position, are checked without assuming missing policy. Budget amount with unknown hard/target strength stays pending, retains known cost and asks a distinct question; it cannot yield a full-fit/in-budget claim. Domain question priority and persistence localization keys agree.

The actual French failure isolated a post-check presentation defect: M4 correctly removed unsupported candidate claims, then an exact label-set check discarded the entire valid candidate translation bundle. The repair authorizes typed candidate rationale keys and post-M4 derived question keys, projects only onto the checked surviving keys, and requires complete coverage. Missing/extra/forged keys, numeric price changes, invalid placeholders and URIs still fail closed. Q independently rechecked the actual four-candidate→two-checked shape and the derived rate-basis question. This is offline repair evidence; historical actual8 remains failed.

Case8 originally referenced the failed case7 state. The amended, authored case8 explicitly restates current party/guardian/sharing/dates and no hard access requirement in a **fresh Pine session**, requests French, was intended to select a checked option before original9. French validation stopped before selection. Original9 subsequently ran independently in another fresh Pine session. Original8 remains in amendment metadata. The amended attempt and fresh booking are separately classified; they **do not prove original7 access handling,7→8 relaxation/edit or inherited child identity**. Those C01 acceptance gaps remain open.

## Local quality gates

| Gate | Result / evidence limit |
| --- | --- |
| Contracts, architecture and API skeleton | **255 passed**, final product candidate; last bootstrap-only driver/test delta also passed20 focused harness tests and Q actual producer/consumer probe |
| All four relevant PostgreSQL suites | **31 passed**, all four relevant suites on isolated test DB after final domain repair; actual acceptance DB untouched by tests |
| Final localization repair | **61 passed** in test_room_advice; Q captured-output projection, derived-question and negative probes PASS |
| Backend canonical Ruff / compile / diff | **PASS**, canonical apps/api/pyproject.toml; compile, Node syntax and diff checks PASS |
| Frontend contracts/lint/typecheck/build | **40 passed / PASS**, reused because all53 pinned frontend files are unchanged |
| Original production-browser fake-provider journey | Selection/edit/stale409,390px mobile and trusted boundary PASS; this does not establish actual-model semantics |

Earlier source-bound review reports are in [evidence/sprint-7](evidence/sprint-7). Final sanitized [local gates](evidence/sprint-7/cont6-local-gates.json), [source manifest](evidence/sprint-7/candidate-manifest-cont6-v2.json), [French failure](evidence/sprint-7/q-review-cont5-actual.json), [localization repair review](evidence/sprint-7/q-review-cont6-localization-final.json) and [booking browser summary](evidence/sprint-7/cont6-booking-browser-summary.json) accompany this report. Do not sum overlapping reruns as unique tests. Default tests/build/startup remain0liveLLM. Existing Starlette/httpx deprecation warning is recorded. Scratch databases contain fake outputs and are never actual evidence; actual acceptance DB is only inspected with enforced read-only transactions outside the browser run.

## Per-story acceptance

| Story | Implemented / verified | Missing acceptance | State |
| --- | --- | --- | --- |
| #39 C01 | Domain data/checks/math, persisted result/selection/edit/replay, registered UI; City1 actual; offline remediations | Actual repaired City2/3, family4/5/6 and original Pine7→8 including French and current selection; fullAC1–8 | **Blocked** |
| #28 B07 | Actual9 intent/language/injection/trusted boundary PASS; offline safe/missing/contact fallbacks reused; independentAC1–3 PASS | None within approved synthetic pilot; no real booking endpoint/functionality claim | **Done** |
| #97 coordination | Team/contracts/oracle, local gates, independent review, preserved attempts and active remediation | Full goal/AC/DoD and verified delivery | **Blocked** |
| #98 S7-F1 | Existing follow-up pulled into current sprint; protocol and evidenced defects repaired | Fixed-candidate actual semantic acceptance and independent verdict | **In Progress / Sprint7** |

No new follow-up story was added during resumed execution: #98 already covers these related protocol/acceptance blockers with problem, impact, attempts, evidence, AC, epic/priority and affected-story links. No broader parent/epic/milestone is closed.

## Bounds and remaining work

The current human continuation request was interpreted as authorization for one resumed maximum9guestturns/18Codexrequests allocation, not separate numeric approval or authority from backlog creation. Technical continuations preserved all counters and consumed only original unattempted cases. That allocation is now **CLOSED:9/9 guest turns,16/18 provider attempts**. Physical Sprint7 lifetime is **17 attempts** including batch1; failed attempts count. Returned usage totals189767 input/6114 output tokens across16 completed provider responses; the failed attempt's unreported usage, agent tokens and monetary usage are unavailable. [Hashed counter/usage receipt](evidence/sprint-7/resumed-counter-usage-receipt.json).

Cont6 sealed completed9/16, SHA256 `7067736dec93d298942e5ca52a87df36e3f4b1d3ec5b7f4e9ad8a007c1ee92bd`. The two unused request slots cannot authorize another guest turn. No reset, implicit cap increase, automatic retry or Sprint6 allowance reuse. Bounds remain2calls/turn,25s/provider,45s/turn,700output post-usage guard. Every earlier failure/source snapshot/counter is retained.

Q's [minimal reacceptance plan](evidence/sprint-7/q-minimal-reacceptance-plan.json) and [exact proposed cases](evidence/sprint-7/reacceptance-cases-proposed.json) cover **7guestturns/max14requests**, three fresh sessions: City couple→separate-bed edit; family missing age→7→12/budget; Pine hard access→explicit relaxation/child8/French. Only fresh City input restates dates/budget because historical bad City state cannot be rolled back; original family/Pine utterances remain. Reuse City1 solo/math, accepted booking9 and offline matrix. No optional retry turns. This is **PROPOSED / authorized_for_live_calls:false**; no config/state initialized. A new applicable allowance is required before running it. C01/#97/#98 remain open; B07 is independently accepted.

## Delivery state

Own branch `sprint-7-room-advisory`; accepted baseline `a46a63eb4b589b8518f9477ebd66e81d89a0f054`; draft PR99 targets designated `sprint-5-canonical-brief`. Previous published HEAD was `e84a7030d8b2a50b920591461cc984748060caf3`; this update contains resumed fixes, reviewed candidate `b91ea362` and sanitized evidence for publication. Final branch commit receipt is recorded in the PR/backlog delivery update. No fullDone, merge, deployment or real booking claim. Three synthetic hotels/nine room types establish neither real hotel approval nor live availability. Demonstration destinations are nonfunctional examples.

[Independent B07 actual verdict](evidence/sprint-7/q-review-cont6-actual.json) verifies native booking_request+hotel_information/en, exact approved URL, English disclosures and source bindings. Read-only DB confirms no M2/result/selection mutation. No external destination click or real-site functionality is claimed.

Actual API/browser are stopped. Owned web3019 and isolated PostgreSQL55437 remain for authorized verification. Configs/signing secret/raw model captures/screenshots stay local0600; publish only source, authored cases/oracle and sanitized text evidence. No Grok/new paid resources/manual GitHub CI/rerun/workflow/protection changes. Automatic CI may run on publication; no CI PASS is claimed.
