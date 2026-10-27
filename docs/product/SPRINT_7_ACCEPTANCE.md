# Sprint 7 — báo cáo thực thi

2026-10-27 (Asia/Saigon). **Sprint 7 chưa hoàn tất. B07 #28 Done; C01 #39, điều phối #97 và S7-F1 #98 Blocked.** [PR99](https://github.com/stayleadqst/staylead-platform/pull/99) giữ Draft, chưa merge, base `sprint-5-canonical-brief`. Không đóng epic/parent hoặc tạo story trùng.

## Kết quả hiện hành

Batch manual mới được Hieu duyệt4lượt/tối đa8requests đã dừng **4/8**, tổng Sprint7 **44requests**. City1→2 và Pine3 PASS; Pine4 FAIL. Family3–5 và B07 đã PASS được dùng lại. Browser/API đã dừng; mọi state/capture/failure giữ nguyên. Không retry, sửa lịch sử nghiệm thu hoặc dùng allowance cũ cho lần chạy mới.

| Công việc | Owner / model / effort | Stage / candidate | Kiểm chứng | Blocker / next action |
| --- | --- | --- | --- | --- |
| City Chinese → sửa giường | Q / gpt-6.1-sol/high | Actual PASS trên345a7141 | STD5.4m/TWN5.85m so sánh tiếng Trung; sửafalse-sharing/hard6.5m, không suyhardtype/maxrooms; hai giườngsingle riêng; cardcũstale/disabled, POST409, chọnmới đúngv2; nguồn/state/DBđúng | Giữ PASS, không chạy lại |
| Family thiếu tuổi→7→12/budget | Q / gpt-6.1-sol/high | Actual PASS trên4797d219 | Cùng childUUID/guardian/consent/giườngriêng/ngày; nguồn5.2m/7.6m; phíunknown/nulltotal, không bịa budgetstrength | Giữ PASS, không chạy lại |
| Pine hardaccess | Q / gpt-6.1-sol/high | Actual Pine3 PASS trên345a7141 | UUIDserver/tuổi7/guardian/share/ngày/hardaccess đúng; tiếng Việt đưa bước khách sạn xác nhận, không tự bỏ điều kiện hay chứng nhận fit | Giữ bằng chứng, chuỗi edit cần freshcontext khi nghiệm thu lại |
| Pine relaxation/French | B / gpt-6-luna/high | Offline fix0eb86e8c,237pins | Nativeclear context/set-only/clear-only; canonicalquestionfields; fakeAPI→PG tuổi8/clear/M4/Frenchpersist PASS | Pine4 actualFAIL còn nguyên; cần actual2lượt sau bản sửa |
| Review độc lập | Q / gpt-6.1-sol/high | Final scoped offline PASS0eb86e8c | Capture sai bị loại, correctedquote→M2/M4/FrenchLOFT4.4m/feesunknown qua; kiểm pins và regression | Actual Pinechain vẫn cần nghiệm thu |
| Tích hợp/delivery | Coordinator / metadata model-effort không có | Nhánh sprint-7-room-advisory; publication đang chuẩn bị | 275backend +16PG PASS; Ruff/compile/diff PASS; frontend53pins không đổi, dùng lại40tests/lint/typecheck/build; controlsNodeSmoke không đổi | Chưa Done/merge trước fullactualAC/DoD |

## Failure thực tế và bản sửa

Pine4 HTTP200/bodySHA `90329d014920d5ccf54919b242713fd416b6f41a34fa936235c5a7aa51a9aabc` sửa đúng cùng childUUID lên8 và giữ guardian/sharing/ngày, nhưng vẫn lưu `hard_accessibility_needs=['wheelchair-accessible bathroom']` dù khách đồng ý bỏ cả hai yêu cầu. Model liệt kê10field không liên quan trong `clear_fields`, bỏ sót field cần clear. DB đã commit brief/state2,2requests/results hoàn thành,4messages; không có selection. Không sửa DB để biến failure thành PASS.

Call2 còn trả `questions[].field='accessibility_confirmation'`. Schema cũ chấp nhận arbitrarystr; renderer không nhận đó là canonicalpath, đổi sang question.generic/room và loại labelFrench tương ứng, dẫn đến ENfallback. Không có Frenchpositiveoptions/rationale/currentselection. Đây là lỗi extraction và lỗi question-fieldcontract riêng biệt.

Bản sửa offline `0eb86e8c747e5674c45867fd358c007e767f91586ac1dc51761dd90c30d1c6cd` dùng trusted `GuestBriefSnapshot` hiện có để giới hạn clear vào các field đang có giá trị (kể cả budget0), không tạo emptyenum; nativewire tách set-only/clear-only, mixededits dùng các operation hiện có. Canonical M2 validator giữ nguyên, không parser ngôn ngữ/alias/capincrease. Questionfieldnative/Pydantic/prompt dùng canonicalpaths và canonicalUUID-age path, từ chối presentationalias. Không sửa platform/domain boundary hoặc frontend.

Regression fakeprovider qua API→M2→M4→PostgreSQL xác nhận tuổi7→8 cùngUUID/guardian/ngày, bỏ hardaccess, LOFT2.2m/đêm×2=4.4m knownbase; phí trẻunknown nên totalnull/incomplete. Rationale và câu hỏi tiếng Pháp được project/persist đúng. Corrected partialremaining-needs, mixedset/clear qua hai operation và budget0 có kiểm tra; guard set/clear collision, quote/intent/source vẫn giữ. Đây là schema/prompt remediation được kiểm tra offline, chưa chứng minh model thật tuân thủ.

