# Sprint 7 — execution report

2026-10-27 (Asia/Saigon). **Sprint7 is not complete. B07 #28 is Done; C01 #39, coordination #97 and S7-F1 #98 remain Blocked.** Existing #98 stays Sprint7/P0; no duplicate story or broader epic closure. [Draft PR99](https://github.com/stayleadqst/staylead-platform/pull/99) targets `sprint-5-canonical-brief` and remains unmerged.

## Current outcome

The NEW approved manual allocation7guest/14requests stopped at **6guest/11requests**. City1 and Family3–5 passed independent actual review; City2 and Pine6 failed; Pine7 was not attempted because Pine6 never committed its required brief. The allocation is halted and unused1guest/3requests closed, with no retry/reset/reallocation. Sprint7 lifetime is36provider attempts. Actual API/browser runners are stopped.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| City bed edit | B / gpt-6-luna/high | Explicit exact-bed-type versus separate-surface guidance implemented | Prior actual City1 Chinese/currentselection PASS; City2 invented hardtwin caused correct M4 rejection of single beds; exact offline counterfactual passes without invented type | Guidance is offline remediation; actual City1→2/stale selection still required |
| Family unknownage→7→12/budget | Q / gpt-6.1-sol/high | Actual cases3–5 PASS | Stablechild/guardian/consent/separatebed/dates; known5.2m then7.6m base; unknown fees/nulltotal and budgetstrength clarification; current source/state/version/UI proof | Accepted evidence reused; do not repeat this chain |
| Pine hardaccess→relaxation/French | B / gpt-6-luna/high | Native contextual ID schema and known model-validation error boundary implemented | Existing childUUID positives/invented child-1 negatives; both native producers use trusted snapshot; FastAPI+isolatedPG confirms502/no brief or receipt mutation | Prior actual Pine6 remains FAIL; Pine7 dependencyBlocked. New actual chain required |
| Independent review | Q / gpt-6.1-sol/high | Final scoped offline PASS on d7ca88db (237pins) | Actual failures preserved; strict canonical/M4/quote/source guards unchanged; neutral platform boundaries | Actual City/Pine acceptance remains required |
| Local gates/delivery | Coordinator / exact model/effort metadata unavailable | Offline candidate d7ca88db; publication pending | 277backend+15PG PASS; Ruff/compile/diff PASS; unchanged53frontendpins reuse40tests/lint/typecheck/build; unchangedNode controls reuse | Publish reviewed source/evidence; no Done/merge before full actualAC |

Pine6 native preparation emitted an invented `child-1` in `set_bed_sharing` after adding a new child. The canonical validator correctly rejected it, but its ValueError escaped to genericHTTP500. The fix binds native sharing IDs to canonical adult1..30 (existing SetAdults bound) plus childUUIDs already in the trusted snapshot; new-child consent goes inline in `add_child`. Both FactSelection and grounded-preparation paths pass the neutral snapshot through registered domain schema factories. The strict final validator remains necessary for canonical validity. Only its known pre-mutation ValueError is mapped to502 invalid_model_output; programming/storage errors are not broadly masked.

The failed actual Pine6 has **no M2 brief/sourceutterance/receipt/messages/result/selection, but one valid inferred-language preference row persisted**. It is incorrect to claim no state changed. No actual history was repaired. Offline tests/fake-provider checks are not real-model acceptance.

## Latest actual evidence

| Original turn | Actual verdict | Evidence / implication |
| --- | --- | --- |
| City1 | PASS | Chinese couple/explicitsharing/no inferredmaxrooms; STD5.4m knownbase/current exactversionselection at0provider. One option allowed; no multioption ranking claim |
| City2 | FAIL | Correct sharingfalse plus invented hardtwin; proposed distinctsinglebeds rejected by correct M4guard. Removing only unsupported hardtype in offline copy yieldsTWN5.85m; original badM2/result unchanged |
| Family3 | PASS | Unknown childage usefulclarification; explicitguardian/adultconsent/childseparatebed/dates preserved; no unsupported fullfit |
| Family4 | PASS | Samechild age7; GDN2.6m×2=5.2m knownbase, childfeesunknown/nulltotal; actual mixedFAQ exactnumeric/source checks pass |
| Family5 | PASS | Samechild age12/minor/guardian/separatebed; one-room/6mwholemandatory budget saved, hard-v-target strengthunknown asks clarification; FAM7.6m knownbase not claimedwithin6m, extraadultfeesunknown |
| Pine6 | FAIL | Invented child-1 passes shape parsing but canonical guard rejects; HTTP500 after firstcall, no call2. Language preference row persists separately |
| Pine7 | Blocked / not attempted | Same-child/date/access-relaxation/French depends on missing Pine6M2; no amended input or fabricatedhistory |

