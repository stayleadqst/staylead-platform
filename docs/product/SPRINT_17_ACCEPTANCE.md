# Sprint 17 — B05 safe edits, nghiệm thu kỹ thuật

Full [B05 #22](https://github.com/stayleadqst/staylead-platform/issues/22) AC1–3/DoD kỹ thuật được C chấp nhận sau local validation và independent Q review trên candidate 9 file `1b9717bb977274467d8329f7c502e3daa6ebccd4cae6a2e0ae2e20776a937416`, từ canonical `62a3a30d89dc60deba24b6558c8f0ff224588564`. Trạng thái publication/merge và lifecycle thực tế nằm tại [Sprint record #118](https://github.com/stayleadqst/staylead-platform/issues/118); tài liệu này không tự tuyên bố deployed hoặc real-hotel acceptance.

## Thay đổi

Khách có thể lưu rồi bỏ soft view preference qua native schema, current-turn quote authorization, canonical confirmation và M2. Không thêm hard-view hoặc view-fit guarantee. Bounds clear/authorization hỗ trợ đúng 13 room fields; số operations tối đa vẫn12.

Receipt hiển thị actual applied delta cho tất cả13 room fields, gồm clear. Trước sửa, một số room edits vẫn báo không có thay đổi. Khi confirm edit làm brief tăng version, result/answer cũ nay lập tức stale theo authoritative brief version; old selection bị disable ngay, không chờ focus refresh hoặc lượt chat kế. Helper giữ known stale signal và existing absent-metadata behavior, không thêm HTTP/provider calls hoặc sửa M2.

## Full AC matrix

| AC | Expected → observed / evidence |
|---|---|
| AC1 exact edit và retention | Actual UI normal confirm child5/access/softcityview/15mVND stay_total hard budget breakfast+taxes; clearview receipt chỉ View preferences: Not set; lowerbudget receipt chỉ amount12m. Next M4 projections giữ dates/adults/childage/access/currency/basis/strength/inclusions, view absent sau clear. Domain tests còn kiểm giữ child/guardian khác khi thêm member. Separate proposal/cancel giữ v1/adults2/children0; không tự commit suggestion. |
| AC2 CAS/retry/currentness | Source-compatible S5 atomic CAS/request-bound receipt/replay/generated IDs, S9 signed confirmation và S7/S9 result-version guards được Q đối chiếu cụ thể. Original actual v2 oldselection-current-looking FAIL giữ nguyên. Fresh v3 cùng private DB cho stale badge và disabled old action ngay sau confirm trước focus/pageshow/extra turn. |
| AC3 applied delta, race/partial/continue | Receipt lấy delta đã apply, không model narrative; actual continuation clear/lower giữ unrelated state. Q10 independent version-transition cases và exact2 M4 retention oracles PASS. Concurrent/partial/lost-ack/answer-only recovery dùng evidence S5/S9 tương thích và current guard review; không claim fresh forced-partial/concurrency UI run. |

[Q full review](evidence/sprint-17/independent-review.md) và [verdict](evidence/sprint-17/independent-verdict.json): Ready YES, Q17-1/2 closed, không còn actionable finding. [Candidate pins](evidence/sprint-17/candidate.json), [actual consumer report](evidence/sprint-17/consumer-evidence.json), [inherited source compatibility](evidence/sprint-17/inherited-source-compatibility.json). Public review giữ nguyên bản report; các `../...` artifact references trong đó theo original local q/ context, raw logs/provider observations được giữ local tại validation/sprint-17-20261104.

## Kiểm chứng và giới hạn

- A22 affected backend tests PASS, configured Ruff4 và compile4 PASS. Existing S16 no-inferred-view test không đổi.
- B27 focused web tests (đã gồm formatter6), ESLint/typegen/tsc và final production Webpack build PASS. Q10 independent helper cases +2 exact retained-state oracles PASS; all9 source pins và8 harness/fixture pins match.
- Parser preflight8 parsed outputs =4 scenarios×2 parser types, exit0. Actual controlled production UI/proxy/API/M2/M4/UI dùng private PostgreSQL và deterministic provider; B operated AX/screenshots, Q đọc frozen text/provider state, không tự chạy browser/DB. Screenshots chỉ trong CUA transcript, không có screenshot file persisted.
- Tổng23 offline stub invocations ở recording contexts riêng:8 preflight +15 UI (4 original FAIL +8 fresh fixed +3 cancel). Provider IDs lặp giữa instances, không globally unique. Không live model/token/billing claim.
- Source research official [ibis Saigon Airport](https://all.accor.com/hotel/9468/index.en.shtml), [Accor terms July2026](https://all.accor.com/a/en/information/internet-sales-conditions.html), [Sheraton Saigon](https://www.marriott.com/en-us/hotels/sgnsi-sheraton-saigon-grand-opera-hotel/overview/) được đọc04/11 trước plan/fixtures; không chứng minh popularity, giá/availability thật hoặc M1 hotel approval. Fixture synthetic có nhãn; hard access chưa đủ source thì no checked fit, không tự nới điều kiện.

## Lịch sử và counters

Đoạn timebox đầu hết18:20 với0/1Done/GoalNOT_ACHIEVED, parser/UI chưa chạy; ReadyNO và failed evidence giữ nguyên. Sau đó Hieu trực tiếp yêu cầu tiếp tục và xác nhận Sprint17/B05; resumed planning được trình chat/sync#118 trước dispatch, end mới23:20/Review23:05/Retro23:15 trong trần24h. Không backdate outcome cũ hoặc giả human acceptance.

Product3/3 và shared B05 harness3/3 EXHAUSTED; B04/D02/all inherited counters giữ nguyên. Các failed test/import/patch/build/Python/PG operations, một Ruff failed-log overwrite, Q overall KeyError probe và unreserved retry timing được ghi thật; không all-history-PASS hoặc thêm repair allowance. Q cardinality đã có4 actual successful checks trước expectation KeyError; overall probe vẫn FAIL, product finding được đóng bằng completed checks/source/A22.

Private API/web/PG và agent tabs đã dừng, DB/key/initial failed + fresh fixed/cancel sessions giữ nguyên. Không reseed hoặc restart oldS16 resources. No manual CI/rerun/wait-CI-added-gate/workflow-protection bypass, live inference/deploy/paid/shared-credential changes. Automatic CI có thể phát sinh từ authorized PR; chỉ khẳng định kết quả có evidence.
