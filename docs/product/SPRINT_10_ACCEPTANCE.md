# Sprint 10 — Nghiệm thu B08

Trạng thái: local verification và [Q độc lập đủ AC1–3/technical DoD PASS](evidence/sprint-10/independent-final-review.json); đang delivery. Chưa nhận story Done, merged hoặc deployed.

Sprint record chính: [#105](https://github.com/stayleadqst/staylead-platform/issues/105). Core duy nhất: [#29 B08](https://github.com/stayleadqst/staylead-platform/issues/29), giữ đủ AC1–3. Không có stretch story; #16/#19 là dependencies dùng lại capability/evidence phù hợp, không đóng parent rộng hơn.

## Candidate và môi trường

- Base integration: bcddfe84e5361587075f08aa01b9ac185998ca43; owner sprint-10-helpful-fallback.
- Product pin cuối: 025039c370c565ce0fb2fe8214e76a84b18a5e15477591618b4d1451168ab498, 217 file apps/src và fixtures; [manifest](evidence/sprint-10/product-candidate-v2.json). Pin cũ8f65426d… giữ làm lịch sử đã bị Q bác vì P1.
- [Test pins](evidence/sprint-10/test-candidate.json), [kỳ vọng độc lập](evidence/sprint-10/expected-results.json), [execution/checkpoint](../execution/SPRINT_10_EXECUTION.md).
- Next.js production build local→same-origin proxy→FastAPI→PostgreSQL riêng. Property/source authored synthetic; provider giả được inject có kiểm soát, không có đường live inference trong test app.
- PG loopback55440, test/browser DB riêng; web13540; API18540 riêng từng ca. Screenshots/logs chi tiết ở workspace validation/sprint-10-20261028, chỉ local.
- C runtime model/effort unavailable; B gpt-6-luna/high; Q context mới gpt-6.1-sol/high, không sửa candidate. Không claim OS-enforced reviewer readonly.

## Kết quả theo AC

| AC | Expected / observed | Evidence và giới hạn |
|---|---|---|
| B08-AC1 | Breakfast có căn cứ vẫn hiện cùng helipad unknown và bước xác nhận; không từ chối cả câu. Component conflict giữ các nguồn xung đột và yêu cầu xác nhận, không chọn ngầm. | Browserdefault5PASS; current grounded contracts; reuse S2 CITY actual partial/conflict theo phạm vi còn hợp lệ. Không chạy model thật mới hoặc nhận toàn bộ model/language quality trên candidate mới. |
| B08-AC2 | Contact/hours do server bind đúng property, link booking và contact cùng dùng được. Explicit control/request mở chi tiết; nêu rõ chưa liên hệ/gửi tin. Thiếu contact/hours nêu unknown, không lấy của property khác. HTML trong config được hiển thị literal, không execute. | Actual API→PG201/200, browserdefault5PASS, scoped config/URL/unit negatives. Source P1 purebooking combined no-text guard đã sửa qua domain-neutral callback + exact Hospitality predicate; Q xác nhận CLOSED. |
| B08-AC3 | Clock timeout1giây trong fake phát ProviderError→API504; UI có fallback tĩnh độc lập model. Arabic/RTL dùng notice Arabic; Korean hiển thị English fallback rõ; property thiếu contact vẫn có thông báo an toàn. Zero automaticretry; guest status-check cùng ID, retry mới sau terminal failure rồi hỏi thông tin mới thành công. | Actual API→PG504 sau1.037giây; browser outage/outage-ar/outage-ko/outage-missing-ar đều exit0; API từng ca stoppedexit0. Đây là controlled offline-provider fault, không phải real provider/adapter acceptance. |

## Thay đổi và giới hạn sử dụng

Contact là cấu hình tùy chọn booking_contact_by_hotel (tối đa240ký tự); hours là booking_contact_hours_by_hotel (tối đa160), keyed bằng hotel slug server đã giải quyết. Giá trị trống/quá dài/có control characters không được phát; UI render text, approved HTTPS booking destination giữ validator cũ. Cấu hình có thể cấp bằng STAYLEAD_BOOKING_CONTACT_BY_HOTEL và STAYLEAD_BOOKING_CONTACT_HOURS_BY_HOTEL dạng JSON; không có contact/hours thật mặc định.

Shared outage resources chỉ là UI status trung lập, không hardcode Hospitality vào sharedcore, không đặt whitelist cho ngôn ngữ hội thoại. Khi không có resource locale phù hợp, hiển thị English và nói rõ fallback. Không tự gửi staff/message, reserve/pay hoặc hứa thời hạn.

Core chỉ chấp nhận empty preparation khi callback domain đã đăng ký xác nhận exact purebooking và toàn bộ substantive channels/patch/claims/refs/ack/clarification rỗng, sau metadata/scope/content checks. Default core không có callback vẫn reject; empty/mixed hotel_information, guest edits/courtesy/localguide không capability, foreign/unsupported và rejected guest claims vẫn bị chặn. Giữ exact M2 confirmation/B09 recovery.

## Local gates

| Gate | Kết quả |
|---|---|
| Grounded orchestrator hiện tại | 105PASS, gồm combinedbooking positive và meaningful negatives |
| Contact/provider fault focused | 5PASS; booking channel compatibility3PASS trước test-only fault delta; không cộng counts trùng |
| B09 API/PG sau P1 | 10PASS |
| Backend Ruff/compile/diff | PASS; test fault delta có Ruff/compilePASS |
| Web contracts/lint/typecheck/production build | 47PASS và gatesPASS; websource không đổi sau build nên reuse |
| Browser integration | default5 +4outagecasesPASS; mobile390, locale/RTL/fallback/recovery, scope/rendering |

## Failures và counters được giữ

Harnessthree repairs trước gồm preparation metadata/scope và readiness; các lượt FAIL không bị xóa. Lượt outage đầu không thật sự inject timeout (fake ngủ2s < turn5s), C dừng mutation tại cap3. Hieu trực tiếp cấp thêm đúng1vòng; harnessattempt4 dùng asyncio.timeout1s→typedprovidererror, API504 trước browser. Tổng harness4/4; không có lượt thứ5. Product P1 no-text/booking contradiction dùng1repair riêng, không reset lịch sử harness. Một lỗi PG sandbox loopback và hai lỗi định dạng test ban đầu được phân biệt với product defect. Live product inference mới=0; coding tokens/cost unavailable.

Giới hạn UI/evidence: CITY chứng minh supported breakfast continuation; case missing-property chỉ chứng minh safe unknown/scope/continuation, không breakfast answer cho Lagoon. Ảnh full-page có internal transcript clipping; thông báo/recovery được kiểm qua DOM assertions/API logs, ảnh hỗ trợ mobile/RTL/literal contact.

## Delivery và sự kiện sprint

Chưa commit/publish/merge tại lúc tạo report. C sẽ đối chiếu source/test pins với tree/head đã publish trước khi chuyển Done. Không manualCI/rerun, không chờ CI làm gate hoặc bypass; workflows tự động có thể chạy khi branch/PR được cập nhật.

Timebox: starts15:40:09, Review16:45, Retro16:55, ends17:00 ngày28-10-2026 +07. Planning/tracker/lịch được bổ sung muộn, không backdate; sự cố và thay đổi quy tắc planning đã ghi trong #105/AGENTS.md. Review bắt đầu thực tế16:47:52+07 (muộn2phút52s so với lịch); snapshot đủAC/QPASS nhưng mergepending. Retro NOT_RUN tại lúc tạo report; Qreview không tự thay hai sự kiện này. Stakeholder feedback thực về planning/process đã có từ Hieu; không có hotel/guest pilot hay product signoff mới.
