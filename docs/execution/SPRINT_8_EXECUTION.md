# Sprint 8 execution checkpoint

Started 2026-10-28 under Hieu's direct execution request. That request authorizes core #100–#102 code, synthetic fixtures, local validation, GitHub updates, commit/push/PR/merge after applicable review. Planning-only text in issues is historical evidence. Sprint-Execution.md does not authorize additional scope, infrastructure changes or inference. R0/R1/R2 rules remain revoked.

## Baseline and delivery

- Initial checkout `sprint-7-room-advisory@d8b2ec160577e98da053a70a373254a0e4fcf2c8`, clean.
- GitHub PR #99 verified merged at `12122f7d012c0617670438de5419efdc3d7729ab` into `sprint-5-canonical-brief`; accepted product tree identical. Sprint 7 remains complete.
- Remote heads inspected; no Sprint 8 branch or PR existed. New owner branch `sprint-8-guide-shortlist` starts at that merge; intended PR base remains `sprint-5-canonical-brief`. Existing PRs #89 and #83 are outside this delivery.
- No inference, deployment, manual CI, credentials change or shared infrastructure mutation authorized. Tests/build/startup use disabled/fake providers by default. Prior Sprint 7 allowances are closed.

## C1 / T0 contracts and leases

| Work / deliverable | Owner — model / effort | Scope and exclusions | Dependencies / parallel start | Acceptance evidence |
|---|---|---|---|---|
| Contracts, leases, integration, verification, publication | C — current session / exact runtime model and effort unavailable | This checkpoint, evidence, local runtime and GitHub; no production or live inference | Before dependent editing | Baseline refs; pinned candidate and matrix |
| Typed guide, M1 adapter, domain shortlist, M2 patch and M3 injection | A — gpt-6-luna / high | Hospitality schemas/prompts/tools/policy/fixtures/tests; neutral contract and generic orchestrator seam; new local-guide adapters | T0 approved; publish exact callable signatures before consumer-dependent edits | G1–G3, L1–L3; producer tests |
| Dev identity, protected operator consumer, guest composition and M6 | B — gpt-6-luna / high | Auth/entrypoints/settings/composition/web/tests; no domain business rules | Auth and UI may start alongside A; actual integration depends on A interfaces | G4, L4; direct API pre-read denials and integration |
| Independent review and acceptance | Q — fresh gpt-6.1-sol / high | Read-only candidate; independent expected outcomes and findings | Only after reviewable pinned candidate | G/L/C AC mapping; no candidate edits |

Maximum four concurrent agents including C. A/B first completed read-only seam inspection, then received these leases before editing. No reporting-only agent. Runtime token usage/retries unavailable unless supplied by runtime; no savings claim.

A leases `domains/hospitality` schema/policy/recommendation/prompt/tool/registration files required by the two stories; `platform/contracts/local_guide.py`; `platform/conversation/orchestrator/grounded_qa.py`; new `infrastructure/source_connectors/local_guide.py` and `infrastructure/persistence/local_guide_repository.py`; `fixtures/hospitality/sprint8-local-guide-v1`; new domain tests. B leases `entrypoints/app.py` and operator router; `composition/dependencies/{operator_guide,guest_chat}.py`; configuration settings; `infrastructure/identity/operator.py`; web files and corresponding consumer tests. Existing `persistence/store.py` is reserved to B only upon a concrete shared-contract handoff. C owns this execution document and sprint evidence. Any additional shared file requires an explicit lease transfer.

M1 uses existing source/fact lifecycle tables and scoped read ports; no parallel guest knowledge store. Hospitality owns typed record validation, projection, feasibility and fit. Platform contracts remain domain-neutral and never import Hospitality. B composes domain adapters and passes only server-derived scope. M2 commits validated confirmed preference patches before dependent shortlist computation. M3 uses the existing bounded conversation; M6 renders registered domain results. No room selection, full profile, dates or itinerary prerequisite.

## Synthetic records and preliminary expected outcomes

Single property `HTL-S8-DEMO`, slug `lotus-pilot-demo`; synthetic checked date 2026-10-28, ordinary validity through 2027-03-31. Every source, approval and date is explicitly synthetic technical-demo evidence, never real hotel approval.

