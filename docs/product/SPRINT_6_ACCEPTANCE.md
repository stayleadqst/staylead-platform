# Sprint 6 — Hội thoại đa ngôn ngữ và brief nhất quán

**Đang thực thi; chưa có story Done.** Implementation đã có và các lỗi đã xác minh đang được sửa trong Sprint 6 qua #95 (P0, Epic E2). Chưa hoàn thành chuỗi nghiệm thu 9 lượt UI/copy trên một candidate cố định. Quyết định defer trước đây đã được thay bằng yêu cầu tiếp tục theo [Sprint-Execution.md](../execution/Sprint-Execution.md); giữ [báo cáo lịch sử](evidence/sprint-6/remediation/historical-acceptance-report.md) để đối chiếu.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|
| #91 preference/state | A — gpt-6-luna/high | Implemented, offline verified; Blocked shared DoD | Scope/CAS/restart/replay; thực tế đổi vi→en→fr→ja→zh→ar→hi→ko, brief và child identity được giữ | Nghiệm thu đầy đủ answer/UI/copy; short/mixed chưa có delivered answer |
| #92 grounding/guards | A — gpt-6-luna/high | Implemented; correction đang thực thi | JA numeric/timezone đã đạt thực tế; URL fix tại 559a3d2 qua review; strict source/numeric guards giữ nguyên | Typed clarification cho ngày mơ hồ; kiểm false unknown và câu trả lời courtesy |
| #93 presentation/RTL/labels | B — gpt-6-luna/high | Implemented, offline verified; Blocked shared DoD | Desktop/mobile/script/RTL/labels/races; actual UI/copy T1–5 | Hoàn tất presentation trong matrix cố định |
| #74 current eligible copy | B — gpt-6-luna/high | Implemented, offline verified; Blocked shared DoD | Exact clipboard T1–5; recovery/pending/stale/scope/failure paths | Không thay diagnostic API bằng bằng chứng UI/copy |
| #95 remediation | A+B — gpt-6-luna/high | In Progress, current Sprint 6 | Schema, receipt recovery, safe portion, Japanese boundaries/timezone, URL retrieval đã sửa | Clarification và acknowledgement contract đang sửa; sau đó review và nghiệm thu |
| #94 coordination | C — runtime model/effort unavailable | In Progress | Candidate/source pin, bounds, evidence, local gates và điều tra | Tích hợp, final AC map và publication |
| Independent review | Q — gpt-6.1-sol/high | URL/helper đã review; review sửa tiếp theo đang chuẩn bị | 64 backend tests và 14 helper tests độc lập đạt | Chưa có full-matrix semantic PASS |

## Kết quả actual-model và counters

Mỗi namespace tối đa 18 requests, hai calls/HTTP turn, 25s/provider, 45s/turn và 700-token postcheck; không automatic retry. Requested model `gpt-6-luna/low`, Codex CLI 0.153.4, existing authentication. Actual served model, billing và total tokens không được CLI báo; native hard output cap chưa xác minh. Các số input/output được giữ theo từng invocation trong events, không suy ra chi phí.

| Run | Candidate / kết quả | Provider requests | Semantic turns / explicit resumes |
|---|---|---:|---|
| Original | e66647: schema parse thất bại; historic exact field unknown vì không giữ raw | 2 | 1 / 0 |
| Namespace 1 | 70b→7ed: sửa ISO date prompt; explicit answer recovery trả current VI và exact copy; consumer lock được tìm thấy | 4 | 1 / 1 |
| Namespace 2 | 9929: T1 đạt; T2 thiếu child-count ref nên guard từ chối; continuation cũng bị từ chối | 6 | 2 / 1 |
| Namespace 3 | a933: T1–3 trả answer; T1 thiếu timezone; T4 bị false rejection với Japanese suffix | 8 | 4 / 0 |
| Namespace 4 | f52 UI T1–6, sau đó 0227 API diagnostic T7–9; xem chi tiết dưới | 18 | 9 / 0 |
| **Cộng dồn** | Không reset, không dùng trùng allowance | **38** | Không cộng các namespace thành một matrix PASS |