## Bằng chứng và quality gates

[Actual review và AC matrix](evidence/sprint-7/q-review-reacceptance3-actual.json) · [Actual manifest345a7141](evidence/sprint-7/candidate-manifest-reacceptance3-v1.json) · [Readiness](evidence/sprint-7/q-review-reacceptance3-final.json) · [Stop receipt](evidence/sprint-7/reacceptance3-stop-receipt.json) · [Authority receipt](evidence/sprint-7/reacceptance3-authorization-receipt.json).

State halted4/8 SHA `e43430da31b74f840f82bcedf2b45c0fdeafc6643d12646c2e17c15561dd6d9b`. Root chỉ ghi semanticPASS receipts01–03 sauQ; không04. City stale409 và selections dùng0provider. Tất cả8outputs≤700tokens, providercalls≤25s, HTTPturns≤45s. Allowance đã hết; không call thêm sau bản sửa.

[Final offline manifest0eb86e8c](evidence/sprint-7/candidate-manifest-reacceptance3-final-pine.json),237pins · [Local gates](evidence/sprint-7/reacceptance3-final-pine-local-gates.json):275contracts/architecture/API PASS(3existingwarnings),16isolatedPG PASS(1existingwarning), Ruff/compile/diff PASS. Builder81focusedcontracts +1newfakeAPI/PG regression PASS. Không cộng các suite chồng nhau thành số tests độc lập. Frontend53pins không đổi: dùng lại40tests/lint/typecheck/build; controls không đổi sau actual345a7141: dùng lại Node syntax/smoke. Defaulttests/startup không gọi LLM thật; PGtest dùng `staylead_sprint7`, không ghi database nghiệm thu. Q kiểm tra actualDB bằng transaction read-only.

[Review cuối](evidence/sprint-7/q-review-reacceptance3-final-pine.json) xác nhận237repo/snapshotpins/digest, đúng7filedelta, originalbadclear và fieldalias bị loại, positive/negative probes đạt; reviewer không gọi model hoặc ghi actualDB. AcceptedCity/Family/B07 tiếp tục hợp lệ, proposalPine2/4 là scope tối thiểu còn lại.

Raw model/API captures, configs/signingsecret, DBdumps và screenshots chỉ local0600; public chỉ source/authoredcases và summaries/hashes đã lọc.

## Backlog và phần còn lại

| Story | Đã kiểm chứng | Còn thiếu | Trạng thái |
| --- | --- | --- | --- |
| #28 B07 | Actual technicalpilot bookingintent/trust/language/privacy, independentAC1–3 PASS | Không có trong phạm vi được duyệt; không claim endpointbooking thật hoạt động | Done/closed |
| #39 C01 | Citychain, Familychain, Pineinitial; M4/source/math/state/UI guards | Actual Pine hardaccess→samechildage8/clear/French/currentselection trên bản sửa; fullAC1–8 | Blocked |
| #98 S7-F1 | Nguyên nhân/capture/counterfactual và bản sửa offline hiện hành | Actual Pinechain trên bản sửa | Blocked / Sprint7 / P0 |
| #97 điều phối | Team/limits/gates/accepted evidence được giữ | FullactualAC/DoD/delivery | Blocked |

#98 là follow-up hiện có cho các defect liên quan; cập nhật problem/impact/attempts/evidence/AC/epicE3/priorityP0/affected#39/#97, không tạo trùng hoặc âm thầm defer. B07 và acceptedCity/Family giữ nguyên.

## Đề xuất manual còn lại — chưa được phép

[Proposal reacceptance4](evidence/sprint-7/reacceptance4-cases-proposed.json): **freshPine2lượt/tối đa4requests**, đúng hai câu gốc (R3turn3→4, sourcecase7→8), giữ gpt-6-luna/low,2calls/lượt,25sprovider/45sturn/700output,noautomaticretry/stopfirstblockingfailure. City/Family/B07 dùng lại PASS. Proposal `authorized_for_live_calls:false`, không có newconfig/state/inference. Chỉ hỏi allowance MỚI sau concrete reviewedpublication; không hỏi lại hoặc dùng lại4/8 đã đóng.

Q đánh giá fullC01AC1–8 sau actual/reuse; chỉ Done/merge ownPR99 khi đầy đủAC/DoD/localgates/review và GitHub cho phép. Không manualCI/rerun/waitgate, bypasscheck, Grok/deploy/newpaidresources/main/otherPRmerge/broaderclosure. Workflow tự động có thể chạy sau branchupdate; không claimCI PASS.

## Usage và delivery

[Observed usage R3](evidence/sprint-7/reacceptance3-observed-usage.json):8responses report98877input/3178outputtokens, kể cả failure; tổng lifetime44requests gồm36trước đó. Agenttokens và billingamount không có; số liệu adapter không phải claim hóa đơn. [R2usage](evidence/sprint-7/reacceptance2-observed-usage.json) và lịch sử giữ nguyên.

Acceptedbaseline `a46a63eb4b589b8518f9477ebd66e81d89a0f054`; publishedHEAD trước recovery này `ba37ca1be1ad32a660227126a57aa0ff93c00edf`. Commit/tree publication mới ghi trong PR/backlog và deliveryreceipt saureview. PR99 vẫnDraft/unmerged. Ba synthetic hotels/chín roomtypes không chứng minh realhotelapproval/liveavailability; bookingdestinations là ví dụ.

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
