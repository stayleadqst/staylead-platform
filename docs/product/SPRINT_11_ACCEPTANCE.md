# Sprint 11 — B10 technical acceptance

**B10 #31 đạt đủ AC1–4 trong technical pilot local/offline.** Q độc lập đã PASS trên source `4f74ba27d4daccfe2e320c7d6c5506b13aaec5fbc2d8761fdf8005a1bba6a5f8` (224 files) và test fingerprint `04d6cd7d2646ae537a782d725b732e835fa51ad66bde433b2db774d25e67e273` (60 files). Functional observations chạy trên pin `ed8138c868ad9d28e8248dc6252fe4df25cd1bb04e0f0984085e8a45f75a9d11`; delivery pin chỉ xóa một LF dư, Q delta PASS, 223 source khác và toàn bộ60 test không đổi. Commit, PR, merge và kết quả Sprint Review/Retro được ghi tại [sprint record #108](https://github.com/stayleadqst/staylead-platform/issues/108); tài liệu này ghi technical acceptance, không tự tuyên bố đã deploy hoặc business acceptance.

## Scope và authority

Core duy nhất: [B10 #31](https://github.com/stayleadqst/staylead-platform/issues/31), P0/order23, đầy đủ AC1–4. Không stretch hoặc broader-parent closure. Dùng lại B02/S1–S8 và B08/S10 evidence còn hợp lệ; không mở lại accepted S1–S10. M1–M6 giữ nguyên.

Hieu chốt D4 ngày29/10/2026 cho local technical pilot: raw guest payload64KiB;12 turn mới/session/600 giây;120/property/600 giây;1 in-flight/session,4/property; tối đa2 provider dispatch/request gồm failure/retry. Quota bind hotel/session do server xác định, durable qua restart. Internal confirmation answer không tốn thêm turn quota và dùng chung provider budget của request cha; explicit guest confirmation là request riêng. Same-ID replay không reset quota/counter hoặc gọi provider lại.

Giữ question2.000 ký tự, context22.000 ký tự, output ceiling700 token (selector140), provider timeout25 giây, whole-turn45 giây và session token24 giờ. Không đặt retention policy mới. D5: provider-neutral execution với injected deterministic provider; không live product inference.

## Expected → observed / AC

| AC | Kiểm chứng và kết quả |
|---|---|
| AC1 | Request-scoped trace có identity, versions/config, provider attempts/usage, retrieval/capability timing, outcome và failure stage. Q tái hiện persistence failure, invalid output, M4 failure và confirmation failure/replay; final outcome/stage đúng, exception payload được redaction. Persisted và first-response terminal snapshot giống nhau; replay không cộng lại calls/usage. |
| AC2 | Giới hạn context/output/calls kiểm trước dispatch; brief/constraints giữ riêng khi nén history. Absolute deadline áp dụng cả confirmation admission và các lock waits; Q probe budget1 giây trả504 trong1,013 giây, không answer call/late commit. Existing cancellation, CAS, partial-success và delayed-ack recovery regressions đạt. |
| AC3 | Simple FAQ và mixed FAQ+brief edit/confirmation có expected facts/state và observations. Fixture breakfast dùng đúng `F-HTL-CITY01-040`; mixed dates10–13/05/2027,2 adults/child9, briefv1. Per-request calls đúng; usage là số do stub cung cấp, cost unknown. [Benchmark](evidence/sprint-11/benchmark-observations.json). |
| AC4 | Raw byte boundary/streaming;12/13 session,120/121 property; concurrency1/4; window expiry; restart/call persistence; scope/hash/owner denial; serialized-clock race; expired lease và rejected-no-dispatch đạt. Migration7→8 giữ dữ liệu. Actual browser quota429 giữ nguyên12 request rows/2 provider calls/2 messages/briefv0. |

## Local gates và independent review

- Coordinator: **195 backend tests PASS**,16,33 giây; relevant runtime/grounded/architecture/admission/trace và S1/S4/S5/S6/S7/B09 regressions. Không cộng các counts overlapping của builders/Q.
- Web: **48 contracts PASS**, lint/typecheck/build PASS với `NEXT_PUBLIC_STAYLEAD_DOMAIN=hospitality`, `NEXT_PUBLIC_STAYLEAD_GUEST_CONTRACT_VERSION=2`.
- Source, new tests, changed S1/B09 tests: Ruff/compileall/diff-check PASS. Bốn lỗi Ruff `I001` trong import blocks cũ S4–S7 khớp chính xác base `e42d57f`; imports đó không thay đổi. [Đối chiếu baseline](evidence/sprint-11/ruff-baseline-comparison.json).
- Q fresh context, `gpt-6.1-sol/high`: PASS đủ AC1–4;9 known observations/reproducers và3 final fixture cases đạt, source/test pins trước/sau khớp. Q không sửa candidate; read-only là instruction, không có enforced permission profile. [Report](evidence/sprint-11/independent-final-review.json).
- B/A `gpt-6-luna/high`; coordinator runtime model/effort unavailable. [Candidate](evidence/sprint-11/candidate-final.json), [expected cases](evidence/sprint-11/expected-results.json), [local checks](evidence/sprint-11/local-checks.json).

## Consumer và giới hạn phép đo

[Browser evidence](evidence/sprint-11/browser-observations.json) và [ảnh quota](evidence/sprint-11/browser-quota-v3.png): actual browser → production web local → API v3 → PostgreSQL → offline provider. Một FAQ đã trả lời; C seed thêm11 synthetic reservations trực tiếp qua store, rồi gửi request tiếp theo bằng UI để kiểm429. Đây không phải12 lượt guest/model thật. Request bị từ chối không tạo thêm reservation, provider call, message hoặc thay brief; UI không báo nhầm unknown outcome hay tự retry.

`execution.elapsed_ms` và simple benchmark đo processing **tới snapshot trước commit**, không gồm final persistence/commit wait và không phải full HTTP latency. Chỉ mixed `workflow_elapsed_ms` là stopwatch toàn workflow. Provider/usage đều deterministic offline; không suy ra chất lượng model thật, tối ưu, uptime production hoặc hard billing cap. Giá/usage không có nguồn giữ unknown. Không hidden reasoning, transcript hoặc secrets trong trace.

## Failure history và delivery

Q v1 FAIL đã được giữ: trace lifecycle/path/stage, quota timestamp race, confirmation deadline, benchmark attribution. Root v1:187PASS/2FAIL; v2:192PASS/3FAIL; v3:194PASS/1FAIL; final195PASS. Hai lock-test setups được điều chỉnh theo atomic admission, giữ deadline/rollback; B09 tamper fixture sửa significant signature bit thay vì base64 padding alias, giữ409/no mutation/no calls. Không đổi product security semantics hoặc hạ AC.

Final counters: trace-path consistency3/3; confirmation deadline2/3; quota serialized clock1/3; benchmark attribution1/3; B test-contract expectations3/3; async runner1; missing-time import1; A deadline-test compatibility2; B09 tamper fixture1. Bốn chiến lược observer test không thành công trước handshake được giữ nguyên trong A ledger; không relabel để cấp lại repair budget. Ledger gốc được giữ local; [counter snapshot](evidence/sprint-11/counters.json) không reset lịch sử. S10 harness4/4, product P1 repair1 và closure-commit timeout retry1 vẫn đóng/giữ nguyên; new live inference0.

Timebox29/10/2026:08:00–09:30+07; Review09:10, Retro09:25. Actual outcomes và resource cleanup thuộc record #108 cùng workspace checkpoint/handoff. Không dispatch/rerun CI thủ công, không chờ CI như gate bổ sung; workflow tự chạy được ghi theo evidence ở record chính. Không deployment, mua tài nguyên, thay credentials/shared infrastructure hoặc private external notifications.
