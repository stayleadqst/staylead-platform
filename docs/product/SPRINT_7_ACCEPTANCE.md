# Sprint 7 — báo cáo thực thi

2026-10-27 (Asia/Saigon). **Sprint7 chưa hoàn tất. B07 #28 Done; C01 #39, điều phối #97 và S7-F1 #98 Blocked.** [PR99](https://github.com/stayleadqst/staylead-platform/pull/99) Draft/unmerged, base `sprint-5-canonical-brief`. Không tạo story trùng hoặc đóng broaderparent/epic.

## Kết quả hiện hành

Batch NEW Pine2/4 được Hieu duyệt dừng tại **1lượt/2requests**, tổng Sprint7 **46runtime provider requests**. Pine1 FAIL vì tự tạo pendinghard_bed_types; Pine2 phụ thuộc và chưa chạy. Unused1guest/2requests đóng, không retry/reset/transfer/amendedinput/historyrepair. API/browser đã dừng. AcceptedCity/Family/B07 tiếp tục dùng lại; không biến các failure cũ thành PASS.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| B07 #28 | Q / gpt-6.1-sol/high | ActualAC1–3 PASS, closedDone | Bookingintent/trustedboundary/language/privacy trong technicalpilot; không claim bookingendpoint thật hoạt động | Giữ Done, không chạy lại |
| City Chinese→sửa giường | Q / gpt-6.1-sol/high | ActualR3 City1→2 PASS | STD5.4m/TWN5.85m comparison; false-sharing/hard6.5m/noinventedtype/maxrooms; distinctsingles; staleUI/POST409/newv2selection0extraLLM; source/DB/version đúng | Giữ PASS |
| Family thiếu tuổi→7→12/budget | Q / gpt-6.1-sol/high | ActualR2 Family3–5 PASS | Stablechild/guardian/consent/separatebed/dates;5.2m/7.6m knownbase, feesunknown/nulltotal, budgetstrength không bịa | Giữ PASS |
| Pine2case chain | Q / gpt-6.1-sol/high | R3initialverificationPASS; latestR4Pine1FAIL/Pine2Blocked | Party/date/access đúng nhưng unrequestedpending gây sai clarification; chưa có fullFrench/currentselection | Cần actualfreshPine2case trên reviewedfix/profile mới được duyệt |
| Offline remediation | B / gpt-6-luna/high | Implemented/frozen1435c5fc,237pins | Knownaccessmarker qua unrelatedpending, promptpermission rule, driverhardtype/pendingnegative; canonicalvalidator không đổi | Promptadherence chưa được actualverify |
| Independentreview | Q / gpt-6.1-sol/high | ScopedofflinePASS1435c5fc |237repo/snapshot/digest/exact6delta; causal/positive/negative/source/driver probes; đọc rootgates | Không claim actualmodelPASS hoặc modelupgradeguarantee |
| Integration/delivery | Coordinator / exactmodel-effort metadata không có | Ownbranch/PR99; publication đang chuẩn bị |280backend16PG/RuffcompileDiff/NodeSmokePASS; frontend53pins không đổi dùng lại40tests/lint/typecheck/build | FullactualAC/DoD trướcDone/merge |

## Actual failure và nguyên nhân

LatestR4 candidate221027b1,2Pinecasecontrols-only trên product0eb, đã qua23focusedharness/APItests vàQreadiness. Pine1HTTP200/bodySHA `95da645df994aeee849e7618a1dfad62e909fb4c2e42ab20753a70d0163494e8` lưu đúngadult1/childUUIDage7/guardian/sharing/date/twohardaccessneeds. Model thêm `clarify(room_requirements.hard_bed_types)` chỉ vì permission “chung giường lớn” không nêu physicaltype. Quote support không chứng minh clarification đó cần thiết. CanonicalM2 đã commit brief/state1,pendinghard_bed_types,1completedrequest/result,2messages,noselection; source refs vẫn current/approved. Không sửa actualstate.

M4 earlybranch khi có pendingroomrequirement đã trả result trước khi gắn `known_hard_accessibility_needs`. Saved/nonpendingaccessquestion vì thế render generic “Tôi nên áp dụng yêu cầu phòng nào?”; fieldroom_advice cũng generic. Đây là primaryM3semanticmisclassification và secondarydeterministicrenderingmetadata defect. Driver dừng đúng trước marker01; Pine2 chưa chạy vì không có quyền tự xóa pendingkhông liên quan trong originalnextutterance.

[Actualreview và ACmatrix](evidence/sprint-7/q-review-reacceptance4-actual.json) · [Actualmanifest221027b1](evidence/sprint-7/candidate-manifest-reacceptance4-v2.json) · [Readiness](evidence/sprint-7/q-review-reacceptance4-final.json) · [Authorityreceipt](evidence/sprint-7/reacceptance4-authorization-receipt.json) · [Stopreceipt](evidence/sprint-7/reacceptance4-stop-receipt.json). Finalhalted1/2 SHA `16e5d987eff565d2b23a373b02057e682f1ab7c72742e0010d0c9baa46c5062c`, lifetime46. Không có marker01/turn2 hoặc inference sau offlinefix.

## Reviewed offline fix và giới hạn

Candidate **1435c5fc0a58cc5e3133497416aa3eb39d4a8f51685c398b53d9a8c344284e5d**,237pins,exact6delta từactual221027b1. Prompt phân biệt permission/broadbedsize với hardphysicaltyperequirement/clarification; genuineexplicitunsupportedhardtype và realconflict vẫn được giữ pending. **Originalbadcapture vẫn qua staticparser/currentquote/canonicalM2**; không claim server đã nhận biết semanticnecessity. Prompt change là adherencehypothesis, chưa actualmodelproof.

