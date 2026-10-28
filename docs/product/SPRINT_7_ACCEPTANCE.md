# Sprint 7 — báo cáo thực thi

2026-10-28 (Asia/Ho_Chi_Minh). **Sprint7 chưa hoàn tất. B07 #28 Done; C01 #39, điều phối #97 và S7-F1 #98 Blocked.** [PR99](https://github.com/stayleadqst/staylead-platform/pull/99) Draft/unmerged, base `sprint-5-canonical-brief`.

## Kết quả hiện hành

Batch Sol/low R6 được duyệt max2guest/4requests đã **dừng tại1lượt/2requests** do lỗi AC2 ở lượt đầu; tổng Sprint7 **52runtime provider requests**. Unused1guest/2requests đóng; không marker01/turn2/retry/reset/reallocation/history repair. API đã dừng exit143; browser dừng exit137 sau SIGTERM không kết thúc.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|
| B07 #28 | Q / gpt-6.1-sol/high | Done/closed | Actual technical synthetic pilot AC1–3 | Giữ Done; không claim real booking endpoint hoạt động |
| City Chinese→sửa giường | Q / gpt-6.1-sol/high | R3 actual PASS | Comparison,6.5m budget,separate singles,staleUI/409/newselection0extraLLM | Reuse |
| Family thiếu tuổi→7→12/budget | Q / gpt-6.1-sol/high | R2 actual PASS | Stablechild/guardian/consent/date,5.2m/7.6m base,feesunknown/nulltotal | Reuse |
| Pine full chain | Q / gpt-6.1-sol/high | R6 Pine1 AC2FAIL; Pine2 not attempted | Correct M2/known access verification, but extra generic question asks saved requirements again | Actual fullchain/French/options/currentselection still missing |
| Typed question necessity | B / gpt-6-luna/high | Implemented/frozendd0cc688 | Remove unsupported broad model hint from typed known/nonpending state; preserve real missing/pending/conflict/rate questions | Q scoped PASS; publish concrete bounded actual proposal |
| Integration/delivery | Coordinator / exact model-effort unavailable | Own branch/PR99 | Local292backend16PG, prior frontend40 reused | Full AC/DoD before Done/merge |

## Actual R6 failure và nguyên nhân

Hieu explicitly approved “Cho phép batch mới Sol/low 2/4” on reviewed product327ea219/PR99commit5085de0. Exact original two Pine utterances/one fresh session, Sol/low,2calls/turn,25s/provider,45s/turn,700output,noautomaticretry/nofallback,stopfirstblockingfailure. Source of authority is direct human reply, not attached guides/backlog.

Actual candidate **a7b93fae598973c0911e75ed438797c4b0b42544ee5dd7f5ec4206ca17f4d04f**,237pins, only3controls delta from327. [Manifest](evidence/sprint-7/candidate-manifest-reacceptance6-sol.json) · [Readiness](evidence/sprint-7/q-review-reacceptance6-sol-final.json) · [Authorization](evidence/sprint-7/reacceptance6-sol-authorization-receipt.json). Prior actual R5bootstrap2 sealed2/4/lifetime50/stateSHA9441449d remains unchanged; bootstrap1zero was not used as predecessor.

Pine1 HTTP200/bodySHA **a2b293fe1b610c4c7562f362162a1511d1bdc3df3dde40c4909a0f06e6903d24** saved correctadult1/child7/explicitguardian/sharing/dates2n/bothhardaccess,pending[]. UI correctly asks hotel to verify known accessibility needs, but also asks **“Tôi nên áp dụng yêu cầu phòng nào?”** despite complete relevant saved requirements. Q confirms strict **C01-AC2 FAIL**: the generic question has no missing consequential guest information behind it. No false fit/availability/math claim was released.

Cause: M4 copied every canonical model question, then no-option branch forwarded broad `room_advice` without checking typed-state necessity. This differs from the old pending-marker bug; known-access marker and verification now work, but the extra question remains unjustified. Q enforced readonly DB confirms brief/state1,one completedrequest/result,2messages,noselection,all10source owner/version/hash/generation refs current. Actual failure/state/capture remain preserved. [Actual review and AC matrix](evidence/sprint-7/q-review-reacceptance6-sol-actual.json).

Root withheld marker01 and stopped before original turn2. State sealedHALTED1/2 SHA **4a238a18eb8a8b1e904f8e3b5188fb06a1974128d3a85e7121651b00b59c5b27**, lifetime52. [Stop receipt](evidence/sprint-7/reacceptance6-sol-stop-receipt.json).

