# Sprint 6 — Hội thoại đa ngôn ngữ và brief nhất quán

**Kết quả: đã triển khai và kiểm chứng offline; Sprint6 vẫn Blocked, không có story nào được đánh dấu Done.** Batch model thật dừng ở lượt1 do structured-answer validation; lượt2–9 chưa chạy. Đã tạo [S6-R1 #95](https://github.com/stayleadqst/staylead-platform/issues/95) trong product backlog cho sprint sau, P0/E2, có problem/impact/attempts/evidence/AC/links. Không tự retry inference.

## Work / owner / stage / verification / next action

| Work | Owner / actual model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|
| #91 preference và state invariants | A /root/backend, gpt-6-luna/high | Implemented, offline verified; Blocked | PG scope/CAS/no-op/restart/replay; language-only giữ brief version; actual T1 vi/rev1 và briefv1 persist | Shared model matrix chưa hoàn tất; #95 |
| #92 cross-language grounding / guards | A, gpt-6-luna/high | Implemented, offline verified; Blocked | Guard ngày/giờ/số Unicode; source regressions; pinned actual-PG lexical baseline | Không có delivered grounded answer; model semantic comparison chưa kiểm chứng; #95 |
| #93 presentation / RTL / labels | B /root/frontend, gpt-6-luna/high; A producer | Implemented, offline verified; Blocked | Desktop/mobile multilingual, explicit-script RTL parity, atomic labels/fallback; Q kiểm schema→fallback correction | Chinese/Arabic/Hindi/etc actual model presentation chưa chạy; #95 |
| #74 current eligible copy | B, gpt-6-luna/high | Implemented, offline verified; Blocked | Actual Chrome clipboard/keyboard, exact rendered text, pending/stale/old-scope/late gates, failure/unsupported fallback | Current answer từ shared live matrix chưa có; #95 |
| #94 coordination/integration | C /root, exact runtime model ID/effort unavailable | Ownership/contracts/integration/report complete; Sprint goal Blocked | Candidate pin, bounds, PG/browser, findings/fixes, evidence/status/backlog | Giữ core Open/Blocked; không đóng parent/epic/milestone |
| Acceptance infrastructure | /root/acceptance_helper, gpt-6-luna/high | Prepared, offline tested; C executed | Persistent9turn/18request/max2counter, redaction, baseline, read-only snapshot, driver | Helper không tự inference |
| Independent review | Fresh /root/sprint6_review, gpt-6.1-sol/high | Code findings closed; shared DoD Blocked | [Review](evidence/sprint-6/review.md), direct probes và final37focused tests | Không nhận semantic PASS hoặc actual live success |

## Candidates / source / runtime

- Baseline remote S5 `d5d824125867d008f004300899f408aa75245e04`, tree `c8f24adcffe27b1ec86cf0c7cff57b7668210c5c`, khớp local S5 c073580. Chỉ nhánh mới `sprint-6-multilingual` được phát triển; PR83/89 và main không merge/reset.
- Actual failed batch: `e66647a24d5c81b60b3496a74ef7f4217c85a4c4`; [manifest214files](evidence/sprint-6/candidate-manifest.json), fingerprint `391b09ae203ef3922c1ec54cac54373e52ee200d0690a3a7df4f868699c197c9`. Product fingerprint không đổi trong batch.
- Final offline product: `5ac41db7646c49d2fc2acce5387781f4fa67ee9e`; [final manifest](evidence/sprint-6/final-candidate-manifest.json), fingerprint `55a4ab00e0d75cb850585d6ac2ce71b9f2c1f50687e936ce4ed15029376a16cc`. Không có live rerun trên candidate này.
- Corpus authored synthetic knowledge-v1 + một nguồn URL synthetic test mới; URL nonfunctional, không phải hotel/operator approval thật. Không sửa/promote các internal/unapproved URLs. [Overlay/hash/parser checks](evidence/sprint-6/harness-check.json), [database initialization](evidence/sprint-6/database-initialization.json).
- Existing PG18 server dùng database test và acceptance mới riêng biệt, không sửa database sprint cũ. Khởi tạo cluster riêng từng bị sandbox chặn và host hết shared-memory IDs; giải quyết bằng database cô lập trên server hiện có, không chỉnh host IPC hay dừng server dùng chung.
- CodexCLI0.153.4, requested gpt-6-luna/low qua adapter local/test; actual served model unreported. Không production account service. [Boundary/model/prompt/matrix hashes](evidence/sprint-6/live-boundary.json).

## Actual batch — expected / observed

[Matrix](evidence/sprint-6/live-cases.json):9guestturns, tối đa18requests, max2/turn,25s/provider,45s/turn,700token postcheck, không automatic retry/resume/judge. Native hard pre-generation output cap chưa được xác minh.

| Turn | Expected | Observed / verdict |
|---|---|---|
| 1 VI | Preference vi/rev1; dates10→13Dec2026, nights3, adults2; grounded breakfast tại Bến Gió tầng1,06:30–09:30; current copy | Preference/brief/receipt đúng đã persist. Hai model calls returned; final answer bị schema parse từ chối, HTTP502/partial_success. Không delivered answer/citations/current copy. **FAIL acceptance**, không có semantic verdict về raw answer. |
| 2 EN | Add child missing age, giữ dates/adults, rev2 | Chưa chạy |
| 3 FR | Same child age7, checkout14, rev3 | Chưa chạy |
| 4 JA | “Bữa sáng đó” contextual FAQ, rev4, brief không đổi | Chưa chạy |
| 5 Chinese | Grounded Wi-Fi, giữ IDs/age/dates, render/copy, rev5 | Chưa chạy |
| 6 AR | RTL, exact parking numbers/approved synthetic URL, rev6 | Chưa chạy |
| 7 HI | Ambiguous checkout clarification, old dates giữ nguyên, pending field, rev7 | Chưa chạy |
| 8 KO | Explicit checkout15, same child/age, rev8 | Chưa chạy |
| 9 short/mixed | Giữ KO/rev8 và brief | Chưa chạy |

Actual [observations](evidence/sprint-6/live-run/observations.jsonl), [stop result](evidence/sprint-6/live-run/run-result.json), [runtime events](evidence/sprint-6/runtime-events.jsonl), [persisted exact error](evidence/sprint-6/failed-request-diagnosis.json), [read-only PG snapshot](evidence/sprint-6/codex-db-observation.json).

Error `invalid_model_output / The model returned an invalid answer.` xác định failure tại `model_validate_json`. Raw rejected output và validation locations/types không được giữ, chỉ hash/length/usage: exact field/root cause **unknown**. Không quy failure cho numeric guard, labels hoặc model semantics khi chưa có evidence. Đây không phải timeout/output-cap failure theo telemetry.

Usage: **1/9 turns,2/18 requests,2 returned results,0 automatic retries/resumes**; input15635/output259tokens, total/billing unavailable. Provider5.038/5.567s; HTTPturn10.759s. Counter chưa hết; không reset hoặc coi phần còn lại là một fresh batch. S5 Codex8/Grok8 frozen, không inference Grok. Agent token/cache/reasoning/billing metrics unavailable.

## Local quality / review findings

- C integrated backend run:114passed/1failed ở mocked freshness contract cũ; test cần mock thêm persisted-language read và assert mới `answer_eligibility`. Đã sửa test seam, production fail-closed không đổi; A affected freshness6/language3/PG2passed. [Initial full log](evidence/sprint-6/backend-final-tests.log) được giữ, không gọi đó là full-suite PASS.
- Sau findings: backend guard/prompt focused34passed, generic-date recheck28passed; final optional-label fix37focusedpassed. Q độc lập xác nhận37 và6schema/cache probes. Chỉ chạy impacted checks sau sửa, không lặp suite không liên quan.
- C Ruff toàn backend/tests PASS; compile76backend source files trong memory PASS; builders Ruff/compile files sửa PASS. [Lint](evidence/sprint-6/backend-final-lint.log), [local summary](evidence/sprint-6/local-gates-summary.json).
- B web35contracts, lint/typecheck/build PASS; RTL cut presentation3tests + lint/typecheck/build PASS. Public build config chỉ domain=hospitality, guest contract1. Builder không lưu raw command logs; report phân biệt báo cáo builder và các browser checks C trực tiếp chạy.
- Actual Chrome trên production build:6script/text cases × desktop/mobile đã qua các assertions text/clipboard/keyboard/lang/dir/overflow, denied/unsupported fallback và pending/stale trước khi harness race assertion lỗi. Race checks sau đó PASS riêng; final focused az-Arab main/brief/answer direction PASS. [Harness](evidence/sprint-6/browser-presentation.mjs), [prefix log](evidence/sprint-6/browser-presentation-final.log), [race log](evidence/sprint-6/browser-races-identity-final.log), [RTL log](evidence/sprint-6/browser-rtl-script-corrected.log).
- Giữ lịch sử harness failures: browser-cache mismatch, English fallback warning expectation, async count, dynamic last-card locator, focused-probe TDZ. Đã sửa harness; không dùng lỗi này để nhận lỗi sản phẩm. Race-only log cũ in thừa các full-matrix booleans: chỉ3race assertions của invocation đó là evidence; corrected harness summary đã giới hạn checks_run. Không claim một full browser invocation PASS.
- Q phát hiện/sửa4code gaps: ordered time/date literal identity (sửa đầu ISO-only chưa đủ, đã thay generic ordered three-part span); explicit-script RTL precedence; final committed preference authority; wrong-typed optional labels fail trước fallback. Final Q không còn code finding. Lỗi labels được chứng minh/sửa offline; **không chứng minh** nguyên nhân actual rejected JSON hay live recovery.

## AC traceability — không đồng nhất offline evidence với Done

| Scoped AC | Expected / observed evidence | Remaining |
|---|---|---|
| L1-AC1 | Open tag validation; scoped PG preference; actual VI explicit/rev1 committed | Các language turns khác chưa chạy |
| L1-AC2 | Prompt precedence/short-mixed rules; current state persists | Actual short/mixed T9 chưa kiểm |
| L1-AC3 | Language-only producer PG không tăng brief version; separate preference revision | Actual switches T4–6 chưa kiểm |
| L1-AC4 | Replay historical metadata/stale eligibility; final prompt authoritative; existing receipt recovery regressions | Actual multi-language recovery/answer chưa đạt |
| L1-AC5 | Fresh engine/application đọc persisted preference; no-op/CAS tests | Real later-turn generation chưa chạy |
| L2-AC1 | Source authority unchanged; expected facts pinned, current PG lexical trace | No actual grounded delivered answer |
| L2-AC2 | Source/revoke/scope/injection regressions trong backend checks, không đổi filters | Không claim model semantic acceptance |
| L2-AC3 | Q direct positive/negative Unicode/time/date/decimal probes PASS | Không claim actual AR/Hindi numerical answer |
| L2-AC4 | [Current-matrix baseline](evidence/sprint-6/codex-retrieval-baseline-current-matrix.json): expected-fact lexical coverage T1/T4/T5=100%,T6=50% (parking missing);0LLMcalls | Actual contextual completeness/usefulness/false-rejection/unknown/conflict chưa đánh giá được; schema rejection1, actual grounded output0 |
| L3-AC1 | Actual offline production browser text/script/viewport/clipboard checks | Actual Chinese/etc model presentation chưa chạy |
| L3-AC2 | Client/server script parity tests + az-Arab production main/brief/answer PASS; historical copy/race gates | Actual sequential switching chưa đạt |
| L3-AC3 | Final schema→resolver malformed bundles fallback; valid cache atomic; core claim schema vẫn strict;37tests+6probes | Final candidate chưa live |
| L3-AC4 | Deterministic English fallback disclosure, last cache, clipboard error paths verified offline | Actual failure yielded partial result; no current answer |
| B12a-AC1–2 | Real Chromium exact rendered clipboard, keyboard desktop/mobile, denied/unsupported selection outcomes | Shared semantic matrix chưa đạt |
| B12a-AC3–4 | Pending/stale/old-turn/scope/late gates verified offline, no model call for clipboard | Current eligible model answer chưa có |
| C-AC1–3 | Contracts/leases/model roles, finding ownership, fixed candidate/evidence/limits and #95 backlog report | Integrated goal và all scoped AC/DoD còn Blocked |

## Delivery / remaining work

Implementation và offline fixes đã commit trên `sprint-6-multilingual`; final evidence/report được publish cùng nhánh và stacked draft PR base `sprint-5-canonical-brief`. Exact published head/PR link được ghi trên #94. Không merge/deploy hoặc đóng parents/epics/milestone khi shared DoD còn Blocked. Không dispatch/rerun CI hoặc dùng chờ CI làm gate; automatic workflows có thể chạy khi publish/PR update, không nhận CI PASS khi chưa kiểm.

#95 giữ P0/E2/Draft, không gán milestone hoặc tự thực thi sprint sau. Next owner cần diagnostic capture/reproducer đủ xác định structural failure và một fresh acceptance allowance tường minh, rồi chạy/check toàn matrix trên fixed candidate. User stories #91/#92/#93/#74 và coordination#94 giữ Open/Blocked; chỉ Done khi đầy đủ scoped AC/DoD.

C đã dừng riêng acceptance API18086 và web13016 sau snapshot; không dừng shared PostgreSQL server. Dữ liệu và counters giữ nguyên để điều tra. Secrets chỉ ở local private runtime config, không đưa lên repository/GitHub/evidence.
