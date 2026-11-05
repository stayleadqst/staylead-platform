<!-- staylead-sprint:11:execution -->
# Sprint 11 — Đo và giới hạn thực thi mỗi turn
Trạng thái: TECHNICALLY_ACCEPTED, DELIVERY_PENDING lúc 08:41+07; planning/readback hoàn tất trước coding, contracts cập nhật 08:04+07. Nguồn backlog chính thức: GitHub Issues. Scope delivery được Hieu ủy quyền trong workspace AGENTS.md; quy trình process/autonomous-agile-v2.0-staylead/.
## Goal và phạm vi
Người vận hành lần được outcome của một turn tới retrieval/tool/provider, biết phần usage còn unknown; server chặn workload vượt giới hạn local đã chốt, giữ đúng authoritative state khi timeout/cancellation/retry.

| Scope | User story | Priority | AC đầy đủ | Dependencies | Owner/status |
|---|---|---|---|---|---|
| Core | [B10 #31](https://github.com/stayleadqst/staylead-platform/issues/31) | P0/order23 | AC1 trace versions/calls/latency/failure stage/redaction; AC2 whole-turn time/step/context/cancellation + authoritativebrief; AC3 simple/mixed benchmark observations + sourced usage/cost; AC4 payload/session/property/concurrency/retry ceilings, rejected requests create no calls | B02 capability evidence S1–S8 (parentOpen không tự là thiếu); B08 #29 accepted S10; D4 approved29Oct; D5 local offline stub, no new inference | B gpt-6-luna/high product; A gpt-6-luna/high admission/persistence; Q fresh gpt-6.1-sol/high; IN_PROGRESS sau dispatch leases; trước đó chỉ preflight |
Không stretch. Không nhận #32/#34/#47/#48/#53/#64 hoặc broader-parent closure; không mở lại S1–S10.
## Timebox/capacity
starts_at 2026-10-29T08:00:00+07:00; ends_at 2026-10-29T09:30:00+07:00 (90min, fixed); Review09:10; Retro09:25. Forecast ban đầu60–75min chưa đo; preflight builders không xác nhận đủ capacity (ước lượng conventional5–18h chưa hiệu chỉnh). C giữ scope đầyđủ và timebox90min, triểnkhai tối thiểu hai owners; forecast completion AT_RISK, không hứa Done; quá hạn chỉ closure và ghi chưaDone. C inspection theo milestone và mỗi15min khi active; next_check_at08:15+07. Max4agents inclC; worker run<=60min. Không có hard deadline/wake/restart supervisor được xác minh; không dựng framework.
## Team và ownership
| Owner | Model/effort | Lease |
|---|---|---|
| C | unavailable/unavailable (runtime không expose) | integration, docs/execution/SPRINT_11_EXECUTION.md, docs/product/SPRINT_11_ACCEPTANCE.md, docs/product/evidence/sprint-11/**; workspace validation/sprint-11-20261029/** và binding; private services |
| B /root/b_b10 | gpt-6-luna/high | composition/dependencies/guest_chat.py; platform/ai_runtime/**; infrastructure/observability/**; platform/conversation/orchestrator/grounded_qa.py; tests/contracts/test_b10*.py; tests/integration/test_b10_trace*.py; không sửa file A/C |
| A /root/a_admission | gpt-6-luna/high | composition/configuration/settings.py; entrypoints/app.py; infrastructure/persistence/store.py + admission helper nếu cần; infrastructure/migrations/**; tests/integration/test_b10_admission*.py; không sửa file B/C |
| Q (fresh, chưa dispatch) | gpt-6.1-sol/high | Independent fixed-candidate review; không sửa candidate; enforced read-only permission profile unavailable, không tuyên bố đã enforce |
## Contracts / D4 / D5
Hieu trả lời trực tiếp29Oct: “Dùng các mức đề xuất cho technical pilot local”: HTTP payload<=64KiB;12newturn/10min/session;120newturn/10min/property;1inflight/session,4/property; retry same request reuses reservedquota, không thêm quá2providercalls tổng/request. Existing question<=2000chars/context<=22000chars/output700tokens, selector140/2calls/25sprovider/45sturn/24htokenTTL giữ. Quota phải bind server-resolvedhotel/session, durable qua restart và concurrency; không dùng arbitrary clientproperty. Redaction: structured allowlist, không transcript/CoT/prompts/credentials/DSN raw. Cost unknown khi thiếu giá/usage; không hardAzurebillingcap claim. Config version sprint11-local-v1, C owner. Không thay retention/sourceexpiry policy.
D5: provider-neutral path + existing codex/Foundry adapters; tests dùng injectedofflineprovider, pin adapter/config, no live inference. Benchmark HTTP/API/PG thật với providerstub được ghi rõ synthetic/offline, không actualmodel/productionclaim.
Trace contract: request/turn identity, versions(source/brief/prompt/schema/config/model whereknown), safe stage events/counts/timing/outcome, partial/missing usage/cost unknown. B chốt exact typed API trước A.
## Tasks kỹ thuật (không userstories mới)
| ID | Owner/model/effort | Scope/deliverable | Dependencies/parallel | Verification |
|---|---|---|---|---|
| T0 | C unavailable | contracts/leases/base/tracker | trước coding | chat+GitHub readback, basee42d57f/tree4e8160c |
| T1 | B gpt-6-luna/high | trace/limits/admission/persistence/wiring + contracttests | T0; một filemộtwriter | producer→consumer positive/negative; offline |
| T2 | A gpt-6-luna/high | independent expected cases, HTTP/PG/restart/concurrency/cancel/retry + benchmark simple/mixed | T0, exactinterfaces từB; parallel isolated tests | observations có nguồn/candidate; no selfgrade |
| T3 | C unavailable + Q gpt-6.1-sol/high | localrelevant tests/Ruff/compile; browser consumer nếu user-facing mới; fixedcandidateQ, fix findings | T1/T2; Bfix giữownership | fullAC1–4/DoD; no fake=real claim |
| T4 | C unavailable | candidatepins, commit/push/ownerPR/merge existing sprint5base, Review/Retro/cleanup/handoff | relevant gates+QPASS; GitHubpermits | exactmerge readback, actualeventtimes/outcomes |
## Controls và handoff
Không live inference/deploy/paidresources/credentials/sharedinfra/manualCI/rerun/waitgate/bypass/workflowprotectionchanges. AutomaticGitHubnotifications từauthorizedmutations included; no privateemailSlack.
Repair cap3/failureclass/workpackage, retry3afterinitial peroperation, C ledger owner; reserveattemptbeforefix. Preserve S10 harness4/4, P1repair1, inference0, closurecommitapprovaltimeoutretry1; không reset. Initial B10 chưa có repair attempts verified from no priorB10work/issuecomments+handoff; newfailure IDs recorded when observed. Token actual telemetry unavailable, không tự numericalbudget/savings.
Resources từS10STOPPED; C owns new isolatedPG/API/web only; no writeroldowner. Untrackedrepo validation/2logs không publish. Owner sprint-11-turn-observability created from verified origin/sprint-5-canonical-brief@e42d57f0ca7a1721f58a2f59fc8c1eeb27a057bb, tree4e8160cb96b92170dbfedbb78a95323a17398d12; gitfetch requirednetworkescalation and succeeded.
Milestone chưa tạo; issue sprintrecord này là tracker chính. Không mặc định milestone đã tồn tại.
## Outcomes / events
Checkpoint ban đầu trước coding: Implementation NOT_STARTED; localgates NOT_RUN; Q NOT_RUN; PR none; Review NOT_RUN; Retro NOT_RUN; Goal NOT_EVALUABLE. Stakeholder feedback chưa có cho increment; không suy từ silence/tests.

## Contract freeze / scope history trước coding
- Hai productowners theo seams trên, không C coding. A giữ store.reserve_request backwards-compatible, thêm optionallimits, deadlinelease và cộtprovider_calls; atomiclock hotel→session, quota window600s; expiredlease không còninflight nhưng không xóa historicalquota/request hoặc reclaimM2.
- A: QuotaExceeded(scope,retry_after_seconds), ProviderCallLimitExceeded; consume_provider_slot(engine,session_id,hotel_id,request_id,limit=2,timeout_seconds,...)->int atomic trướcdispatch. Scope từverifiedserverclaims. Request cùngID khôngresetcallcount.
- B: request-scoped provider-neutral wrapper, local2callguard +async callback A; traceallowlist bounded, versions/timing/outcome/failurestage, no rawtext/secrets. Nội bộ confirm→answer shares trustedbudget/admission scope, khôngtựdeadlock1/session; preserve replay/CAS/partialsuccess.
- Existing contextcompression giữ authoritativebrief riêng, max22000chars;2providercalls làstepbound hiệncó, khôngnewarbitrarytoolceiling.
- A nguyênrawbody64KiB dù thiếuContent-Length; rejected no downstreamcalls.
- T2 nay A code+admissiontests, B trace/context+tests; C runs benchmark fromrelevantHTTP/PG observations and candidatepins. Mỗiowner báo actualfailures/C ledger trướcrepair; uncertainty khôngtự đổiAC/deadline.
- New sprintrecord đãtạo #108, đọc lạibody khớp trước coding; chưamilestone.


## Technical checkpoint cuối — 29/10/2026, 08:41+07
B10 đầy đủ AC1–4 PASS local/offline; C195 backend tests và48 webcontracts PASS, relevant lint/typecheck/compile/build đạt, Q fresh độc lập PASS trên final source `4f74ba27d4daccfe2e320c7d6c5506b13aaec5fbc2d8761fdf8005a1bba6a5f8` / tests `04d6cd7d2646ae537a782d725b732e835fa51ad66bde433b2db774d25e67e273`. Xem [acceptance](../product/SPRINT_11_ACCEPTANCE.md) và evidence đi kèm. B/A/Q đã hoàn tất, source frozen. PR/push/merge còn pending tại thời điểm checkpoint này; kết quả delivery và actual Review09:10/Retro09:25/ends09:30 được cập nhật ở [official sprint record #108](https://github.com/stayleadqst/staylead-platform/issues/108). Không suy từ technical PASS thành stakeholder feedback hoặc deployed.
