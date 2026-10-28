# Sprint 7 — báo cáo thực thi

2026-10-28 (Asia/Ho_Chi_Minh). **Sprint7 chưa hoàn tất. B07 #28 Done; C01 #39, điều phối #97 và S7-F1 #98 Blocked.** [PR99](https://github.com/stayleadqst/staylead-platform/pull/99) Draft/unmerged, base `sprint-5-canonical-brief`.

## Kết quả hiện hành

Batch Sol/low được Hieu duyệt đã đóng **2 lượt / 4 requests**, tổng Sprint7 **50 runtime provider requests**. Pine1 PASS; Pine2 lưu đúng nhu cầu nhưng FAIL phương án/chọn/tiếng Pháp. API/browser đã dừng, không marker02 hoặc retry. Giữ mọi failure/counter; không sửa actualstate thành PASS.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|
| B07 #28 | Q / gpt-6.1-sol/high | Done/closed | Actual AC1–3 technical synthetic pilot | Giữ Done; không claim endpoint đặt phòng thật hoạt động |
| City Chinese→sửa giường | Q / gpt-6.1-sol/high | R3 actual PASS | STD5.4m/TWN5.85m; separate singles/budget; stale UI/409/new version selection0extraLLM | Reuse |
| Family thiếu tuổi→7→12/budget | Q / gpt-6.1-sol/high | R2 actual PASS | Stablechild/guardian/consent/date;5.2m/7.6m base,feesunknown/nulltotal,budgetstrength truthful | Reuse |
| Pine hardaccess→age8/clearboth/French | Q / gpt-6.1-sol/high | Actual ff917ce6: Pine1 PASS/Pine2 FAIL | Correct M2 samechild7→8,clearboth,guardian/share/dates; turn1 VI hotel verification; turn2 invalid room/bed indices | No useful option/French question/current selection; remains Blocked |
| Producer index contract | B / gpt-6-luna/high | Offline implemented/frozen327ea219 | Explain both zero-based index conventions; retain strict validators | Local gates/Q scoped PASS; publish concrete candidate |
| Integration/delivery | Coordinator / exact model-effort unavailable | Own branch/PR99 | Limits/source/usage/state preserved; local relevant gates | Full AC/DoD before Done/merge |

## Actual evidence và nguyên nhân

Hieu explicitly approved “Cho phép Sol/low 2/4” for exact two original Pine utterances, one fresh session, `gpt-6.1-sol/low`,2calls/turn,25s/provider,45s/turn,700output,noautomaticretry/nofallback/firstblockingfailurestop. Approved cases SHA607a92dcb433bf463150648e9cad548e0b7b47a78932d1d8f5ca1cd38ea625eb; oracle4adda unchanged. PriorR4 sealed1/2/lifetime46 remains unchanged; its unused slots closed.

First bootstrap candidate0a741183 failed before any turn/request: adapter constructor only allowed Luna/low. Root and Q reproduced real construction failure. B added explicit Sol/low alongside Luna/low, defaults unchanged and other profiles reject. Tests verify real Settings→build_provider→CLI model argument, no inference. First state retained/sealedHALTED0/0 SHA0c41c6db. Linked bootstrap2 uses separate files under SAME approved allocation; no duplicated allowance. [Recovery receipt](evidence/sprint-7/reacceptance5-sol-bootstrap-recovery.json).

Actual candidate **ff917ce60b3e2bf93a409cb8e6fe0cd6543c953914e88fa7af5a052fc7b3b5d5**,237pins: [manifest](evidence/sprint-7/candidate-manifest-reacceptance5-sol-bootstrap2.json), [readiness](evidence/sprint-7/q-review-reacceptance5-sol-bootstrap2-final.json), [35-test local gate](evidence/sprint-7/reacceptance5-sol-bootstrap2-local-gates.json).

Pine1 HTTP200/body450f0fed: child7,explicitguardian/sharing,date2n,bothhardaccess,pending[],noinventedhardtype/budget. Correct useful Vietnamese hotel-verification question, current sources, no certified accessibility/availability claim. Q enforced readonly DB confirms brief/state1,result1/completedrequest1,messages2,noselection. Root marker01 follows independent semanticPASS.

Pine2 HTTP200/bodyec570b87: samechild age8,clearONLYtwoaccessneeds,guardian/sharing/dates retained,pending[]. Native candidate has ONE Garden room with room_index1 and queen bed_index1; canonical both start at0. M4 rejects room_count_mismatch; nooption/selection. French claim labels exist, but new derived conflict question lacks translation and falls back English. Actual C01-AC5/8 remains missing. Q readonly DB confirms brief/state2,2completedrequests/results,4messages,noselection; actual data preserved.

