# Sprint 7 — báo cáo nghiệm thu

2026-10-28 (Asia/Ho_Chi_Minh). **Sprint7 đạt đầy đủ AC/DoD trong technical synthetic pilot.** Independent Q chấp nhận C01-AC1–8, B07-AC1–3 và coordination DoD. Không còn functional blocker; tiếp tục publication và merge own [PR99](https://github.com/stayleadqst/staylead-platform/pull/99) vào designated base `sprint-5-canonical-brief`. Trạng thái merge cuối cùng được ghi tại PR và backlog; không deploy.

## Kết quả và ownership

| Work/story | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|
| #39 C01 | B gpt-6-luna/high; Q gpt-6.1-sol/high | All AC1–8 accepted | Actual CityR3/FamilyR2/PineR7 + relevant offline source/state/race/negative guards | None functional; publish/close/merge |
| #28 B07 | B Luna/high; Q Sol/high | Done/closed, retained | Actual synthetic AC1–3/trusted destination/privacy/noreservationpayment | None; no rerun |
| #98 S7-F1 | B Luna/high; Q Sol/high | Blocker work complete in Sprint7 | Typed quotes,clear/UUID/localization/indexing/typed-question-necessity fixes; actual Pine fullchain PASS | No duplicate story/defer; close completed |
| #97 coordination | Coordinator exact model-effort unavailable | Scoped DoD accepted by Q | Ownership,limits,localgates,independentreview,evidence/demo/handoff | Publish/merge authorized ownPR when GitHub permits |

## Final actual Pine chain

[Final Q review and full AC matrix](evidence/sprint-7/q-review-reacceptance7-sol-actual.json) · [Runtime manifest](evidence/sprint-7/candidate-manifest-reacceptance7-sol.json) · [Readiness](evidence/sprint-7/q-review-reacceptance7-sol-final.json) · [Explicit human approval](evidence/sprint-7/reacceptance7-sol-authorization-receipt.json).

Actual candidate **2bf9fd824b4ff4930407d6af5702b4ba1f59758ff6752d1ab54c8ef4127fd4d5**,237pins; product **dd0cc688** unchanged, only3new namespace/receipt controls. Q verified all237 repo/snapshot/source digests before/after; no code changes during actualrun. Exact two original Pine utterances in one fresh session, human-approved Sol/low,max2guest4requests,2calls25s45s700,noautomaticretry/nofallback/firstblockingfailurestop. PriorR6 and every earlier failure/counter remain unchanged; unused old slots closed.

- **Pine1 PASS:** correctadult1/child7/explicitguardian/sharing/dates2n/bothhardaccess,pending[],noinventedhardtype/budget/roomlimit. ONE useful Vietnamese hotel-verification question, no generic restatement or falseaccess/availability claim. ReadonlyDB and all10 source refs current. APIbodySHA24cb10f9b66d6859ff1502501da4155522227ae2ee1e2821c374e7ec55790897.
- **Pine2 PASS:** samechildUUID age7→8, clearONLYtwoaccessneeds, retain guardian/share/dates, M2commit before dependent result. Gardenroom0/queenbed0 covers both once; source-backed occupancy/age/guardian/consent checks pass.2.5mVND/night×2=**5m knownbase**, childfeesunknown, totalnull/partial; no quote/withinbudget/availability guarantee. Three checked French rationales visible/persisted, no fallback/unnecessaryquestion. Current result2/option1 UIselection persisted and GETlatest matches, **0extra provider calls**; previous result stale. APIbodySHAea30fbee2cb5d292f3b44e528e9755753bebc41c143a3d2ee0e6708265c1e2a7.
- Browser completedexit0; both Q/root semantic receipts correct, mobile390px/body390/nooverflow. Enforced readonlyDB confirms correct versions/scope/source/result/selection and no duplicate patch. API stoppedexit143. [Browser summary](evidence/sprint-7/reacceptance7-sol-browser-summary.json).

## AC coverage

| AC | Accepted evidence |
|---|---|
| C01-AC1 context/requirements | City negation/edit; Family stablechild/guardian; Pine samechild/authorizedclear/retainedfields; quote/intent negatives |
| C01-AC2 sources/necessaryquestions | Current scoped sources; Pine specific hotel verification only; typed-state unknown/pending/early-return negatives |
| C01-AC3 room/party checks | Source-backed capacity/bed/share/age/guardian/cot/access checks; no unsafe certified unknown; offline boundary negatives |
| C01-AC4 money/budget | Independent math oracle, City/Family/Pine knownbase; unknown fees/nulltotal/notclaimedinbudget; basis/currency/conflict negatives |
| C01-AC5 compare/select | City STD5.4m/TWN5.85m comparison/current selection; Pine French Garden5m partial/current persistedselection |
| C01-AC6 missing/conflict/availability | Family missingage/budgetstrength; Pine hardaccess unknown and explicitrelaxation; offline conflict/limit; no soldoutclaim |
| C01-AC7 edits/currentness/replay | City staleUI/POST409/newselection; Family agechain; Pine age/clear/currentselection; PostgreSQL replay/source/race/failure guards |
| C01-AC8 actual consumer/language/boundary | Actual web/API/model/domain CityChinese/Family/PineVietnamese→French, select/edit/latest; B07 trusted booking boundary |
| B07-AC1–3 | Prior actual bookingintent/trustedconfiguredHTTPS/language/privacy/safeanchor/referrer/disclosures/noreservationpayment; no-link offline fallback |
| Coordination C-AC1–3 | Recorded team/leases/models/dependencies, candidate-bound evidence, preserved failures/budgets, independent review/fix/demo/handoff |

## Local gates, corrections và limits

Productdd0: **292contracts/architecture/API tests +16isolatedPG PASS**, Ruff/compile/diffPASS; B88roomtests/NodeSyntaxPASS. Runtime R7:23focusedharness/APItests/Ruff/compilePASS; B21focused/NodeSyntax/diffPASS. Known deprecation warnings retained. Frontend53pins unchanged; reuse40tests/lint/typecheck/build. Suites overlap, no invented unique-test total. Default tests use fake providers/0inference.

Necessary fixes completed in #98: per-operation quote/native parity/server validation, stablechild/clear-only edits, guardian/sharing/budget preservation, localizedchecked-label projection, explicit zero-based room+expandedbedindex convention, and typed-state question necessity. Independent review found a related knownaccess/unknownadults early-return edge; it was fixed/tested before final publication. No parser coercion, hidden M2 repair, output reindexing, validator weakening or extra model step. Historical FAIL results are not reclassified.

[Final allocation receipt](evidence/sprint-7/reacceptance7-sol-stop-receipt.json): **COMPLETED2guest/4requests**, stateSHA4665e22612dc04d3532c60cfec98fc280d06fa81b1805008025e9221a36f8da6, Sprint7lifetime**56requests**. [Usage](evidence/sprint-7/reacceptance7-sol-observed-usage.json):51049input/1352outputtokens; eachrequest≤700output/25s, bothturns≤45s; no retry/fallback, selection0calls. Agenttokens/billing unavailable. Allocation closed; no further inference authorized.

Scope remains authored synthetic3hotels/9roomtypes/referenceprices, not realhotelapproval/liveinventory/production readiness. Booking destinations are configured examples; no booking/payment/deploy/Grok/newpaidresources/broaderparent/epic closure. Raw model/API/config/signingsecret/DB/screenshots local0600; public source/authoredcases/sanitized summaries/hashes only. No manualCI/rerun/waitgate/checkbypass; automaticworkflows may run after push, no CI PASS claimed.

## Historical actual failures — retained evidence

### Earlier attempts

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
| Reacceptance1 / `fcdd4a2f` | Approved7/14; City1 HTTP502 after1providerresponse; no M2; global1/1 | Noncontiguous quote correctly rejected; inferred hard king and missing consent also observed. Generic quote/permission/type prompt repair reviewed offline |
| Reacceptance1-cont1 / `390daa4c` | Family3 HTTP200/2calls but missing adult consent; Family4 HTTP502/2calls after age7 M2 commit; global3/5 | Driver missed consent omission and advanced. Answer rejected correct3800000 rendered3,800,000. Guard preserved; actual mixed producer prompt and missing-consent negative repaired; original failures retained |
| Reacceptance1-cont2 / `5c7f04dd` | Pine6 HTTP200/2calls; correct M2 but wrong known-requirement question. Pine7 HTTP502 after1request >700output guard; global5/8 | No age8/access-relax/French commit. Known-vs-pending explanation/CAS fixed offline; compact-delta instruction unverified. No actual failure reclassified |



Repeated serialization failures led to a mechanism change: the native preparation wire now carries `current_turn_quote` inside each typed operation. Hospitality deterministically derives operation index/name/targets and then runs existing quote/current-question/intent/semantic validation. It rejects missing or forged quotes, old parallel/mixed metadata and unauthorized edits. Canonical M2/GuestBriefProposal and platform interfaces remain unchanged. No old failed capture is reclassified as PASS.

The provider schema restriction is documented in [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). That source establishes unsupported syntax, not the discarded CLI stderr of case5.

Child separate-bed intent now has a typed initial value and stable-child setter. Explicit false-sharing refusals persist; separate sleeping surfaces, including known bunk position, are checked without assuming missing policy. Budget amount with unknown hard/target strength stays pending, retains known cost and asks a distinct question; it cannot yield a full-fit/in-budget claim. Domain question priority and persistence localization keys agree.

The actual French failure isolated a post-check presentation defect: M4 correctly removed unsupported candidate claims, then an exact label-set check discarded the entire valid candidate translation bundle. The repair authorizes typed candidate rationale keys and post-M4 derived question keys, projects only onto the checked surviving keys, and requires complete coverage. Missing/extra/forged keys, numeric price changes, invalid placeholders and URIs still fail closed. Q independently rechecked the actual four-candidate→two-checked shape and the derived rate-basis question. This is offline repair evidence; historical actual8 remains failed.

Case8 originally referenced the failed case7 state. The amended, authored case8 explicitly restates current party/guardian/sharing/dates and no hard access requirement in a **fresh Pine session**, requests French, was intended to select a checked option before original9. French validation stopped before selection. Original9 subsequently ran independently in another fresh Pine session. Original8 remains in amendment metadata. The amended attempt and fresh booking are separately classified; they **do not prove original7 access handling,7→8 relaxation/edit or inherited child identity**. Those C01 acceptance gaps remain open.