## Offline consumer fix và quality gates

Candidate **dd0cc68883904259776be49d21bb961146a393f39150edc76823e01388719bab**,237pins, exact3delta fromactuala7: M4consumer, room-advice tests and browser. With saved nonpending hardaccess and no pending room field, discard only unsupported model broad `room_advice` hints, independent of pair/order. With no options and only that hint, surface the existing known-needs hotel-verification step. Preserve specific questions, actual pending-room questions and server-derived conflict/rate questions. No NLparser/alias/M2repair/output-reindex/constraint-validator weakening or extra model call.

Browser original Pine1 now requires only the useful specific verification question. Tests cover broad-only, reordered/pair/additional-specific layouts, actual missingchildageNone/pendingage preservation, absent/pending/wholeobject/otherroompending, conflict/rate paths. Original two-question capture gives the correct single verification question offline; actual R6 remains FAIL.

[Manifest](evidence/sprint-7/candidate-manifest-reacceptance6-sol-question-remediation-final.json) · [Gates](evidence/sprint-7/reacceptance6-sol-question-remediation-final-local-gates.json): **292 contracts/architecture/API PASS,16isolatedPG PASS**, Ruff/compile/diffPASS; builder88roomtests/NodeSyntaxPASS. Final corrected missing-child fixture3targeted casesPASS. Existing warnings:3backend/1PG deprecations. Frontend53pins unchanged; reuse40tests/lint/typecheck/build. Suites overlap; no invented unique-test total. [Independent fix review](evidence/sprint-7/q-review-reacceptance6-sol-question-remediation-final.json): **scoped PASS**, including reported early-return edge, all237 pins and emitted-browser positive/negative proofs.

Independent review found an early-return regression in initial96a: known access could be rendered generic when adults were unknown. Final fix defers new verification derivation until after party/cap earlyreturns and carries trusted known-access metadata for existing specific questions through both earlyreturns. Missing-adults question and processing-limit status remain intact; positive/negative regressions pass. [Initial finding](evidence/sprint-7/q-review-reacceptance6-sol-question-remediation-initial.json).

Prior explicit zero-based room/bed guidance remains in the candidate. R5 actual one-based room/bed proposal still rejected; corrected COPY gives FrenchGarden5m base/unknownchildfees/nulltotal offline. R6turn2 was not attempted, so actual adherence to the indexing fix remains unverified.

## Backlog / next action

| Story | Đã kiểm chứng | Còn thiếu | State |
|---|---|---|---|
| #28 B07 | Actual technical pilot AC1–3 | None in scope | Done/closed |
| #39 C01 | City/Family; prior Pine correct M2 edits; offline source/math/currentness guards | Fixed actual Pine clarification→age8/clearboth/French/options/currentselection; full AC1–8 | Blocked |
| #98 S7-F1 | Roots/attempts/evidence and necessary fixes executed in Sprint7 | Actual fixed Pine fullchain acceptance | Blocked / Sprint7 / P0 |
| #97 coordination | Team/ownership/bounds/gates | Full AC/DoD/verified delivery | Blocked |

Existing#98 covers problem/impact/attempts/evidence/AC/epicE3/P0/affected#39/#97; no duplicate story or broaderparent/epic closure. [Concrete fresh Pine proposal](evidence/sprint-7/reacceptance7-sol-cases-proposed.json): NEW max2guest4requests, exacttwooriginalcases/onefreshsession, sameSol/low2calls25s45s700/noautoretry/nofallback/firstblockingstop, reuseCity/Family/B07. **No NEW allowance approved, no new config/state/init/inference.** R6 unused1/2closed, cannot reuse or transfer.

## Usage / delivery limits

[Observed R6 usage](evidence/sprint-7/reacceptance6-sol-observed-usage.json):2successful adapter responses,25051input/489outputtokens(449+40),9.25s/5.10s provider latency,14.53s HTTPturn; no retry/fallback. Lifetime52; agenttokens/billing unavailable.

Ownbranch `sprint-7-room-advisory`, acceptedbaselinea46a63e, publishedHEAD before this recovery5085de0. Raw model/API/config/signingsecret/DB/screenshots local0600; publish source/authoredcases/sanitized summaries/hashes only. Synthetic3hotels/9roomtypes/referenceprices do not prove realhotelapproval/liveavailability/booking. No manualCI/rerun/waitgate/checkbypass/Grok/deploy/newpaidresources/main/otherPRmerge/broaderclosure. Automatic CI may run after push; no CI PASS claimed.

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