| Stable ID | Record and facts |
|---|---|
| DIN-01 | Lotus Noodle; quiet; 100000 VND/person; access supported; allergy unknown |
| DIN-02 | River Table; sponsored; social/culture; 300000 VND/person; conflicting hours require verification |
| DIN-03 | Night Grill; known closed |
| ATT-01 | Craft Museum; culture/indoor; 90 minutes; 120000 VND/person; access supported; child safety unknown |
| ATT-02 | Riverside Garden; nature/quiet; 45 minutes; 0 VND; hours and access unknown |
| ATT-03 | Old Fort; expired 2026-10-01 |
| TR-01 | 3 seats excluding driver; luggage 2; child-seat/access/availability unknown |
| TR-02 | 6 seats excluding driver; luggage unknown; child-seat supported; access unsupported; availability unknown |
| LEG-01 | Hotel → DIN-01; walk; 10 minutes |
| LEG-02 | DIN-01 → hotel; walk; 12 minutes |
| LEG-03 | Hotel → ATT-01; taxi; 15 minutes |
| LEG-04 | ATT-02 → hotel; taxi; 20 minutes |

No reverse routes, capacities, hours, suitability or availability inferred. Source IDs/version/hash/currentness and actual field evidence must be materialized by A, not inferred from this table. Missing values stay unknown; conflicts stay explicit. Source instructions cannot grant permissions.

Preliminary offline oracle A (quiet/budget) favors DIN-01 and ATT-02 with missing hours/access/route tradeoffs. Oracle B (culture/social) favors DIN-02 and ATT-01 with sponsor disclosure, price and unresolved hours tradeoffs. Closed DIN-03 and expired ATT-03 cannot be final available recommendations. Hard allergy, child safety or access requires positive supporting evidence; unknown cannot certify suitability. Q independently pins expected fits/tradeoffs against the actual catalog before live acceptance. Oracles remain outside serving/model context.

Supported pilot fixture size: exactly 6 venues, 2 providers, 4 directional legs. Existing M1/runtime payload and fact limits remain in effect; bounded operator request size and exact field limits are enforced by implementation. No cap increase or extra automatic inference call is authorized.

Dev principal `local-operator-s8` binds server-side to `HTL-S8-DEMO` with guide read/write permissions. Opaque secret is local server configuration outside git, with constant-time matching; no public/default credential. Dev/test targets only. The requested property is compared with the authenticated principal before any guide read/service call. Missing, guest, unauthorized and wrong-property requests fail directly at the API, even bypassing UI. This is not production OIDC/F03 completion.

## Reused dependency evidence

- #16/#18/#35/#36: Sprint 3 report and independent pack/consumer evidence establish typed source import, property scope, guest approval and actual M1 consumers. Sprint 4 report establishes refresh/delete/revoke, expiry, generation/CAS, saved-answer/history invalidation and source-bound media. These are inherited capabilities; Sprint 8 still verifies its new guide producer and consumer against them.
- #21/#26: Sprint 5 actual canonical-brief/receipt/edit consumer, Sprint 6 actual multilingual/language/currentness acceptance, and Sprint 7 full scoped C01 acceptance establish M2/M3/M6 state/edit/source seams. Reuse valid evidence for unchanged paths; verify changed shortlist paths and affected regressions locally.
- Evidence: `docs/product/SPRINT_{3,4,5,6,7}_ACCEPTANCE.md` and linked candidate-bound independent reports. Folders and empty operator stubs are not capability evidence. No broader parent/epic is closed by this refinement.

## Remaining acceptance and authority

Implement → focused local tests → integrated vertical slice → relevant lint/compile/build/PG gates → pinned candidate → fresh Q review/fixes → offline operator demo. Actual guest web → API → model → domain → UI remains unverified until a separately authorized batch.

Pending proposal only: four guest turns / at most eight requests, gpt-6.1-sol/low, at most two calls per turn, 25 seconds/call, 45 seconds/turn, 700 output tokens, no auto retry/fallback, stop first blocking failure. Chinese fresh brief A; French fresh brief B on same catalog; third session mixed/RTL hard suitability unknown then clarification/edit/language change. Observe mobile/RTL within those turns. Request authorization only with exact candidate/config/data/prompt pins and matrix/input/expected after local gates and independent review. No batch state initialized and no live inference performed.

Stories remain In Progress until complete AC/DoD; implemented, verified, pushed, merged and deployed are reported separately. Estimate 15–27 active agent-hours remains uncalibrated; re-estimate after first integrated slice if evidence warrants it.

## First integration checkpoint

