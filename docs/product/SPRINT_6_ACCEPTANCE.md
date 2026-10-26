# Sprint 6 — acceptance and execution report

**Chưa Done.** #91/#92/#93/#74 **Blocked** vì shared actual semantic/UI DoD; #95 remediation và #94 coordination **In Progress**. Không ghép các lượt đạt từ candidate/batch khác nhau thành một matrix PASS.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|
| Language / grounding / answer contracts | A — gpt-6-luna/high | Context-bound output536b90d implemented/reviewed; pending-date/source-qualification fix95fcf27 implemented/reviewed | C102contracts/architecture+4PG/API; finaldelta76grounded;Ruff/compile/diffPASS | Actual confirmation on95fcf27;81contracts+4PG/API,37harness+7routingPASS |
| Consumer / bounded harness | B — gpt-6-luna/high | Recovery implemented; drivera059046 reviewed; NS8 paths prepared offline | 35runtime/helper+7routingPASS; latesthelper20/runtime17; reused36web/15state/build/recovery | No NS8 initialize/inference without new allowance |
| Independent review | Q — gpt-6.1-sol/high | NS6/NS7 semantic evidence reviewed; 95fcf27 reviewed; no code finding | Captured-output/guard/Ajv probes, state/copy/source review, readonlyPGT8 | No code finding on536; actualNS7T6/T8 constraints remain failed |
| Integration / delivery | C — root runtime ID/effort unreported | NS7closed18/18; cumulative78; reviewed source95fcf27; publication checkpointfca8672 | Fixed product fingerprint; PG/production browser T1–8 and API diagnosticT9 | Publish code/text; new max18batch requested, pending approval |

## Actual results and accounting

| Batch | Actual requests | Evidence / outcome |
|---|---:|---|
| Original +NS1+NS2+NS3 | 2+4+6+8=20 | Historical failures/counters retained; no reset |
| NS4 |18| UI1–6/API7–9, product changed during diagnosis; not fixed-matrixPASS |
| NS5 |4| T1PASS,T2label-only output rejected; remaining14 transferred once after explicit increment4 |
| NS6 |18| All9state targetsPASS,7answerPASS/2FAIL; UI1–2/API3–9 only |
| NS7 |18| Fixedproduct536b90d/harnessa059046; T6qualificationFAIL,T8state+answerFAIL; T9APIonly |
| **Total** |**78**| Every allowance closed/transferred explicitly; no automatic retry |

NS6 approved increment4+transfer14; NS7 separately approved new18. NS7 is now exhausted and `authorized_for_live_calls:false`; there is no remaining allowance. Existing requests remain immutable. Same `gpt-6-luna/low`,CodexCLI0.153.4,max2calls/HTTPturn,25s/provider,45s/turn,700-token postcheck. Served-model identity,native pre-generation hard cap,total tokens/billing remain unknown. Default tests/build/startup stay offline; no Grok or judge/translation calls.

## Namespace7 — fixed-product observed results

[Manifest](evidence/sprint-6/remediation/namespace7-candidate-manifest.json), [independent semantic review](evidence/sprint-6/remediation/namespace7-semantic-review.json), [UI observations](evidence/sprint-6/remediation/remediation-7-live-run/observations.jsonl), [closed counters](evidence/sprint-6/remediation/namespace7-run-state-closed.json), [runtime events](evidence/sprint-6/remediation/namespace7-runtime-events.jsonl). Product SHA256 `27e0806342f3cfda2cc5e1862f971bcb0a543b891e7280a4eb93ab9acaa06589` stayed unchanged during all18calls.

| Turn | Expected / observed | Verdict |
|---|---|---|
|1VI|ISO10→13Dec2026,nights3,adults2; breakfastBếnGió/floor1/06:30–09:30+sourceTZ040;current/exactcopy|PASS|
|2EN|Onechildageunknown/pending, same dates/adults; targeted age question;brief2/rev2,current/exactcopy|PASS|
|3FR|Samechildage7,checkout14/nights4;brief3/rev3,current/exactcopy|PASS|
|4JA|Contextualbreakfast040/location/floor/time/TZ;briefunchanged,current/exactcopy|PASS|
|5ZH|Freeguest-areaWiFi/deskcredentials021;briefunchanged,current/exactcopy|PASS|
|6AR|40spaces/100000VNDpervehicle/night/noadvancebooking046;exactURLowncitation;RTL/current/exactcopy. URL label contextualizes it without required synthetic/nonfunctional sample qualification|Narrow answer constraintFAIL; state/corefacts/copyPASS|
|7HI|Asks12or13December2026;keepscheckout14,child7,pendingcheckout;brief4/rev7,current/exactcopy|PASS|
|8KO|Expectedcheckout15/nights5/pendingclear. Preparation incorrectly emitsclarify against oldpending14; final15claim citescheckin,guard correctlyrejectsHTTP502. KOrev8persists,brief4/checkout14/pendingremain|State+answerFAIL|
|9short/mixed|API200Koreancourtesy,KOrev8unchanged; preserves actualbrief4/checkout14/pending. Does not repair inheritedT8failure;noUIcopy|Courtesy/observedstatepreservationPASS; globalexpectedbrief5unmet|