Hieu đã cho phép namespace2 tối đa18; bổ sung6 cộng12 còn lại thành namespace3; bổ sung8 cộng10 còn lại thành namespace4. Allowance cũ được đóng khi chuyển, counters giữ nguyên. Namespace4 hiện hết18/18, đã khóa live calls; **chưa có allowance cho namespace5**.

## Namespace 4 — expected / observed

[UI observations](evidence/sprint-6/remediation/remediation-4-live-run/observations.jsonl), [case comparison với lexical baseline](evidence/sprint-6/remediation/namespace4-case-comparison.json), [runtime events](evidence/sprint-6/remediation/namespace4-runtime-events.jsonl), [closed counters](evidence/sprint-6/remediation/namespace4-run-state-closed.json).

| Turn | Observed | Đánh giá |
|---|---|---|
| 1 VI | Dates 10→13 December 2026, nights3, adults2; breakfast đúng nguồn/time/timezone; current/exact copy | Đạt case trên f52 |
| 2 EN | Add một trẻ chưa rõ tuổi; đúng pending age, briefv2/rev2; current/exact copy | Đạt case trên f52 |
| 3 FR | Cùng trẻ age7, checkout14/nights4, briefv3/rev3; current/exact copy | Core đạt; có câu hỏi thêm không cần thiết |
| 4 JA | Context breakfast, 06:30–09:30 và Asia/Ho_Chi_Minh; brief không tăng; current/exact copy | Đạt case trên f52 |
| 5 Chinese | Wi-Fi miễn phí và credentials tại desk; dates/member không đổi; current/exact copy | Đạt case trên f52; screenshot desktop không tự chứng minh mobile |
| 6 Arabic | Lưu ar/rev6; parking40/100000 đúng nhưng URL claim không cite URL fact; HTTP502 | Guard từ chối đúng. Selector bỏ supporting URL dù preliminary retrieval/index có; đã sửa tại559 |
| 7 Hindi, API only | hi/rev7; checkout14 giữ nguyên, pending checkout, briefv4; same child age7. Unknown hỏi sai lựa chọn13/14, chứa ngày không có numeric provenance; HTTP502 | State đạt; answer không đạt. Không retry. Typed clarification đang sửa |
| 8 Korean, API only | ko/rev8; checkout15/nights5, briefv5, pending clear; same child age7; HTTP200 | State đạt; answer thêm false/irrelevant breakfast/Wi-Fi unknowns nên không full semantic PASS |
| 9 short/mixed, API only | Model output rỗng ở mọi content array, chỉ có labels; HTTP502 invalid_model_output | Không có delivered answer; thiếu kênh courtesy acknowledgement. Read-only PG xác nhận ko/rev8, briefv5 và cùng child age7 không đổi sau turn |

T7–9 dùng [one-shot helper](evidence/sprint-6/remediation/diagnostic_api_turn.py), mỗi lượt một POST, không retry, evidence allowlist và exclusive0600. [T7](evidence/sprint-6/remediation/diagnostic-api-turn-07.json), [T8](evidence/sprint-6/remediation/diagnostic-api-turn-08.json), [T9](evidence/sprint-6/remediation/diagnostic-api-turn-09.json). Helper đã được sửa lỗi preflight bảng/count trước khi gửi HTTP: failed T6 có request record nhưng không có user-message row. Lần ImportError không gọi model hay thay counters. Chẩn đoán API không chứng minh UI/clipboard; namespace4 có đổi product nên không phải fixed-candidate PASS.

## Các sửa đổi đã kiểm chứng