C executed actual FastAPI operator routes → connector → existing PostgreSQL M1 → guest repository on an isolated local database with AI disabled. Import left zero guest facts; primary and secondary activation advanced generation to 2 and 3; preview returned 6 venues, 2 providers, 4 directional legs, 1 conflict; guest repository returned 114 current facts and zero expired ATT-03 facts. Unauthenticated preview returned 401; wrong-property preview 403. See `docs/product/evidence/sprint-8/initial-vertical-slice.json`. This is exploratory integration on an unfrozen working tree, not final AC acceptance or independent review. It establishes the chosen integration path is viable; it does not calibrate total agent-hours or establish a deadline. Final relevant gates/demo remain required after candidate freeze. A continues domain policy and M2/M3; B continues operator/guest M6.

## Integration and lease handoff

A reported 117 focused domain/grounded-QA tests and Ruff passing, then held product files stable. C independently ran 111 existing affected guest-brief/preparation/room/claim-format/architecture regression tests; all passed (`domain-regressions.log`). B reported 13 identity/transport and 2 real PostgreSQL API tests plus initial web lint/typecheck passing; subsequent renderer fixes require affected final rechecks.

The first refresh integration failure was a `ScopeError`: a synthetic revision changed the authoritative hotel config. A corrected the fixture to preserve that config; the existing scope guard was not weakened. B preserved the original failure locally. Current guest replay correctly returns 409 `stale_source` after source refresh, freshness reports stale, current retrieval reflects 110000, historical saved data remains 100000, and fake-provider calls do not increase.

C review required specific-need evidence matching, source/fact grouping, whole-turn read timeouts, domain-owned localization, and consumer fixes for nested refs, stale cards and specific unknowns. These are scoped AC corrections, not new stories or scope expansion.

Lease handoff: A now owns only NEW `tools/evals/sprint8_runtime.py`, `sprint8_browser.mjs`/helpers and their new harness tests until controls are ready. Sprint 7 controls/state remain untouched. B temporarily owns `domains/hospitality/registration/local_guide_labels.py` and a dedicated label test for specific localized unknown-code text, in addition to its consumer files. All other A product files are stable unless a concrete coordinated integration finding requires a named transfer. No live runtime config/state has been initialized.

## Final offline readiness checkpoint

Product f4af97b878f78986015a5203edb5ff33c103732897b2eb226dd0aaf6bec53182/273 and controls66c7f6d466d5e8edacf6673a8ee5d700be093229f745a5685dd94ddd46df8a24/4 independently verified by Q; all seven findings closed. Final263 relevant backend checks, affected99 native/orchestration after last guard, web43/contracts/lint/typecheck/build, canonical Ruff/compile and staged whitespace checks pass; counts overlap. Actual operator demo and mobile390 completed, guest facts0 after revoke/delete; API/web stopped. Actual guest model run UNVERIFIED, no live-authorized config/state, no S7 reuse. Exact four inputs, data/prompt/config/source pins and independent oracle are in the proposal and manifests.

Git CLI publication lacks a credential; use the already connected GitHub connector to publish the exact reviewed tree to the same Sprint8 owner branch/base, without credential changes. No manual CI or CI wait gate; no merge before remaining actual AC. #100 will contain immutable publication/PR and fresh permission proposal. Coding/model effort metrics unavailable except reported model IDs. A/B/Q are finished; no pending code command or file lease. Isolated local PG only is retained temporarily, with no real provider. See acceptance report for truthful Done/pending scope.

## Approved batch1 stopped; offline repair checkpoint

Hieu approved pinned4turn/max8request Sol/low and explicitly acknowledged700-token CLIpostcheck limitation. Originalcandidate b1744bf exactproduct/control/data/oracle pins were independently verified before activation. Private authorized matrix changed only run_id/authorization metadata (derived SHA825b4ef6074b29bb78999737fd3ba7219d78ef08321dea42a324a31d2fb8b73a); fresh isolated DB staylead_s8_live bothv1 sources approved generation3 exactoraclehashes. No Sprint7 allowance reused.

Batch first-failure stopped/sealed at1turn/2requests; unused3/6 CLOSED, no retry/reset/transfer or new live authority. StateSHA9919789c262844aa5cfe9a381f98bdfbb9a1705c5a1c2d8c4acd9fe76fcd66b4. Provider calls12619ms/11634ms; aggregate24454input/1015output across2calls, percallusage unavailable. API stoppedexit143/browserexit1. Original browser failed literal需要确认; Q confirmed validChinese待核实事项/请向场所确认当前营业时间。 makes this a lexical oracle false negative, while original attempted artifacts were lost beforeassert. Original failure/oracle/state stay preserved; read-only DB and offline exact-response M6replay only establish component evidence, not original fullUI/batchPASS.