[Actual City review](evidence/sprint-7/q-review-reacceptance2-actual.json), [Family/Pine review and full AC matrix](evidence/sprint-7/q-review-reacceptance2-cont1-actual.json), [sealed counter receipt](evidence/sprint-7/reacceptance2-cont1-stop-receipt.json). StateSHA `9a7b3777fded731ab57292b2c315dac06fd757ba5f875b44e8a2d6568a5362c5`. Earlier City stop at2/4 remains immutable; technical continuation was seeded2/4 under the same7/14 allowance, not a new budget.

## Quality gates and review limits

[Offline candidate manifest](evidence/sprint-7/candidate-manifest-reacceptance2-final-mechanism.json): `d7ca88db6c1251a7dc9ff64acdf9d6624731b5865a46d322f28f55dde3b5e35a`,237pins. [Local gates](evidence/sprint-7/reacceptance2-final-mechanism-local-gates.json):277contracts/architecture/API PASS (3existingwarnings),15isolatedPostgreSQL PASS (1existingwarning), Ruff/compile/diff PASS. Native contextual schema tests cover both producer paths, savedUUID and new-child inline consent; fakeprovider FastAPI regression proves typed502 and unchanged brief/receipt. Contextual native schema is intentionally more restrictive than static parsing; identical constraints are not claimed.

Frontend53pins unchanged: reuse40tests/lint/typecheck/build. Controls unchanged from4797d219: reuse Node syntax/smoke. Do not sum overlapping runs as unique tests. Default tests/startup make0liveLLM calls; isolated `staylead_sprint7` uses fakes and does not write the acceptance database. Q actual inspection enforces read-only transactions. Raw captures/config/secrets/DBdumps/screenshots stay local0600; publish curated summaries and authored inputs only.

[Final independent review](evidence/sprint-7/q-review-reacceptance2-final-mechanism.json) confirms all237 repository/snapshot pins,8 focused native/static/producer tests, exact original failure rejection, supported inline consent, narrow502 boundary and unchanged M1–M6 boundaries. The proposed4 cases exactly match previous1,2,6,7; Family/B07 need no repeat. This is offline PASS, not actual semantic acceptance.

## Per-story acceptance and remaining actions

| Story | Verified scope | Missing acceptance | State / owner |
| --- | --- | --- | --- |
| #28 B07 | Prior actual booking intent/trusted boundary/language and independentAC1–3 syntheticpilot PASS | None in approved scope; no real booking endpoint claim | Done / retained |
| #39 C01 | City1 and Family3–5 actualPASS; localM4/math/ID/source/state/UI guards | Actual corrected Citybededit/stale/reselection; Pinehardaccess→age8/explicitrelax/French/currentselection; fullAC1–8 | Blocked / B + Q |
| #98 S7-F1 | Bounded diagnosed fixes implemented and locally verified | Actual remainingchains | Blocked / Sprint7/P0 / B + Q |
| #97 coordination | Team/gates/actual evidence/counters maintained | FullactualAC/DoD and verified delivery | Blocked / Coordinator |

Existing #98 records problem/impact/attempts/evidence/AC/epicE3/priorityP0/affected#39 and#97; no new story duplicates it. It remains in the current sprint rather than being silently deferred. Broader parents/epics stay open.

## Proposed remaining manual acceptance — not authorized

[Reacceptance3 proposal](evidence/sprint-7/reacceptance3-cases-proposed.json) contains **4 unchanged original utterances**, freshCity1→2 plus freshPine6→7, maximum4guest/8requests, gpt-6-luna/low,2calls/turn,25sprovider/45sturn/700output,noautomaticretry/stopfirstblockingfailure. Family3–5 and B07 accepted evidence reused. It is `authorized_for_live_calls:false`; no new config/state/API/model run exists. Need an explicit new manual allowance after concrete reviewed publication; old7/14 approval is not requested again or reused. Current continued execution authorizes offline repair and delivery, not silently raising that exact model budget.

After authorized actual runs, Q verifies fullAC1–8; only then may #39/#97/#98 becomeDone and ownPR99 be merged under existing authority when GitHub permits. No manualCI/rerun, checkbypass, deployment, newpaidresources, Grok or broaderclosure. AutomaticCI may run after branch publication; no CI PASS claim or waiting gate.

## Observed usage and delivery

[Reacceptance2 observed usage](evidence/sprint-7/reacceptance2-observed-usage.json): all11adapterresponses report140042input/3363outputtokens, including semantic failures. Lifetime36requests includes25before this allocation. Agenttokens and monetarybilling unavailable; this is observed adapter usage, not a billing guarantee.

Ownbranch `sprint-7-room-advisory`, accepted baseline `a46a63eb4b589b8518f9477ebd66e81d89a0f054`. Last publishedHEAD before this remediation was `dd5169cb319d92f27c82635ecac45b28d3fbfd4c`; new exact publication recorded in PR/backlog/delivery receipt after finalreview. DraftPR99 remains unmerged. Three synthetic hotels/nine roomtypes establish neither realhotel approval nor liveavailability. Demonstration booking destinations remain examples.

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