- Nested schema và canonical ISO/source literals; optional malformed labels fallback vẫn giữ core schema strict.
- Consumer dọn đúng pending sibling cùng answer-only receipt, giữ historical answers và mở lại composer. Production-browser proof với API mock đạt, không thêm model calls.
- Committed answer chỉ bỏ nguyên guest claim numeric-invalid khi còn nội dung an toàn có nghĩa đã được kiểm độc lập; không sửa text, thêm/mượn refs hoặc nới schema/source/URL/unknown/conflict guards. Citation-only content vẫn bị từ chối. PG/API safe-portion trace và same-ID replay đạt.
- Numeric tokenizer xử lý Japanese/CJK/Devanagari/Arabic và ASCII units; equivalent Unicode digits được chấp nhận, unequal values bị từ chối. Hospitality formatter chỉ bổ sung timezone từ đúng cited fact/window và revalidate literals; actual Japanese case đã đạt.
- URL supporting fact chỉ được giữ khi exact URL cùng xuất hiện trong question và same-hotel preliminary fact, ID nằm trong candidate index; current-source fetch và final claim-own-citation guard tiếp tục áp dụng. Foreign/guest-only/nonidentical/revoked cases không được nâng quyền.

Latest product URL fix `559a3d2`, helper-only correction `0227b9b`; [diagnostic pin](evidence/sprint-6/remediation/namespace4-diagnostic-boundary.json). C chạy **68 backend contracts + Ruff PASS**; Q chạy64 focused backend và source probes PASS. Helper14 tests + actual read-only PG resolver PASS. Các gates trước vẫn hợp lệ theo phạm vi: 10 PG regressions, safe-portion PG/API replay, Japanese timezone PG composition, 15 runtime checks; B36 web contracts/15 state/lint/typecheck/build và browser recovery proof. Chỉ chạy lại phần bị thay đổi; chưa ghi PASS cho code đang sửa.

Raw synthetic model output chỉ ở private scratch, opt-in, tối đa64KiB,0600; không publish. Diagnostics mặc định tắt, dev/test only, paths/types/counts allowlist. Giữ M1–M6 và default tests/build/startup offline.

## AC map và next action

| AC group | Evidence đã có | Còn thiếu trước Done |
|---|---|---|
| L1-AC1–5 | State/scope/CAS/restart/replay/late preference; actual language switching và same-child/date invariants | Full answer/UI recovery sequence trên fixed candidate; [snapshot sau T9](evidence/sprint-6/remediation/namespace4-final-db-observation.json) đã xác nhận state không đổi |
| L2-AC1–4 | Source/numeric negatives, pinned expectedfacts/lexical baseline, actual contextual JA/Chinese; per-case comparison | Clarification provenance, URL actual recheck, false unknown correction và complete semantic verdict |
| L3-AC1–4 / B12a-AC1–4 | Production layout/scripts/RTL/races/clipboard failure; current copy T1–5 | Full actual UI/presentation/copy matrix |
| R1-AC1–3 | Concrete captured failures, privacy guards, safe portion/recovery proof | Typed clarification/courtesy correction + targeted tests/review |
| R1-AC4–5 / C-AC1–3 | Owners/contracts/bounds, failures preserved, local gates | Fixed-candidate actual matrix, final review/map và delivery |

Không tạo story trùng: existing #95 có problem/impact/attempts/evidence/AC/E2/P0/affected links và được xử lý ngay trong Sprint6. #91/#92/#93/#74 giữ Blocked, #95/#94 In Progress. A sửa contract, B chuẩn bị namespace mapping nhưng không initialize hoặc inference, Q review; C tích hợp và chuẩn bị next acceptance cụ thể. Chỉ xin thêm budget khi bản sửa đã đủ reviewable; không tự tăng cap.

Draft PR96 vẫn base `sprint-5-canonical-brief`, chưa merge. Các local commits sau f877 chưa cập nhật remote branch ref; GitHub objects đã chuẩn bị một phần không đồng nghĩa đã push. Không deploy, tạo paid resources, manual CI hoặc đóng parent/epic/milestone. Automatic workflows có thể chạy khi cập nhật PR; không có claim CI PASS.

## Screenshot publication decision

Hieu yêu cầu giữ15 screenshot nghiệm thu local và chỉ publish code/báo cáo. [Index với hash](evidence/sprint-6/remediation/local-screenshot-index.json) giữ đối chiếu, không chứa ảnh. Automatic approval review đã từ chối upload ảnh vào repository public; không dùng workaround để upload. Bản local được giữ nguyên, ảnh không thuộc remote publication tree hoặc history.