B traced separate S8-only cold-cache genericUIlabels omission: local-guidecall2 requests onlydomainlabels, forcingEnglishgenericfallback. Authorized offline repair leases: B composition/dependencies/guest_chat.py, domainlocal_guide_labels helper ifneeded, newcorelabelcontracts/integrationtests; A4existingacceptancecontrols (browser/helpers/runtime/harnesstest) for capturebeforeassert, structuralrenderedunknowncheck, futureNEWreacceptance1namespace. No changes to approvedutterances/caps/calls/model, no newprivateauthorization/state; Q derives separate v2oracle without overwritingoriginal and independently reviews fixes. Fullfresh4/8 proposed after changedcall2contract; no reuseofclosedslots or automaticrun. #100/#102 remainBlocked; #101 remainsDone, parentsunchanged.

### Repaired candidate frozen and independently reviewed

Product71dbcf11b07cba4259d3a0f052316499cd156ce38c9ab470acf50cafe3bec855/275; controls257513597e9121239410b52cdc5f5aeb772add96e8947a155b730b9c567983b0/4; newindependentoracle25d92789b1d5065a8c41573d91e1a0934436b045e96d10595b673aa319471030. B4productfiles and A4controlsfiles frozen; C121+15focused/staticPASS; QindependentrepairreadinessPASS, actual repairedpathUNVERIFIED. Web/prompt/catalog unchanged, priorrelevantgatesreused. Newproposalreacceptance1 is unauthorized4/8 originalinputs; no liveconfig/state initialized. Originalsealed1/2/statehash9919 remainsunchanged; unused3/6CLOSED. API/browser/webstopped, isolatedPG retainedonlyuntilfinalQchecks thenstop. No additionalmodelcalls, newbacklogstory, fullSprintDone/merge/deploy. Publishnewexactreviewedtree viaexistingGitHubconnector tosameownerbranch/base; neverrestoreoldallowance.

## Final approved actual batch completed

Hieu explicitly approvedNEWproposalv2/candidate4f73e00. Product275/control4/oracle/cases unchanged and independently preflighted; privateauthorizedcaseSHAce03aca2afb5313aef71c25bd8986a66c915233a950f1a9859022b363fe73ce1 differs onlyrunID/authorizationmetadata. FreshDBstaylead_s8_r1 bothv1sources approvedgeneration3 exacthashes. Actual4turn/8requests COMPLETED with4exactQ/rootreceipts, no retry/fallback. StateSHA bf05af652f3c796af218b45b804470221e115b0a597ff9bb20271d123478d8b7; no furtherinferenceauthorized. Chinese/Frenchsamecatalogdistinctfits/source/sponsor/currentness; ArabicmobileRTLpeanut+stepfree+wheelchairUNKNOWN; sameC Frenchquiet→social edit retainsallhardneeds, sourcegeneration3, finalbriefv2. ActualDB4completedrequests/3briefs/4receipts/4sourceutterances/8messages/0roomresults; no roomselection/profileprerequisite. C/Q inspectedresponsehashes/currentguideDOM/screenshots; mobilelowerguideinscrollabletranscript, nofullscrolledguidescreenshotclaim.

Currentbatch95864input/3396outputtokens, all8callswithin25s (max13.911s), percallusage/returnedmodelidentifier unavailable; requestedSol/low,700CLIpostcheck limitation unchanged. OriginalHALTED1/2 andclosed3/6preserved; totalSprint8actual5guest/10requests/120318input/4411output acrossbothbatches. API/webstoppedexit143/browserexit0, localPGstopafterQfinalreadonlyreport. Sourceunchanged so priorrelevantlocalgates andindependentoperator/domain/auth evidence reused; no repetitivesuites. PublishfinalAC/evidence only then ownPRready+mergeintoexistingbasewhenGitHubpermits. No manualCI/deploy orbroaderparentclosure.

Final independentQ verdict PASS fullscopedG1–G4/L1–L4/C1–C3/DoD, noopenactionablecorefinding; independent-final-review.json SHA8ee235fa942a76cfa2595fb9b126b010e1a04fb86a06250a98fc5f9b2afa0dbf. Allactualreadonlycheckscomplete; isolatedPGstoppedcleanly, no commandsrunning. No furtherinferenceauthorized. Finaldocs/evidenceonlypublicationandownPR103mergeauthorized; retainbroaderparentsOpen.
