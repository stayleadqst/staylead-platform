# Sprint 16 — nghiệm thu kỹ thuật B04

Full B04 #21 AC1–3 được C chấp nhận sau local validation và fresh independent Q review. Candidate sáu file: `3e7359afb2435341641d8a09295f5d2ef9c0230e9c3d02aa2757a62575b709f5`, từ canonical `9ec415b6c32bdfb89c43ac1ff62a393f599677d4`. Delivery/merge và lifecycle cuối cùng được ghi tại [Sprint record #116](https://github.com/stayleadqst/staylead-platform/issues/116); báo cáo này không tự tuyên bố đã deployed hoặc hotel/model acceptance.

## Thay đổi và giá trị

Khách cung cấp ngân sách thiếu currency/kỳ sẽ được hỏi đúng phần thiếu trước phép so; không còn mặc định kỳ thành stay_total. Guest budget inclusions được lưu qua typed native schema, quote authorization, M2 và M4, tách khỏi source rate inclusions. Hard-budget lower bound vẫn có thể loại phương án đã chắc vượt trần dù phí/phần bao gồm khác còn unknown. Các key câu hỏi mới đi qua native/Pydantic localization; nhánh làm rõ giữ marker nhu cầu access đã biết.

| AC đầy đủ | Expected → observed / evidence |
|---|---|
| AC1 hard/soft, phủ định, không suy guardian/diagnosis | B actual C1: normal review/confirm chỉ lưu step_free/wheelchair_access hard; không tạo view preference; M4 không đưa phương án khi thiếu party, hỏi số người. Desktop + responsive390×844. Schema/quote và relevant guardian/soft-negative contracts giữ ranh giới. |
| AC2 câu hỏi gắn decision, không hỏi known/irrelevant, supported part giữ | B actual C3 initial có party/dates/twin/6mhard nhưng currency/basis thiếu: UI hỏi đúng hai field và không đưa option; sau bổ sung v2 không hỏi lại. Inclusions vắng không thành câu hỏi thường lệ. Mixed-FAQ regression giữ hotel_answer; Q known-access và missing-field probes kiểm nhánh đổi. C2 dùng lại điều kiện thực C3, không giả thêm run. |
| AC3 giữ known currency/period/inclusions/hard constraints; làm rõ mâu thuẫn trước áp dụng | C3 cùng session normalconfirmv1→v2 giữ2adults/ngàyNov12–15/twinsoft/amount, thêm VND/stay_total/[breakfast,taxes]; M4/UI giữ unknown coverage, không claim in-budget. Q independent hard-bed contradiction qua schema/currentquote/auth→M2→M4 giữ toàn bộ known fields, chỉ disputed hard_bed_types pending/no options; followup clear pending, không đổi unrelated data. 8 checks PASS. Independent lower-bound math giữ hard cap. |

AC3 hard-bed probe có wording tổng quát “Which room requirement should I use?”, causal link là pending leaf; không claim câu hỏi king-specific hay semantic detection bởi model thật. Exact C4 breakfast include/exclude của harness **chưa chạy**, không ghi PASS hoặc coi hard-bed case là chính exact C4. Full nghĩa vụ generic supported AC3 được kiểm bằng evidence riêng; không bắt mọi negative qua UI.

## Kiểm chứng và review

- Relevant contract tests: **112 PASS, 1 deselected**. Deselected là exact inherited `test_rate_validity_covers_charged_nights_not_checkout_day`; test/provenance baseline giữ nguyên. Không có full-backend-PASS claim mới.
- Compile sáu file PASS; git diff check PASS. Configured Ruff sáu file **EXIT1**, duy nhất I001 ở import block `schemas/room_advice.py:3–10`. C và Q independently chạy cùng binary/config trên canonical base và candidate: lỗi/vị trí/message giống hệt, prefix bytes không đổi; **0 lint finding mới**. Không suppress/ignore hoặc ghi all-checks PASS.
- Fresh independent Q đóng Q16-1/2/3, xác nhận fullAC coverage và no open product acceptance finding. [Review verdict](evidence/sprint-16/independent-review.json), [candidate pins](evidence/sprint-16/candidate.json), [independent contradiction evidence](evidence/sprint-16/hard-constraint-contradiction.json).
- User-facing path là actual production-build local UI → API → normal confirmation → M2 → M4 → UI với deterministic offline provider. B operated desktop/C1 mobile-width; Q đọc frozen sanitized operator/readback artifacts, không tự thao tác browser/DB hoặc xem screenshot. Full C3 sequence chạy desktop; mobile là C1 responsive inspection.

## Nghiên cứu và giới hạn

Research trước giải pháp/fixtures/planning đọc nguồn chính thức [ibis Saigon Airport](https://all.accor.com/hotel/9468/index.en.shtml), [Accor service terms July2026](https://all.accor.com/a/en/information/internet-sales-conditions.html), [Sheraton Saigon](https://www.marriott.com/en-us/hotels/sgnsi-sheraton-saigon-grand-opera-hotel/overview/) ngày04/11/2026. Đây là nguồn về operating model/price basis/inclusions/access conditions; không chứng minh popularity, rate/availability cụ thể hoặc hotel-approved M1 source. Fixtures kỹ thuật S7 tương thích được giữ synthetic và valid-window có nhãn; numerical boundary tests không là giá thị trường.

B C3 có CITY-STD queen dù twin là soft preference còn lưu. Ghi đúng observation của bounded stub; không nâng soft thành hard, không claim ranking/suitability/optimality. D2/D3 real-hotel policy/source approval còn riêng. Không live LLM, real quote, inventory, booking/payment, PII send hoặc deployment.

## Lịch sử, counters và delivery boundary

Initial actual UI run vẫn **FAIL**: M2v1 đã apply, harness trả native response wrapper sai provider-neutral contract; parser đúng từ chối invalid_room_advice. Q tái hiện và stored safe error corroborate. Sau quyền Hieu cụ thể, fixed1 dùng NEW private DB/session/evidence namespace, không đổi old failed DB/receipt thành PASS hoặc claim failed-session recovery. Initial2 + fixed1 six = **8 deterministic stub calls**; không là model/token/billing usage.

Product repair1/3; shared B04 harness5/5 **exhausted**, gồm hai direct human extensions cap3→4→5; unreserved correction, lint/path/import mistakes, rejected escalation và mọi failed logs được giữ. D02 product8/8/backend10/10/browser9/9 cùng toàn bộ inherited history/caps/publication failures3 không reset. Source tại checkout divergent cũ được giữ nguyên; owner branch canonical riêng dùng cho publication. Private fixtures/harness/DB/screenshots/node_modules link/old pnpm lock không thuộc product publication.

Runtime/private worker cleanup và Sprint Review16:30/Retro16:40/timebox16:50+07 ghi actual timestamps trên #116; không backdate hoặc tự nhận business acceptance. Không manual CI/rerun/wait-CI added gate, không workflow/protection bypass. Automatic workflows có thể phát sinh từ authorized PR; kết quả CI chỉ theo evidence thực.

Private S16 PG/API/web đã dừng sau Q release; ports56443/18544/13544 không còn listener theo B final checks. Hai DB initial-failed/fixed1 và evidence được giữ. B-created Chrome tabs đã absent; original web source/status hash before/after không đổi.