M4 deterministicfix giữ knownaccesshotelverification qua unrelatedpending chỉ khi accesscógiátrị và không tự pending/wholeobjectpending. Absent/accesspending/wholepending vẫn hỏi guest, không tự chứng nhận hotelcapability. Browser cảPine1/2 từ chối hard_bed_types hoặc pendinghard_bed_types không được khách yêu cầu. Không NLparser/alias/dropbadstate/validatorweakening/capincrease; existingclear-only/set-only/currentUUID/canonicalquestion/Frenchprojectionguards giữ nguyên.

[Finalmanifest](evidence/sprint-7/candidate-manifest-reacceptance4-final-remediation.json) · [Independentreview](evidence/sprint-7/q-review-reacceptance4-final-remediation.json) · [Localgates](evidence/sprint-7/reacceptance4-final-remediation-local-gates.json): **280contracts/architecture/API PASS**(3existingwarnings),**16isolatedPG PASS**(1existingwarning), Ruff/compile/diff/NodeSyntaxSmokePASS. Builder194focusedPASS; Q6focusedPASS cùng exactcapture/VI+FRknownaccess/unrelatedpending/absent+pendingnegatives/validPineproducer+driver mutants. Không cộng tests chồng nhau thành unique totals. Frontend53pins không đổi: dùng lại40tests/lint/typecheck/build. Defaulttests/startup0liveLLM; PG dùng isolatedstaylead_sprint7, actualacceptanceDB chỉ read-only ngoài approvedbrowserrun.

Các clear/questionfieldfix trước tại0eb vẫn có fakeAPI→PG proof: samechildage7→8/guardian/date, clearbothhardaccess, FrenchLOFT2.2m/night×2=4.4m knownbase, unknownchildfees/nulltotal,persistedFrench. Actualfullchain đó vẫn chưa được nghiệm thu.

## Backlog

| Story | Đã kiểm chứng | Còn thiếu | State |
| --- | --- | --- | --- |
| #28 B07 | ActualtechnicalpilotAC1–3 PASS | None trong scopeđượcduyệt | Done/closed |
| #39 C01 | City/Familychains, priorPineinitial; offlineM4/math/source/state/UI guards | FreshPinehardaccess→samechildage8/clearboth/French/currentselection; fullAC1–8 | Blocked |
| #98 S7-F1 | Exactrootcauses/attempts/evidence/currentofflinefixreviewed | ActualPinesemanticacceptance/profiledecision | Blocked / Sprint7 / P0 |
| #97 coordination | Team/gates/closedlimits/evidence maintained | FullAC/DoD/verifieddelivery | Blocked |

Existing#98 giữ đầy đủproblem/impact/attempts/evidence/AC/epicE3/priorityP0/affected#39/#97; không tạo story trùng, defer ngầm hoặc mở lạiB07. Failure histories bất biến.

## Đề xuất mới — Pine2/4 với Sol/low, chưa được phép

[Proposalreacceptance5](evidence/sprint-7/reacceptance5-sol-cases-proposed.json) dùng **đúng hai Pinecaseobjects/câu gốc**, một phiênfresh, max2guest/4requests,2calls/lượt,25sprovider/45sturn/700output,noautomaticretry/firstblockingfailurestop/nofallback. City/Family/B07 không chạy lại. Đề xuất đổi riêng inferenceprofile từgpt-6-luna/low sang **gpt-6.1-sol/low** vì primarysemanticmisclassification vẫn lặp; builder vẫnLuna/high, reviewerSol/high. Không tự đổi currentruntimeMODEL hoặc defaults, chưa newconfig/state/inference. Cần explicitNEWallowance và modelchangeapproval sau concretepublication; không tái dùng phần dư1/2 đã đóng.

[OpenAI Docs](https://developers.openai.com/api/docs/models/gpt-6.1-sol) xác nhận Sol hỗ trợlow vàstructuredoutputs; localCLImetadata có Sol/low. Điều đó không chứng minh accountaccess thực tế, comparativequality,25s/700success hoặc chi phí. Không có controlledcomparison/guaranteedfix/savingsclaim; đây là boundedtrialproposal, authorizedfalse. CácAC/DoD/source/state/semanticguards giữ nguyên; fullactualQ trướcDone/ownPR99mergekhiGitHubchophép.

## Usage/delivery

[ObservedR4usage](evidence/sprint-7/reacceptance4-observed-usage.json):2responses report24865input/514outputtokens, lifetime46 gồm44trước đó; agenttokens/billingamount không có. Unused1guest2requests đóng, không reset/transfer. API/browserstopped; rawmodel/API/config/signingsecret/DBdumps/screenshots local0600; public chỉsource/authoredcases và sanitizedsummaries/hashes.

Ownbranch `sprint-7-room-advisory`; acceptedbaseline `a46a63eb4b589b8518f9477ebd66e81d89a0f054`; publishedHEAD trước recovery này `4548c181448a07a8788755af1a170f97579bd382`. Publicationcommit/tree mới ghi trong PR/backlog/deliveryreceipt sau review. PR99Draft/unmerged/baseSprint5; no manualCI/rerun/waitgate/checkbypass/Grok/deploy/newpaidresources/main/otherPRmerge/broaderclosure. Automaticworkflows có thể chạy sau branchupdate; không claimCI PASS. Synthetic3hotels/9roomtypes không chứng minh realhotelapproval/liveavailability; bookingdestinations là ví dụ.

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