Q causal probe: room-only correction in a COPY exposes invalidbedindex; correcting BOTH yields French partial Garden2.5m/night×2=5m knownbase,unknownchildfees/nulltotal. This is offline evidence only. [Causal results](evidence/sprint-7/q-review-reacceptance5-sol-causal-probe-results.json).

SealedHALTED2/4 stateSHA **9441449d9e272ac1ec15ea6ed05092dc2c34d49a90ace187e3876779d53936ee**, lifetime50; [stop receipt](evidence/sprint-7/reacceptance5-sol-stop-receipt.json). API43586 exit143/browser76255 exit1, no marker02/retry.

## Offline index fix và kiểm chứng

Candidate **327ea219c0503f66b2ac940ea0b94c228e1d9e7259e86e671ae995097ab0b5cf**,237pins, exact2delta from actualff917ce6: prompt + room-advice contract tests. Hướng dẫn nêu rõ room indexes contiguous0..n-1 và bed indexes theo danh sách expanded source beds,count; ví dụ mộtqueen chỉindex0. M4/parser/schema không đổi, không covert reindex/output repair. Originalbadcapture vẫn bị từ chối; corrected copy và mixedroom0/1 hợp lệ, gap0/2 và bed ngoài phạm vi bị loại. Đây là prompt-contract fix; adherence trên model thật vẫn chưa được kiểm chứng.

[Manifest](evidence/sprint-7/candidate-manifest-reacceptance5-sol-index-remediation.json) · [Local gates](evidence/sprint-7/reacceptance5-sol-index-remediation-local-gates.json): **284 contracts/architecture/API PASS,16isolatedPG PASS**, Ruff/compile/diffPASS; builder80roomtestsPASS. Frontend53pins không đổi, reuse40tests/lint/typecheck/build. Không cộng các suite chồng nhau thành unique totals. [Independent fix review](evidence/sprint-7/q-review-reacceptance5-sol-index-remediation.json).

[Concrete next proposal](evidence/sprint-7/reacceptance6-sol-cases-proposed.json): NEW fresh Pine2guest/max4requests, exactsame2originalcases, Sol/low,2calls25s45s700,noautoretry/nofallback,stopfirstblockingfailure. ReuseCity/Family/B07. **Chưa được duyệt allowance mới**, chưa init config/state/run. PriorR5exhausted2/4/lifetime50; không tự dùng lại hoặc tăng quyền.

## Backlog và next action

| Story | Đã hoàn thành | Còn thiếu | State |
|---|---|---|---|
| #28 B07 | Actual technical pilot AC1–3 | None in scope | Done/closed |
| #39 C01 | City/Family/Pine1 and correct actual Pine2 M2 update; offline math/source/state guards | Valid actual Pine2 options/French/current selection; full AC1–8 | Blocked |
| #98 S7-F1 | Root causes, attempts, evidence; fixes executed in Sprint7 | Producer-index fix validation and bounded actual reacceptance | Blocked / Sprint7 / P0 |
| #97 coordination | Ownership/gates/limits/evidence | FullAC/DoD/delivery | Blocked |

Existing#98 covers the related blockers with problem/impact/attempts/evidence/AC/epicE3/P0/affected#39/#97. No duplicate story, broader closure or silent deferral. Offline fix and independent review PASS; publish candidate and smallest concrete actual proposal before requesting any NEW manual allowance. The current2/4 is exhausted; no further inference is authorized.

## Usage và delivery limits

[Observed usage](evidence/sprint-7/reacceptance5-sol-observed-usage.json):4successful adapter responses,50775input/1410outputtokens; each request≤700output/25s, both turns≤45s. No fallback/retry. Agent tokens/billing unavailable. Bootstrap1 consumed0requests.

Own branch `sprint-7-room-advisory`, accepted baseline `a46a63eb4b589b8518f9477ebd66e81d89a0f054`, published HEAD before this recovery `ac951807f5050f6f637fceb0bc14242b30ae04fc`. Raw model/API/config/signingsecret/DB/screenshots local0600; public only source/authoredcases/sanitized summaries/hashes. Synthetic3hotels/9roomtypes/referenceprices do not establish real hotel approval/liveavailability/booking. No manualCI/rerun/waitgate/checkbypass/Grok/deploy/newpaidresources/main/otherPRmerge/broaderclosure. Automatic CI may run after branch update; no CI PASS claimed.

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