[Read-only PG T8 proof](evidence/sprint-6/remediation/namespace7-turn8-db-observation.json), [T9 diagnostic](evidence/sprint-6/remediation/namespace7-diagnostic-api-turn-09.json), [per-case baseline comparison](evidence/sprint-6/remediation/namespace7-case-comparison.json). No answer-only retry was used; it would not repair the unapplied date mutation. Browser/API/web stopped; sharedPG retained. Maxprovider12.970s/maxHTTP18.421s/maxreportedoutput409tokens. Browser external origin count0 covers browser context only, not server/provider network.

## Corrections and retained evidence

- Native output schema on e9424bc stopped label-only/empty content; NS6 proved actual adapter completion, but structure alone does not ensure semantic correctness.
- Context-bound536b90d restricts claim/declaration refs to authoritative nonnull/nonpending fields; runtime rejects nonnullpending refs too. Pendingage requires questionchannel; current pendingcheckout slashpair requires nonnull typedclarification in everybranch. Existing exactoptions/order/numeric/source/URLguards remain. Qclosed all concrete code findings beforeNS7.
- NS6T2 null-age cite/omitted agequestion and T7translatedoptions rejected correctly. Nonnullpendingref acceptance was a separate offline-found gap, not the observed T7 rejection cause. [NS6review](evidence/sprint-6/remediation/namespace6-semantic-review.json), [case comparison](evidence/sprint-6/remediation/namespace6-case-comparison.json), [finalDB](evidence/sprint-6/remediation/namespace6-final-db-observation.json), [local gates](evidence/sprint-6/remediation/context-bound-output-local-gates.json).
- Driver reports `driver_checks_passed` separately; `matrix_pass` remains pending semanticreview/false on knownfailure. Explicit `next` requires unique same-turn persisted receipt fingerprint; genericT8error had no receipt so driver stopped. API diagnostic is labeled separately.

## Latest reviewed correction —95fcf27

[Candidate manifest](evidence/sprint-6/remediation/pending-resolution-candidate-manifest.json), [gates](evidence/sprint-6/remediation/pending-resolution-local-gates.json). Preparation now treats a stored pending date endpoint as unresolved: explicit unambiguous current-turn date replaces it via set_dates rather than conflicting with the placeholder. Other pending field operations stay unchanged. Final answer preserves cited source synthetic/nonfunctional URL qualification in requested language. No final guard relaxation, fixture hardcode or extra model call. A81contracts+4PG/API; C77grounded+7finalscope+37harness+7routing;Q2changedprompt+2mappingtests,Ruff/compile/diffPASS. Maximum final instructions2970with64chartag. Actual semantics pending new explicitly approved batch; no codefinding remains.

## AC map / remaining work

| AC group | Established evidence | Missing before Done |
|---|---|---|
|L1-AC1–5|Preference scope/CAS/restart/replay/late-response regressions; actual language revisions and samechild continuity|Fixed-candidate complete mutation/answer/UI sequence afterT8fix|
|L2-AC1–4|Source/numeric/URL/injection/revocation/conflict negatives; lexical baseline and per-case semantic/latency/call comparison|URLqualification and final complete semanticverdict|
|L3-AC1–4 / B12a-AC1–4|Productionbuild/layout/RTL/CJK/Devanagari/races/clipboardfailure+fallback;actualT1–7exactcopy|Full actual9turnUI/copy matrix|
|R1-AC1–5 / C-AC1–3|Capturedfailures, diagnostics/privacy, boundedfix/review, owners/counters/versionedmanifest|Finalreview,completeACmapanddelivery|

Existing #95 already has problem,impact,attempts,evidence,AC,epicE2,priorityP0 and affectedlinks #91/#92/#93/#74/#94. Current defects remain in this remediation story; **no duplicate new story added**. Engineering fixes continue in currentSprint under standardized Sprint-Execution. Do not close originalparents/epic/milestone.

## Delivery / privacy

Publication checkpoint before branch update: previous head `fca86724c4446d82974d939fb17792dda2177a13`. Latest reviewed source local95fcf27 maps to GitHub source object `e461efd19ba035ee6d628537254fa0e5d32d3f27`; text evidence commit follows. Final branch-head/equal-tree receipt is recorded outside Git and in PR96. PR96draft stays on `sprint-5-canonical-brief`, unmerged; not deployed. No manualCI/rerun or waitinggate; automatic workflows may run on branchupdate, noCIPASSclaimed.

Hieu explicitly chose local-only screenshots after automatic review rejected public image upload. [Local screenshot hash index](evidence/sprint-6/remediation/local-screenshot-index.json) contains text only;27screenshots remainlocal. No raw provider captures,privateconfigs,tokens,secrets or imagebytes may enter publictree/history. No deploy/newpaidresources/oldrepochanges/baselineormainmerge.
